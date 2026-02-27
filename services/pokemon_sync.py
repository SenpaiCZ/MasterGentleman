import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
import database
import re
from urllib.parse import unquote

logger = logging.getLogger('discord')
logging.basicConfig(level=logging.INFO)

BASE_URL = "https://db.pokemongohub.net"
MAX_POKEMON_ID = 1025

async def scrape_pokemon_data(pokedex_num=None, progress_callback=None):
    """
    Scrapes Pokemon data from db.pokemongohub.net by iterating IDs or scraping a specific ID.
    Populates the pokemon_species table.

    Args:
        pokedex_num (int, optional): The specific Pokedex number to scrape. If None, scrapes all.
        progress_callback (callable, optional): A coroutine to call with progress updates (current, total).
    """
    logger.info("Starting Pokemon GO data sync from db.pokemongohub.net...")
    print("Starting Pokemon GO data sync...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    async with database.get_db() as db:
        async with aiohttp.ClientSession(headers=headers) as session:
            if pokedex_num:
                # Scrape single Pokemon
                try:
                    await process_pokemon_family(db, session, pokedex_num)
                    if progress_callback:
                        await progress_callback(1, 1)
                except Exception as e:
                    logger.error(f"Error processing #{pokedex_num}: {e}")
            else:
                # Scrape all Pokemon
                total = MAX_POKEMON_ID
                for current_id in range(1, total + 1):
                    try:
                        await process_pokemon_family(db, session, current_id)
                        if progress_callback and current_id % 10 == 0:
                            await progress_callback(current_id, total)
                    except Exception as e:
                        logger.error(f"Error processing #{current_id}: {e}")

                    # Polite delay
                    await asyncio.sleep(1.0)

                if progress_callback:
                    await progress_callback(total, total)

    print("Pokemon data sync complete.")

async def process_pokemon_family(db, session, pokedex_num):
    """
    Fetches the main pokemon page, parses base form, and discovers/fetches other forms.
    """
    url = f"{BASE_URL}/pokemon/{pokedex_num}"
    try:
        async with session.get(url) as response:
            if response.status == 404:
                print(f"Pokemon #{pokedex_num} not found (404). Skipping.")
                return
            if response.status != 200:
                logger.error(f"Failed to fetch {url}: {response.status}")
                return
            html = await response.text()
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return

    soup = BeautifulSoup(html, 'html.parser')

    # --- 1. Parse Base Form ---
    base_name = get_text(soup, 'h1')
    if not base_name:
        base_name = f"Pokemon {pokedex_num}"

    base_name = re.sub(r'\s*#\d+$', '', base_name).strip()

    stats = parse_stats(soup)
    types = parse_types(soup)
    image_url, shiny_image_url = parse_images(soup)

    # Upsert Base Form
    await upsert_species(db, pokedex_num, base_name, "Normal", types, stats, image_url, shiny_image_url)
    print(f"Synced #{pokedex_num} {base_name} (Normal)")

    # --- 2. Discover Forms ---
    processed_urls = {url}

    links = soup.find_all('a', href=True)
    form_links = set()

    for link in links:
        href = link['href']
        # Check if it matches /pokemon/{id}-...
        if href.startswith(f"/pokemon/{pokedex_num}-"):
            full_url = f"{BASE_URL}{href}"
            if full_url not in processed_urls:
                form_links.add(full_url)

    # Process discovered forms
    for form_url in form_links:
        processed_urls.add(form_url)
        await process_single_form(db, session, pokedex_num, form_url, base_name)

async def process_single_form(db, session, pokedex_num, url, base_name):
    try:
        async with session.get(url) as response:
            if response.status != 200: return
            html = await response.text()
    except:
        return

    soup = BeautifulSoup(html, 'html.parser')

    # Determine form name
    slug = url.split('/')[-1] # "3-Mega"
    suffix = slug.replace(f"{pokedex_num}-", "") # "Mega"

    form_name = suffix.replace("-", " ").title() # "Mega"

    if "Alola" in form_name: form_name = "Alolan"
    if "Galar" in form_name: form_name = "Galarian"
    if "Hisui" in form_name: form_name = "Hisuian"
    if "Paldea" in form_name: form_name = "Paldean"

    stats = parse_stats(soup)
    types = parse_types(soup)
    image_url, shiny_image_url = parse_images(soup)

    # Upsert
    await upsert_species(db, pokedex_num, base_name, form_name, types, stats, image_url, shiny_image_url)
    print(f"  -> Synced #{pokedex_num} {base_name} ({form_name})")


def parse_stats(soup):
    stats = {'attack': 0, 'defense': 0, 'hp': 0, 'max_cp': 0}
    text = soup.get_text()

    atk_match = re.search(r'Attack\s+(\d+)', text)
    if atk_match: stats['attack'] = int(atk_match.group(1))

    def_match = re.search(r'Defense\s+(\d+)', text)
    if def_match: stats['defense'] = int(def_match.group(1))

    hp_match = re.search(r'Stamina\s+(\d+)', text)
    if hp_match: stats['hp'] = int(hp_match.group(1))

    # Look for Max CP (Level 50) in text
    # The page often has "Max CP 1260 CP" or similar in a table
    # We look for "Max CP" followed by numbers
    max_cp_match = re.search(r'Max CP\s+(\d+)', text)
    if max_cp_match:
        stats['max_cp'] = int(max_cp_match.group(1))

    return stats

def parse_types(soup):
    found_types = []
    # Search for type links in the specific "header" area or just generally unique ones
    # db.pokemongohub.net structure usually puts type icons near the top with links like /pokemon-list/type-xxx

    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/pokemon-list/type-' in href:
            t = href.split('-')[-1].capitalize()
            if t not in found_types:
                found_types.append(t)

    return found_types[:2] if found_types else []

def parse_images(soup):
    """Returns (normal_url, shiny_url)"""
    normal_url = None
    shiny_url = None

    images = soup.find_all('img', src=True)

    # Helper to extract nextjs url
    def extract_nextjs_url(src):
        if 'url=' in src:
            try:
                start = src.find('url=') + 4
                end = src.find('&', start)
                if end == -1: end = len(src)
                return unquote(src[start:end])
            except:
                return src
        return src

    # 1. Look for Official
    for img in images:
        src = extract_nextjs_url(img['src'])
        if not src.startswith('http'): src = f"{BASE_URL}{src}"

        if '/images/official/' in src:
            # We prefer 'medium' or 'full'.
            if not normal_url:
                normal_url = src
            elif 'thumb' in normal_url and ('medium' in src or 'full' in src):
                normal_url = src

    # 2. Look for Shiny (Home Renders or Ingame)
    # Search for "Shiny" in alt text or surroundings?
    # Or look for specific path patterns.
    # Pokemon Home Shiny: /images/pokemon-home-renders/Shiny/
    # Ingame Shiny: .s.icon.png

    for img in images:
        src = extract_nextjs_url(img['src'])
        if not src.startswith('http'): src = f"{BASE_URL}{src}"

        if '/images/pokemon-home-renders/Shiny/' in src:
            if not shiny_url: shiny_url = src
            # Prefer higher res if possible?

        elif '.s.icon.png' in src:
            # Ingame shiny
            if not shiny_url: shiny_url = src

    # Fallback for normal if no official
    if not normal_url:
        for img in images:
            src = extract_nextjs_url(img['src'])
            if not src.startswith('http'): src = f"{BASE_URL}{src}"
            if '/images/pokemon-home-renders/Normal/' in src:
                normal_url = src
                break

    return normal_url, shiny_url

def get_text(soup, tag):
    t = soup.find(tag)
    return t.text.strip() if t else None

async def upsert_species(db, pokedex_num, name, form, types, stats, image_url, shiny_image_url):
    type1 = types[0] if len(types) > 0 else None
    type2 = types[1] if len(types) > 1 else None

    # Flags
    can_dynamax = "Gigantamax" in form
    can_gigantamax = "Gigantamax" in form
    can_mega = "Mega" in form or "Primal" in form

    # GO Stats
    hp = stats.get('hp', 0)
    attack = stats.get('attack', 0)
    defense = stats.get('defense', 0)
    max_cp = stats.get('max_cp', 0)

    sp_atk = 0
    sp_def = 0
    speed = 0

    await database.upsert_pokemon_species(
        pokedex_num, name, form, type1, type2, image_url, shiny_image_url,
        can_dynamax, can_gigantamax, can_mega,
        hp, attack, defense, sp_atk, sp_def, speed, max_cp
    )

if __name__ == "__main__":
    try:
        asyncio.run(scrape_pokemon_data())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
