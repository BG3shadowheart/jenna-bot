import os
import asyncio
import discord

TOKEN = os.getenv("DISCORD_TOKEN")
VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    client.loop.create_task(stay_in_vc())

async def stay_in_vc():
    await client.wait_until_ready()

    while not client.is_closed():
        try:
            channel = client.get_channel(VOICE_CHANNEL_ID)

            if channel is None:
                print("Voice channel not found, retrying...")
                await asyncio.sleep(10)
                continue

            if not discord.utils.get(client.voice_clients, guild=channel.guild):
                print("Joining voice channel...")
                await channel.connect(reconnect=True)

            await asyncio.sleep(60)

        except Exception as e:
            print("Error:", e)
            await asyncio.sleep(10)

client.run(TOKEN)
