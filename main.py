# improved_keepalive_bot.py
import os
import asyncio
import logging

import discord
from discord.ext import tasks, commands
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------- CONFIG (do NOT hardcode your token here) ----------
TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
VC_CHANNEL_ID = int(os.getenv("VC_CHANNEL_ID", "0"))
PORT = int(os.getenv("PORT", "8080"))  # for simple keep-alive webserver
# ---------------------------------------------------------------

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def try_connect():
    """Attempt a single connect / move operation to the target voice channel."""
    if GUILD_ID == 0 or VC_CHANNEL_ID == 0:
        logging.warning("GUILD_ID or VC_CHANNEL_ID not set (0). Skipping connection attempt.")
        return

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        logging.warning("Guild %s not found (bot may not be in that guild).", GUILD_ID)
        return

    channel = guild.get_channel(VC_CHANNEL_ID)
    if channel is None:
        logging.warning("Channel %s not found in guild %s.", VC_CHANNEL_ID, GUILD_ID)
        return

    vc = discord.utils.get(bot.voice_clients, guild=guild)
    try:
        if vc and vc.is_connected():
            # if connected somewhere else, move
            if getattr(vc.channel, "id", None) != VC_CHANNEL_ID:
                logging.info("Voice client connected in another channel -> moving to correct channel.")
                await vc.move_to(channel)
            else:
                # already connected in the correct place
                logging.debug("Already connected in the desired channel.")
            return

        # Not connected -> connect
        logging.info("Not connected -> connecting to voice channel %s ...", VC_CHANNEL_ID)
        await channel.connect(reconnect=True, timeout=60)
        logging.info("Connected to voice channel %s.", VC_CHANNEL_ID)
    except Exception:
        logging.exception("Exception while trying to connect to voice channel")


@tasks.loop(seconds=30.0)
async def ensure_connected():
    """Periodic task to ensure the bot stays in the target VC."""
    await try_connect()


@bot.event
async def on_ready():
    logging.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    # Start the loop only once
    if not ensure_connected.is_running():
        ensure_connected.start()
    # start a tiny webserver (useful for free hosts that require an HTTP endpoint + ping monitor)
    bot.loop.create_task(start_keepalive_webserver())


@bot.event
async def on_voice_state_update(member, before, after):
    # If the bot itself was disconnected from voice, attempt immediate reconnect
    if member.id == bot.user.id:
        # bot got disconnected (after.channel is None) or moved
        if after.channel is None:
            logging.warning("Bot was disconnected from voice (on_voice_state_update). Trying to reconnect now.")
            # run a single reconnect attempt without waiting for the periodic loop
            bot.loop.create_task(try_connect())
        else:
            logging.debug("Bot voice state updated (not a disconnect).")


async def start_keepalive_webserver():
    """
    Starts a trivial webserver that returns 'ok' on GET /. Useful for external ping services
    (UptimeRobot, Healthchecks, etc.) to keep an app awake on some hosting providers.
    """
    async def handle(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", handle)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    try:
        await site.start()
        logging.info("Keep-alive webserver started on port %s", PORT)
    except Exception:
        logging.exception("Keep-alive webserver failed to start")


if __name__ == "__main__":
    if not TOKEN:
        logging.error("ERROR: BOT_TOKEN environment variable not set. Exiting.")
        raise SystemExit(1)
    # run
    bot.run(TOKEN)
