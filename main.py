import discord
from discord.ext import commands, tasks
import asyncio
import os
from gtts import gTTS
import subprocess
import uuid
import shlex

TOKEN = "MTQ0NTkxMDE4NzU0NTQ2MDgyNw.GQ_Na5.ZTcHYK3JMHjAR6XgvETGbb43X5--TPolVBwnr8"  # your token
GUILD_ID = 1332352861723562054
VC_CHANNEL_ID = 1353875404217253909

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def connect_to_vc():
    """Connect bot to the voice channel."""
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("Guild not found.")
            return

        channel = guild.get_channel(VC_CHANNEL_ID)
        if not channel:
            print("Voice channel not found.")
            return

        vc = discord.utils.get(bot.voice_clients, guild=guild)

        if vc and vc.is_connected():
            return

        print("[connect_to_vc] Connecting to VC...")
        await channel.connect()
        print("[connect_to_vc] Connected.")

    except Exception as e:
        print("VC connect error:", e)


@tasks.loop(seconds=20)
async def keep_alive():
    """Ensures bot stays connected every 20 seconds."""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    vc = discord.utils.get(bot.voice_clients, guild=guild)
    channel = guild.get_channel(VC_CHANNEL_ID)

    if not vc or not vc.is_connected():
        print("[keep_alive] Bot disconnected — reconnecting...")
        await connect_to_vc()

    elif vc.channel.id != VC_CHANNEL_ID:
        print("[keep_alive] Bot is in wrong VC — reconnecting...")
        try:
            await vc.disconnect(force=True)
        except:
            pass
        await connect_to_vc()


async def speak_text(vc, text, style="female_sexy_subtle"):
    """TTS → pitch tuned → VC playback."""
    if not vc or not vc.is_connected():
        print("VC not connected, cannot speak.")
        return

    base_id = uuid.uuid4().hex[:8]
    raw_mp3 = f"/tmp/voice_{base_id}.mp3"
    tuned_mp3 = f"/tmp/voice_tuned_{base_id}.mp3"

    try:
        tts = gTTS(text=text, lang="en")
        tts.save(raw_mp3)

        if style == "female_sexy_subtle":
            ffmpeg_filter = (
                "asetrate=48000*1.18,aresample=48000,atempo=1.07,"
                "equalizer=f=3000:t=q:w=2:g=2"
            )
        else:
            ffmpeg_filter = (
                "asetrate=48000*1.12,aresample=48000,atempo=1.03,"
                "equalizer=f=3500:t=q:w=2:g=1.2"
            )

        cmd = (
            f"ffmpeg -y -loglevel error -i {shlex.quote(raw_mp3)} "
            f"-af \"{ffmpeg_filter}\" {shlex.quote(tuned_mp3)}"
        )

        print("Running ffmpeg:", cmd)
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()

        if proc.returncode != 0:
            print("ffmpeg failed, fallback to raw mp3.")
            tuned_mp3 = raw_mp3

        if vc.is_playing():
            vc.stop()

        source = discord.FFmpegPCMAudio(tuned_mp3)
        vc.play(source)

        while vc.is_playing():
            await asyncio.sleep(0.3)

    except Exception as e:
        print("TTS error:", e)
    finally:
        try:
            if os.path.exists(raw_mp3):
                os.remove(raw_mp3)
        except:
            pass
        try:
            if os.path.exists(tuned_mp3):
                os.remove(tuned_mp3)
        except:
            pass


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await connect_to_vc()
    keep_alive.start()


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id:
        if after.channel is None:
            print("Bot disconnected — reconnecting.")
            await connect_to_vc()
        return

    if after.channel and after.channel.id == VC_CHANNEL_ID:
        guild = bot.get_guild(GUILD_ID)
        vc = discord.utils.get(bot.voice_clients, guild=guild)

        if vc and vc.is_connected():
            text = f"Welcome {member.display_name}, I’m happy to see you."
            await speak_text(vc, text, style="female_sexy_subtle")


bot.run(TOKEN)
