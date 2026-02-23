import discord
import aiohttp
import asyncio
import os
import json

with open('config.json') as f:
    config = json.load(f)
TOKEN = config['discord_token']


CHANNEL_ID = 1334676753846767694  # Your channel ID

async def download_images():
    client = discord.Client(intents=discord.Intents.default())
    
    @client.event
    async def on_ready():
        channel = client.get_channel(CHANNEL_ID)
        os.makedirs('downloaded_images', exist_ok=True)
        
        count = 0
        async for message in channel.history(limit=None):
            for attachment in message.attachments:
                if attachment.content_type and 'image' in attachment.content_type:
                    filename = f"downloaded_images/{attachment.filename}"
                    await attachment.save(filename)
                    count += 1
                    print(f"Downloaded: {attachment.filename}")
                    await asyncio.sleep(0.5)  # Prevents rate limiting
        
        print(f"Done! Downloaded {count} images.")
        await client.close()
    
    await client.start(TOKEN)

asyncio.run(download_images())