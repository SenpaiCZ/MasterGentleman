import asyncio
import aiohttp
import re

async def fetch_test():
    url = "https://db.pokemongohub.net/pokemon/150-Mega_X"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            print(f"Status for Mega_X: {response.status}")

asyncio.run(fetch_test())
