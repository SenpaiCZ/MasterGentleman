import aiohttp
import asyncio
from bs4 import BeautifulSoup
import json
import os
import sys

OUTPUT_FILE = "data/pokemon_images.json"
NATIONAL_URL = "https://pokemondb.net/pokedex/national"
SHINY_URL = "https://pokemondb.net/pokedex/shiny"

async def fetch_url(session, url):
    print(f"Fetching {url}...")
    async with session.get(url) as response:
        if response.status != 200:
            print(f"Error fetching {url}: {response.status}")
            return None
        return await response.text()

async def scrape_images():
    async with aiohttp.ClientSession() as session:
        # Fetch National Dex (Normal Images)
        html_national = await fetch_url(session, NATIONAL_URL)
        if not html_national:
            return

        # Fetch Shiny Dex
        html_shiny = await fetch_url(session, SHINY_URL)
        if not html_shiny:
            return

    pokemon_data = {}

    # Parse National
    print("Parsing National Dex...")
    soup_nat = BeautifulSoup(html_national, 'html.parser')
    infocards_nat = soup_nat.select('.infocard')

    for card in infocards_nat:
        try:
            small_data = card.select_one('.infocard-lg-data small')
            if not small_data:
                continue
            id_text = small_data.text.strip()
            if not id_text.startswith('#'):
                continue
            p_id = int(id_text[1:])

            a_ent_name = card.select_one('.ent-name')
            name = a_ent_name.text.strip() if a_ent_name else "Unknown"

            img_tag = card.select_one('.img-sprite')
            if not img_tag:
                continue

            img_url = img_tag.get('src')
            if not img_url or 'data:image' in img_url:
                img_url = img_tag.get('data-src')

            if img_url:
                 if p_id not in pokemon_data:
                     pokemon_data[p_id] = {'name': name}
                 pokemon_data[p_id]['normal'] = img_url

        except Exception as e:
            print(f"Error parsing national card: {e}")

    # Parse Shiny
    print("Parsing Shiny Dex...")
    soup_shiny = BeautifulSoup(html_shiny, 'html.parser')
    infocards_shiny = soup_shiny.select('.infocard')

    for card in infocards_shiny:
        try:
            small_data = card.select_one('.infocard-lg-data small')
            if not small_data:
                continue
            id_text = small_data.text.strip()
            if not id_text.startswith('#'):
                continue

            p_id = int(id_text[1:])

            if p_id not in pokemon_data:
                continue

            if 'shiny' in pokemon_data[p_id]:
                continue

            # Select specifically the shiny sprite
            img_tag = card.select_one('.shinydex-sprite-shiny')

            if not img_tag:
                continue

            img_url = img_tag.get('src')
            if not img_url or 'data:image' in img_url:
                img_url = img_tag.get('data-src')

            if img_url:
                pokemon_data[p_id]['shiny'] = img_url

        except Exception as e:
            print(f"Error parsing shiny card: {e}")

    # Save to JSON
    print(f"Saving {len(pokemon_data)} entries to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(pokemon_data, f, indent=2)
    print("Done.")

if __name__ == "__main__":
    if not os.path.exists('data'):
        os.makedirs('data')
    asyncio.run(scrape_images())
