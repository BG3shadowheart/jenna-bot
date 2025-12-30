# main.py
import os
import asyncio
import logging
import socket
import discord
from discord.ext import tasks, commands

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
VC_CHANNEL_ID = int(os.getenv("VC_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

voice_lock = asyncio.Lock()
is_connecting = False  # guard flag


async def try_connect_with_backoff(max_attempts=None):
    """Try to connect with exponential backoff. This uses reconnect=False and we handle retries."""
    global is_connecting
    async with voice_lock:
        if is_connecting:
            logging.debug("Already connecting; skipping new attempt.")
            return
        is_connecting = True

    try:
        attempt = 0
        base_sleep = 2.0
        while True:
            attempt += 1
            if max_attempts and attempt > max_attempts:
                logging.error("Max connection attempts reached, giving up for now.")
                return

            try:
                guild = bot.get_guild(GUILD_ID)
                if guild is None:
                    logging.warning("Guild %s not found; is bot in that guild?", GUILD_ID)
                    return

                channel = guild.get_channel(VC_CHANNEL_ID)
                if channel is None:
                    logging.warning("Voice channel %s not found in guild %s", VC_CHANNEL_ID, GUILD_ID)
                    return

                vc = discord.utils.get(bot.voice_clients, guild=guild)
                if vc and vc.is_connected() and vc.channel.id == VC_CHANNEL_ID:
                    logging.info("Already connected to the correct voice channel.")
                    return

                if vc and vc.is_connected():
                    logging.info("Moving existing voice client to target channel.")
                    await vc.move_to(channel)
                    return

                logging.info("Attempt #%s connecting to voice (reconnect=False)", attempt)
                # Important: use reconnect=False to avoid discord.py internal retries
                await channel.connect(reconnect=False, timeout=20)
                logging.info("Connected to voice channel successfully.")
                return

            except Exception as e:
                # Dump useful diagnostics
                logging.exception("Voice connect attempt %s failed: %s", attempt, e)

                # If we detect a network/UDP issue, we should back off longer
                sleep = base_sleep * (2 ** (attempt - 1))
                if sleep > 60:
                    sleep = 60
                logging.info("Sleeping %.1fs before next attempt...", sleep)
                await asyncio.sleep(sleep)
                # loop and retry
    finally:
        is_connecting = False


@tasks.loop(seconds=60)
async def periodic_ensure_voice():
    try:
        # quick checks
        guild = bot.get_guild(GUILD_ID)
        if guild is None:
            logging.debug("Guild not available yet.")
            return
        vc = discord.utils.get(bot.voice_clients, guild=guild)
        if vc and vc.is_connected() and getattr(vc.channel, "id", None) == VC_CHANNEL_ID:
            logging.debug("Voice is already connected.")
            return
        await try_connect_with_backoff(max_attempts=6)
    except Exception:
        logging.exception("Error in periodic_ensure_voice")


@bot.event
async def on_ready():
    logging.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    if not periodic_ensure_voice.is_running():
        periodic_ensure_voice.start()


@bot.event
async def on_voice_state_update(member, before, after):
    # Only react to a real disconnect (and don't immediately spawn many attempts)
    if member.id == bot.user.id:
        if before.channel and after.channel is None:
            logging.warning("Detected bot voice disconnect (on_voice_state_update). Scheduling reconnect in 10s.")
            # schedule single reconnect (do not call direct if already connecting)
            await asyncio.sleep(10)
            await try_connect_with_backoff(max_attempts=6)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN missing")
    bot.run(TOKEN)
