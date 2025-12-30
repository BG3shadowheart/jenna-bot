#!/usr/bin/env python3
"""
Patched bot.py — safe voice connection logic

Requirements:
 - Python 3.11
 - discord.py==2.4.0
 - PyNaCl==1.5.0

Optional:
 - aiohttp (if you want the tiny keepalive webserver; add to requirements.txt)

Env vars:
 - BOT_TOKEN
 - GUILD_ID
 - VC_CHANNEL_ID
 - KEEPALIVE_PORT (optional; requires aiohttp)
"""

import os
import asyncio
import logging
import sys
from typing import Optional

import discord
from discord.ext import commands, tasks

# Optional keepalive
try:
    from aiohttp import web  # type: ignore
    HAVE_AIOHTTP = True
except Exception:
    HAVE_AIOHTTP = False

# ---------------- CONFIG / ENV ----------------
TOKEN = os.getenv("BOT_TOKEN")
try:
    GUILD_ID = int(os.getenv("GUILD_ID", "0"))
    VC_CHANNEL_ID = int(os.getenv("VC_CHANNEL_ID", "0"))
except Exception:
    GUILD_ID = 0
    VC_CHANNEL_ID = 0

KEEPALIVE_PORT = int(os.getenv("KEEPALIVE_PORT", "0")) if os.getenv("KEEPALIVE_PORT") else 0
# ---------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("voice-bot")

if not TOKEN:
    logger.error("BOT_TOKEN not set — cannot continue.")
    raise SystemExit(1)
if GUILD_ID == 0 or VC_CHANNEL_ID == 0:
    logger.error("GUILD_ID and VC_CHANNEL_ID must be set to non-zero integer values.")
    raise SystemExit(1)

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
# If you need message content privileges for commands, set intents.message_content = True and enable the intent in dev portal.

bot = commands.Bot(command_prefix="!", intents=intents)

# Single lock to serialize voice operations (prevents race conditions).
voice_lock = asyncio.Lock()
# Track which guilds are currently in a connection attempt
_connecting_guilds = set()

# --------- Core safe connect function (exponential backoff) ----------
async def try_connect_with_backoff(
    guild: discord.Guild,
    target_channel: Optional[discord.abc.GuildChannel] = None,
    max_attempts: int = 8,
):
    """
    Attempt to connect/move the bot to the VC for `guild`.
    Uses reconnect=False on connect and exponential backoff on failure.
    """
    if guild is None:
        logger.warning("try_connect_with_backoff called with guild=None")
        return

    gid = guild.id
    # Avoid overlapping attempts for the same guild
    if gid in _connecting_guilds:
        logger.debug("Connect attempt already in progress for guild %s; skipping.", gid)
        return

    async with voice_lock:
        # mark as connecting
        _connecting_guilds.add(gid)
        try:
            attempt = 0
            base_sleep = 2.0
            while True:
                attempt += 1
                if attempt > max_attempts:
                    logger.error("Max connect attempts reached for guild %s; giving up for now.", gid)
                    return

                try:
                    # Determine the channel to use
                    if target_channel is not None:
                        channel = target_channel
                    else:
                        channel = guild.get_channel(VC_CHANNEL_ID)
                    if channel is None:
                        logger.warning("Target voice channel (id=%s) not found in guild %s", VC_CHANNEL_ID, gid)
                        return

                    # Current voice client for this guild
                    vc = discord.utils.get(bot.voice_clients, guild=guild)
                    # Already connected in the right place?
                    if vc and vc.is_connected() and getattr(vc.channel, "id", None) == channel.id:
                        logger.info("Already connected to desired channel (guild=%s channel=%s).", gid, channel.id)
                        return

                    # Move if connected somewhere else
                    if vc and vc.is_connected():
                        try:
                            logger.info("Moving existing voice client to target channel %s", channel.id)
                            await vc.move_to(channel)
                            return
                        except Exception as e:
                            logger.warning("vc.move_to() failed: %s — will try reconnect", e)

                    # Fresh connect: IMPORTANT use reconnect=False to avoid library internal retries racing with us
                    logger.info("Attempt #%s: connecting to voice (reconnect=False) guild=%s channel=%s", attempt, gid, channel.id)
                    await channel.connect(reconnect=False, timeout=30)
                    logger.info("Connected to voice channel successfully (guild=%s channel=%s).", gid, channel.id)
                    return

                except discord.ClientException as ce:
                    # Often "Already connected to a voice channel." — safe to ignore and treat as success/stop.
                    logger.warning("ClientException during voice connect attempt #%s: %s", attempt, ce)
                    return
                except Exception as e:
                    logger.exception("Voice connect attempt #%s failed for guild %s: %s", attempt, gid, e)
                    # Exponential backoff (cap at 60s)
                    sleep_for = base_sleep * (2 ** (attempt - 1))
                    if sleep_for > 60:
                        sleep_for = 60
                    logger.info("Sleeping %.1fs before next connect attempt...", sleep_for)
                    await asyncio.sleep(sleep_for)
                    continue
        finally:
            _connecting_guilds.discard(gid)


# Periodic ensure task
@tasks.loop(seconds=60.0)
async def ensure_voice_task():
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild is None:
            logger.debug("ensure_voice_task: guild not yet found")
            return

        vc = discord.utils.get(bot.voice_clients, guild=guild)
        if vc and vc.is_connected() and getattr(vc.channel, "id", None) == VC_CHANNEL_ID:
            logger.debug("ensure_voice_task: already connected to target VC")
            return

        # Not connected -> attempt connect
        await try_connect_with_backoff(guild)
    except Exception:
        logger.exception("Exception in ensure_voice_task")


# Optional tiny keepalive webserver (only started if aiohttp present and KEEPALIVE_PORT set)
async def _start_keepalive_server(port: int):
    if not HAVE_AIOHTTP:
        logger.warning("aiohttp not installed; keepalive server not started.")
        return

    async def handle(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", handle)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Keepalive server started on port %s", port)


# Event handlers
@bot.event
async def on_ready():
    logger.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    # Start periodic ensure task (once)
    if not ensure_voice_task.is_running():
        ensure_voice_task.start()

    # Give Discord time to settle then initial connect attempt
    await asyncio.sleep(1.0)
    guild = bot.get_guild(GUILD_ID)
    if guild:
        # schedule initial connect, don't block on it
        bot.loop.create_task(try_connect_with_backoff(guild))

    # Start keepalive server if requested
    if KEEPALIVE_PORT and HAVE_AIOHTTP:
        bot.loop.create_task(_start_keepalive_server(KEEPALIVE_PORT))
    elif KEEPALIVE_PORT and not HAVE_AIOHTTP:
        logger.warning("KEEPALIVE_PORT set but aiohttp not installed. To enable keepalive, add 'aiohttp' to requirements.")


@bot.event
async def on_voice_state_update(member, before, after):
    """
    If the bot itself was disconnected from voice (human kick, network, etc.), schedule a reconnect with a small delay.
    We avoid immediate retries to prevent racing.
    """
    try:
        if member.id != bot.user.id:
            return

        # If bot was disconnected (was in a channel, now not)
        if before.channel is not None and after.channel is None:
            logger.warning("Bot was disconnected from voice (on_voice_state_update). Scheduling reconnect in 10s.")
            # wait a bit to avoid racing with internal library state updates
            await asyncio.sleep(10)
            guild = bot.get_guild(GUILD_ID)
            if guild:
                await try_connect_with_backoff(guild)
        # If bot got moved somewhere else, attempt to move back
        elif after.channel is not None and getattr(after.channel, "id", None) != VC_CHANNEL_ID:
            logger.info("Bot moved to a different channel (id=%s). Will try to move back shortly.", getattr(after.channel, "id", None))
            await asyncio.sleep(2)
            guild = bot.get_guild(GUILD_ID)
            if guild:
                await try_connect_with_backoff(guild)
    except Exception:
        logger.exception("Exception in on_voice_state_update handler")


# Optional admin command to force join (useful for manual debugging/ops)
@bot.command(name="forcejoin")
@commands.is_owner()
async def _forcejoin(ctx):
    """Force the bot to join the configured VC (owner only)."""
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild is None:
            await ctx.send("Configured guild not found.")
            return
        channel = guild.get_channel(VC_CHANNEL_ID)
        if channel is None:
            await ctx.send("Configured voice channel not found.")
            return
        await try_connect_with_backoff(guild, target_channel=channel)
        await ctx.send("Attempted to join/move to configured VC.")
    except Exception as e:
        logger.exception("forcejoin command error")
        await ctx.send(f"Error: {e}")


# Entrypoint
if __name__ == "__main__":
    logger.info("Starting bot main loop")
    try:
        bot.run(TOKEN)
    except Exception:
        logger.exception("Bot crashed on run()")
        raise
