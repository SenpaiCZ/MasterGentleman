import aiohttp
import asyncio

async def fetch():
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://db.pokemongohub.net/",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get("https://db.pokemongohub.net/pokemon/201-Exclamation") as resp:
            text = await resp.text()
            print("Length:", len(text))

            import re
            matches = re.findall(r'poke_capture_(\d+)_(\d+)_([a-zA-Z0-9_]+)', text)
            unique_forms = set([(m[0], m[1]) for m in matches])
            print("Forms:", sorted(unique_forms))

asyncio.run(fetch())
