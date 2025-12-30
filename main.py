# main.py
import os
import sys
import asyncio
import discord

# === Read env vars (names must match Railway service variables) ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")         # optional - not required but safe to accept
VC_CHANNEL_ID = os.getenv("VC_CHANNEL_ID")

# === Quick validation ===
print("DEBUG: starting up, checking env variables...")
print("DEBUG: DISCORD_TOKEN present?", bool(DISCORD_TOKEN))
print("DEBUG: GUILD_ID:", GUILD_ID)
print("DEBUG: VC_CHANNEL_ID:", VC_CHANNEL_ID)

if not DISCORD_TOKEN:
    print("❌ ERROR: DISCORD_TOKEN is missing. Stop.")
    sys.exit(1)

if not VC_CHANNEL_ID:
    print("❌ ERROR: VC_CHANNEL_ID is missing. Stop.")
    sys.exit(1)

try:
    VC_CHANNEL_ID = int(VC_CHANNEL_ID)
except ValueError:
    print("❌ ERROR: VC_CHANNEL_ID must be a numeric ID (no spaces). Got:", VC_CHANNEL_ID)
    sys.exit(1)

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
            channel = client.get_channel(VC_CHANNEL_ID)
            if channel is None:
                print(f"⚠️ Channel {VC_CHANNEL_ID} not found in cache. Retrying in 10s...")
                await asyncio.sleep(10)
                continue

            voice = discord.utils.get(client.voice_clients, guild=channel.guild)
            if voice is None or not voice.is_connected():
                print(f"🔗 Connecting to voice channel: {channel.name} ({channel.id})")
                await channel.connect(reconnect=True)
            else:
                # already connected
                await asyncio.sleep(60)

        except Exception as e:
            print("⚠️ Error in loop:", repr(e))
            await asyncio.sleep(10)

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
