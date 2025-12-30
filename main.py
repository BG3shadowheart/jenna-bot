import os
import asyncio
import logging
import discord
from discord.ext import commands, tasks

# ---------------- CONFIG ----------------
TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
VC_CHANNEL_ID = int(os.getenv("VC_CHANNEL_ID", "0"))
# ----------------------------------------

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

voice_lock = asyncio.Lock()


async def connect_voice():
    async with voice_lock:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            logging.warning("Guild not found")
            return

        channel = guild.get_channel(VC_CHANNEL_ID)
        if not channel:
            logging.warning("Voice channel not found")
            return

        vc = discord.utils.get(bot.voice_clients, guild=guild)

        # Already connected correctly
        if vc and vc.is_connected() and vc.channel.id == VC_CHANNEL_ID:
            return

        # Move if connected elsewhere
        if vc and vc.is_connected():
            logging.info("Moving bot to correct voice channel")
            await vc.move_to(channel)
            return

        # Fresh connect
        try:
            logging.info("Connecting to voice channel...")
            await channel.connect(reconnect=True, timeout=60)
            logging.info("Voice connected")
        except discord.ClientException:
            logging.warning("Already connecting or connected")
        except Exception:
            logging.exception("Voice connection failed")


@tasks.loop(seconds=45)
async def keep_voice_alive():
    await connect_voice()


@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if not keep_voice_alive.is_running():
        keep_voice_alive.start()


@bot.event
async def on_voice_state_update(member, before, after):
    # React ONLY if the bot itself was disconnected
    if member.id == bot.user.id:
        if before.channel and after.channel is None:
            logging.warning("Bot disconnected from voice, retrying in 10s...")
            await asyncio.sleep(10)
            await connect_voice()


if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot.run(TOKEN)
