import asyncio
import aiohttp
import re

async def fetch_sitemap():
    url = "https://db.pokemongohub.net/pokemon/sitemap/0.xml"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            if response.status == 200:
                text = await response.text()
                links = re.findall(r'<loc>(.*?)</loc>', text)
                print(f"Sitemap 0 has {len(links)} links")
                print("First 10:")
                for l in links[:10]:
                    print(l)
            else:
                print(f"Failed to fetch sitemap 0: {response.status}")

asyncio.run(fetch_sitemap())
