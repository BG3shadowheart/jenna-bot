import os
import sys
import asyncio
import discord

# ===== ENVIRONMENT VARIABLES =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
VOICE_CHANNEL_ID = os.getenv("VOICE_CHANNEL_ID")

# ===== VALIDATION =====
if not DISCORD_TOKEN:
    print("❌ ERROR: DISCORD_TOKEN is not set")
    sys.exit(1)

if not VOICE_CHANNEL_ID:
    print("❌ ERROR: VOICE_CHANNEL_ID is not set")
    sys.exit(1)

try:
    VOICE_CHANNEL_ID = int(VOICE_CHANNEL_ID)
except ValueError:
    print("❌ ERROR: VOICE_CHANNEL_ID must be a number")
    sys.exit(1)

# ===== DISCORD CLIENT =====
intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    client.loop.create_task(keep_in_voice())

async def keep_in_voice():
    await client.wait_until_ready()

    while not client.is_closed():
        try:
            channel = client.get_channel(VOICE_CHANNEL_ID)

            if channel is None:
                print("⚠️ Voice channel not found, retrying in 10s...")
                await asyncio.sleep(10)
                continue

            voice = discord.utils.get(client.voice_clients, guild=channel.guild)

            if voice is None or not voice.is_connected():
                print(f"🔊 Joining voice channel: {channel.name}")
                await channel.connect(reconnect=True)

            await asyncio.sleep(60)

        except Exception as e:
            print("⚠️ Error:", e)
            await asyncio.sleep(10)

# ===== START BOT =====
client.run(DISCORD_TOKEN)
