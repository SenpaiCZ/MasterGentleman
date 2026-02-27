import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
import database
import re
from urllib.parse import unquote
import json

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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
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
                # Scrape all Pokemon with Concurrency
                total = MAX_POKEMON_ID
                sem = asyncio.Semaphore(10)  # Limit concurrent requests

                async def sem_process(current_id):
                    async with sem:
                        try:
                            await process_pokemon_family(db, session, current_id)
                        except Exception as e:
                            logger.error(f"Error processing #{current_id}: {e}")

                tasks = [sem_process(i) for i in range(1, total + 1)]

                # Use as_completed to report progress
                for i, future in enumerate(asyncio.as_completed(tasks), 1):
                    await future
                    if progress_callback and i % 10 == 0:
                        await progress_callback(i, total)

                if progress_callback:
                    await progress_callback(total, total)

    print("Pokemon data sync complete.")

async def fetch_url(session, url):
    """
    Helper to fetch a URL with error handling and rate limiting.
    """
    try:
        async with session.get(url) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                logger.error(f"Failed to fetch {url}: {response.status}")
                return None
            return await response.text()
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

async def process_pokemon_family(db, session, pokedex_num):
    """
    Fetches the main pokemon page, parses base form, and discovers/fetches other forms.
    """
    url = f"{BASE_URL}/pokemon/{pokedex_num}"
    html = await fetch_url(session, url)
    if not html:
        print(f"Skipping #{pokedex_num} (Failed to fetch or not found)")
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
    tier_data = parse_tier_ranking(soup)
    best_moveset = parse_best_moveset(soup)
    costumes = parse_costumes(soup)

    # Determine dynamax status from FAQ
    can_dynamax = parse_dynamax_status(soup, base_name)

    # Upsert Base Form
    await upsert_species(db, pokedex_num, base_name, "Normal", types, stats, image_url, shiny_image_url, tier_data, best_moveset, costumes, can_dynamax)
    print(f"Synced #{pokedex_num} {base_name} (Normal)")

    # --- 2. Discover Forms ---
    processed_urls = {url}

    links = soup.find_all('a', href=True)
    form_links = set()

    for link in links:
        href = link['href']
        # Check if it matches /pokemon/{id}-... or https://db.pokemongohub.net/pokemon/{id}-...

        # Normalize href to full URL for checking
        if href.startswith('/'):
            full_url = f"{BASE_URL}{href}"
        elif href.startswith(BASE_URL):
            full_url = href
        else:
            continue

        # Check against pattern
        expected_prefix = f"{BASE_URL}/pokemon/{pokedex_num}-"

        if full_url.startswith(expected_prefix):
            if full_url not in processed_urls:
                form_links.add(full_url)

    # Process discovered forms
    for form_url in form_links:
        processed_urls.add(form_url)
        await process_single_form(db, session, pokedex_num, form_url, base_name)

async def process_single_form(db, session, pokedex_num, url, base_name):
    html = await fetch_url(session, url)
    if not html:
        return

    soup = BeautifulSoup(html, 'html.parser')

    # Determine form name
    # url is like https://db.pokemongohub.net/pokemon/19-Alola
    slug = url.split('/')[-1] # "19-Alola"

    # Sometimes slug might have fragment
    if '#' in slug:
        slug = slug.split('#')[0]

    # Remove pokedex_num prefix
    if slug.startswith(f"{pokedex_num}-"):
        suffix = slug[len(str(pokedex_num))+1:] # "Alola"
    else:
        suffix = slug # Fallback, unlikely if logic is correct

    form_name = suffix.replace("-", " ").title() # "Mega"

    if "Alola" in form_name: form_name = "Alolan"
    if "Galar" in form_name: form_name = "Galarian"
    if "Hisui" in form_name: form_name = "Hisuian"
    if "Paldea" in form_name: form_name = "Paldean"

    best_moveset = parse_best_moveset(soup)

    stats = parse_stats(soup)
    types = parse_types(soup)
    image_url, shiny_image_url = parse_images(soup)
    tier_data = parse_tier_ranking(soup)
    costumes = parse_costumes(soup)

    # Determine dynamax status from FAQ
    # We check if the form name is part of the name used in FAQ, often FAQ refers to the base name
    # But usually db.pokemongohub.net pages are specific to the form.
    # The FAQ check logic is generic based on the soup of the current page.
    full_name = f"{form_name} {base_name}" if form_name != "Normal" else base_name
    can_dynamax = parse_dynamax_status(soup, full_name)

    # Upsert
    await upsert_species(db, pokedex_num, base_name, form_name, types, stats, image_url, shiny_image_url, tier_data, best_moveset, costumes, can_dynamax)
    print(f"  -> Synced #{pokedex_num} {base_name} ({form_name})")


def parse_stats(soup):
    stats = {'attack': 0, 'defense': 0, 'hp': 0, 'max_cp': 0, 'buddy_distance': 0}

    # Helper to extract first integer
    def extract_int(s):
        match = re.search(r'(\d+)', s)
        return int(match.group(1)) if match else 0

    # More robust parsing: look for rows where header contains the key
    # Use re to be insensitive to case and whitespace

    rows = soup.find_all('tr')
    for row in rows:
        header = row.find('th')
        if not header: continue

        # Get all text from header, stripped and lowercased
        header_text = header.get_text().strip().lower()

        value_cell = row.find('td')
        if not value_cell: continue
        value_text = value_cell.get_text().strip()

        # Debug printing
        # print(f"DEBUG: Header='{header_text}' Value='{value_text}'")

        # To prevent overwriting with incorrect tables (e.g. sometimes "Attack" appears in other contexts)
        # We can try to validate the value is somewhat reasonable or check the table context?
        # But for now, let's just match.

        val = extract_int(value_text)

        if 'attack' in header_text:
            # Prevent overwriting if we already have a valid value and this one looks weird?
            # Or assume the FIRST one is the main stats table?
            # Usually the main stats table is near the top.
            if stats['attack'] == 0:
                stats['attack'] = val
        elif 'defense' in header_text:
            if stats['defense'] == 0:
                stats['defense'] = val
        elif 'stamina' in header_text:
            if stats['hp'] == 0:
                stats['hp'] = val
        elif 'max cp' in header_text:
            if stats['max_cp'] == 0:
                stats['max_cp'] = val
        elif 'buddy distance' in header_text:
            if stats['buddy_distance'] == 0:
                stats['buddy_distance'] = val

    return stats

def parse_dynamax_status(soup, pokemon_name):
    """
    Parses the FAQ section to determine if the Pokemon can Dynamax.
    Looks for the question "Can [Name] Dynamax in Pokémon GO?"
    """
    # Find the FAQ section
    faq_section = soup.find('section', class_=re.compile(r'PokemonFAQ_faqSection__'))
    if not faq_section:
        return False

    # Find all questions
    questions = faq_section.find_all('div', itemprop='mainEntity')

    for q in questions:
        question_header = q.find('h3', itemprop='name')
        if not question_header:
            continue

        question_text = question_header.get_text().lower()
        if "can" in question_text and "dynamax" in question_text:
            # Found the dynamax question. Check the answer.
            answer_div = q.find('div', itemprop='acceptedAnswer')
            if answer_div:
                answer_text = answer_div.get_text().lower()
                # Check for positive confirmation
                # "Bulbasaur can Dynamax in Pokémon GO." vs "Ledyba cannot Dynamax in Pokémon GO."
                if "can dynamax" in answer_text and "cannot" not in answer_text:
                    return True
                if "cannot dynamax" in answer_text:
                    return False

    return False

def parse_best_moveset(soup):
    """
    Parses the 'Best moves and movesets' section using the MovesetCard structure.
    Returns a JSON string with details or None.
    """
    # Look for the MovesetCard
    # <div class="MovesetCard_card__B361_"...>
    card = soup.find('div', class_=re.compile(r'MovesetCard_card__'))
    if not card: return None

    header = card.find('header', class_=re.compile(r'MovesetCard_header__'))
    if not header: return None

    # The header text usually contains the summary:
    # "Bulbasaur's best moveset is Vine Whip and Power Whip, with 6.85 DPS... These moves are boosted by Sunny weather."
    text = header.get_text()

    moveset_data = {}

    # Extract Moves
    # Regex: "... best moveset is (.*?) and (.*?), with"
    moves_match = re.search(r"best moveset is (.*?) and (.*?), with", text)
    if moves_match:
        moveset_data['fast_move'] = moves_match.group(1).strip()
        moveset_data['charged_move'] = moves_match.group(2).strip()

    # Extract DPS and TDO from the stats list
    # <ul class="MovesetCard_stats__3Czln">
    #   <li class="MovesetCard_stat__RtCCD"><span>DPS</span><strong>6.85</strong></li>
    #   <li class="MovesetCard_stat__RtCCD"><span>TDO</span><strong>57.50</strong></li>
    stats_list = card.find('ul', class_=re.compile(r'MovesetCard_stats__'))
    if stats_list:
        items = stats_list.find_all('li')
        for item in items:
            label = item.find('span')
            value = item.find('strong')
            if label and value:
                l_text = label.get_text().strip().lower()
                v_text = value.get_text().strip()

                if l_text == 'dps':
                    moveset_data['dps'] = v_text
                elif l_text == 'tdo':
                    moveset_data['tdo'] = v_text
                elif l_text == 'weather':
                    # Weather might be text inside strong or a list of images/text
                    # Example: <strong><ul ...><li>...<span>Sunny</span>...</li></ul></strong>
                    # Or simple text if parsing plain text from header failed?

                    # Try to extract text from the list items if they exist
                    weather_texts = []
                    weather_list = value.find('ul')
                    if weather_list:
                        w_items = weather_list.find_all('li')
                        for w in w_items:
                            w_span = w.find('span') # class="WeatherInfluences_weatherText__..."
                            if w_span:
                                weather_texts.append(w_span.get_text().strip())
                            else:
                                # Fallback: try image alt text?
                                img = w.find('img')
                                if img and img.get('alt'):
                                    weather_texts.append(img.get('alt').title())

                    if weather_texts:
                        moveset_data['weather'] = ", ".join(weather_texts)

    # Fallback to text parsing for Weather if not found in stats list
    if 'weather' not in moveset_data:
        weather_match = re.search(r"boosted by (.*?) weather", text)
        if weather_match:
            moveset_data['weather'] = weather_match.group(1).strip()

    if not moveset_data:
        return None

    return json.dumps(moveset_data)

def parse_tier_ranking(soup):
    """
    Parses the Tier Ranking section.
    Returns a list of dicts: [{'category': 'Raid Attacker', 'tier': 'F Tier', 'rank': '#249'}, ...]
    """
    rankings = []

    cards = soup.find_all('div', class_=re.compile(r'PokemonTierRanking_card__'))

    for card in cards:
        header = card.find('div', class_=re.compile(r'PokemonTierRanking_cardHeader__'))
        body = card.find('div', class_=re.compile(r'PokemonTierRanking_cardBody__'))

        if not header or not body: continue

        category = header.get_text().strip()

        # Check for Not Ranked
        if "Not ranked" in body.get_text():
            rankings.append({
                'category': category,
                'tier': 'Not ranked',
                'rank': None
            })
            continue

        # Extract Tier and Rank
        # <span class="PokemonTierRanking_tier__Z_VsG" ...>F Tier</span>
        tier_span = body.find('span', class_=re.compile(r'PokemonTierRanking_tier__'))
        tier = tier_span.get_text().strip() if tier_span else None

        # <span class="PokemonTierRanking_numericRank__QyD11">#249...</span>
        rank_span = body.find('span', class_=re.compile(r'PokemonTierRanking_numericRank__'))
        rank = rank_span.get_text().strip() if rank_span else None
        # Clean rank text (remove non-digits/hash if needed, or keep as is)

        if tier:
            rankings.append({
                'category': category,
                'tier': tier,
                'rank': rank
            })

    return json.dumps(rankings) if rankings else None

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
    """
    Returns (normal_url, shiny_url).
    Prioritizes Ingame sprites (icon.png) from the "Regular and Shiny" section.
    Falls back to Official artwork if Ingame sprites are not found.
    """
    normal_url = None
    shiny_url = None

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

    def get_best_url(img_tag):
        # Prefer srcset first item (often higher quality in Next.js or just easier to find main src)
        # Actually Next.js srcset has multiple resolutions. We usually want the first one or parsing it.
        # But our goal is to get the `url` param inside the next/image path if possible.

        # Check srcset
        srcset = img_tag.get('srcset')
        if srcset:
            # "url 1x, url 2x" -> split comma, take first part
            first_entry = srcset.split(',')[0].strip() # "url 1x"
            first_url = first_entry.split(' ')[0] # "url"
            candidate = extract_nextjs_url(first_url)
            if candidate and 'http' in candidate or candidate.startswith('/'):
                return candidate

        # Fallback to src
        src = img_tag.get('src')
        return extract_nextjs_url(src)

    # --- 1. Try "Regular and Shiny" Section (Ingame Sprites) ---
    # Look for the section with id="regular-and-shiny"
    # Then find the list immediately following it

    # Finding the UL with class that contains 'PokemonNormalAndShinyComparison_list'
    comparison_list = soup.find('ul', class_=re.compile(r'PokemonNormalAndShinyComparison_list__'))

    if comparison_list:
        # It usually contains two list items: Regular and Shiny
        items = comparison_list.find_all('li')
        for item in items:
            text = item.get_text().lower()
            img = item.find('img')
            if not img: continue

            src = get_best_url(img)
            if not src: continue

            if not src.startswith('http'): src = f"{BASE_URL}{src}"

            if 'shiny' in text:
                shiny_url = src
            else:
                # Assume regular if not shiny (or explicitly 'regular')
                normal_url = src

    # If we found both, return them.
    if normal_url and shiny_url:
        return normal_url, shiny_url

    # --- 2. Fallback: Search globally for Official Artwork ---
    # If we are missing one or both, try to fill in with official artwork
    # Only if we don't have the preferred one.

    images = soup.find_all('img', src=True)

    found_official_normal = None
    found_official_shiny = None

    for img in images:
        src = get_best_url(img)
        if not src: continue

        if not src.startswith('http'): src = f"{BASE_URL}{src}"

        # Official Artwork
        if '/images/official/' in src:
            if '/images/pokemon-home-renders/Shiny/' in src or 'shiny' in src.lower():
                 if not found_official_shiny: found_official_shiny = src
            else:
                # Prefer medium/full over thumb
                if not found_official_normal:
                    found_official_normal = src
                elif 'thumb' in found_official_normal and ('medium' in src or 'full' in src):
                    found_official_normal = src

        # Pokemon Home Renders (often used as fallback)
        elif '/images/pokemon-home-renders/' in src:
             if 'Shiny' in src:
                 if not found_official_shiny: found_official_shiny = src
             elif 'Normal' in src:
                 if not found_official_normal: found_official_normal = src

    if not normal_url:
        normal_url = found_official_normal
    if not shiny_url:
        shiny_url = found_official_shiny

    return normal_url, shiny_url

def parse_costumes(soup):
    """
    Parses the 'Costumes' section.
    Returns a JSON string of a list of dicts:
    [
        {
            'name': 'JAN_2020',
            'image_url': '...',
            'shiny_image_url': '...'
        },
        ...
    ]
    """
    costumes_data = []

    # Find the UL with class PokemonCostumeSprites_list__...
    costume_list = soup.find('ul', class_=re.compile(r'PokemonCostumeSprites_list__'))

    if not costume_list:
        return None

    # Iterate through list items
    # Each list item is usually one variant (e.g. Regular JAN_2020)
    # We want to group by costume name if possible, or just list them.
    # The requirement is: "Bulbasaur has 3 costumes (JAN_2020, SPRING_2020, FALL_2019)... links to costume images might be useful"

    # Structure seems to be:
    # <li> <a ...> <img src="..."> <div class="Badge...">JAN_2020</div> </a> </li>
    # <li> <a ...> <img src="..."> <div class="Badge...">JAN_2020 ✨</div> </a> </li>

    # We will aggregate by name.

    temp_costumes = {} # name -> { normal: url, shiny: url }

    items = costume_list.find_all('li')

    for item in items:
        badge = item.find('div', class_=re.compile(r'Badge_badge__'))
        if not badge: continue

        raw_name = badge.get_text().strip()

        is_shiny = '✨' in raw_name
        name = raw_name.replace('✨', '').strip()

        img = item.find('img')
        if not img: continue

        # Helper to extract nextjs url (copied from parse_images scope or define globally)
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

        def get_best_url(img_tag):
            srcset = img_tag.get('srcset')
            if srcset:
                first_entry = srcset.split(',')[0].strip()
                first_url = first_entry.split(' ')[0]
                candidate = extract_nextjs_url(first_url)
                if candidate and 'http' in candidate or candidate.startswith('/'):
                    return candidate
            src = img_tag.get('src')
            return extract_nextjs_url(src)

        src = get_best_url(img)
        if not src.startswith('http'): src = f"{BASE_URL}{src}"

        if name not in temp_costumes:
            temp_costumes[name] = {'name': name, 'image_url': None, 'shiny_image_url': None}

        if is_shiny:
            temp_costumes[name]['shiny_image_url'] = src
        else:
            temp_costumes[name]['image_url'] = src

    # Convert to list
    costumes_data = list(temp_costumes.values())

    return json.dumps(costumes_data) if costumes_data else None

def get_text(soup, tag):
    t = soup.find(tag)
    return t.text.strip() if t else None

async def upsert_species(db, pokedex_num, name, form, types, stats, image_url, shiny_image_url, tier_data, best_moveset, costumes, can_dynamax):
    type1 = types[0] if len(types) > 0 else None
    type2 = types[1] if len(types) > 1 else None

    # Flags
    # can_dynamax passed as arg from FAQ parsing
    can_gigantamax = "Gigantamax" in form
    can_mega = "Mega" in form or "Primal" in form

    # GO Stats
    hp = stats.get('hp', 0)
    attack = stats.get('attack', 0)
    defense = stats.get('defense', 0)
    max_cp = stats.get('max_cp', 0)
    buddy_distance = stats.get('buddy_distance', 0)

    await database.upsert_pokemon_species(
        pokedex_num, name, form, type1, type2, image_url, shiny_image_url,
        can_dynamax, can_gigantamax, can_mega,
        hp, attack, defense, max_cp,
        buddy_distance, tier_data, best_moveset, costumes
    )

if __name__ == "__main__":
    try:
        asyncio.run(scrape_pokemon_data())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
