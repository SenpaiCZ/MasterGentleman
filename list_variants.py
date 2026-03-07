import aiohttp
import asyncio
import re

async def main():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with aiohttp.ClientSession(headers=headers) as session:
        for i in range(14):
            url = f"https://db.pokemongohub.net/pokemon/sitemap/{i}.xml"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.text()
                        links = re.findall(r'<loc>(.*?)</loc>', data)

                        mewtwo_links = [l for l in links if '/pokemon/150' in l]
                        if mewtwo_links:
                            print(f"Found in {i}.xml:")
                            for ml in mewtwo_links:
                                print(ml)
            except Exception as e:
                print(f"Error {i}:", e)

if __name__ == "__main__":
    asyncio.run(main())
