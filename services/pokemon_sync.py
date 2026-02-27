import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
import database

logger = logging.getLogger('discord')
logging.basicConfig(level=logging.INFO)

POKEMON_DB_URL = "https://pokemondb.net/pokedex/all"
DYNAMAX_URL = "https://pokemondb.net/go/dynamax-attackers"

async def scrape_pokemon_data():
    """
    Scrapes Pokemon data from pokemondb.net and populates the pokemon_species table.
    Uses database.get_db() for connection consistency.
    """
    logger.info("Starting Pokemon data sync...")
    print("Starting Pokemon data sync...")

    async with aiohttp.ClientSession() as session:
        async with session.get(POKEMON_DB_URL) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch Pokemon DB: {response.status}")
                return
            html = await response.text()
            print(f"Downloaded Pokedex HTML, length: {len(html)}")

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', {'id': 'pokedex'})
    if not table:
        print("Table not found!")
        return

    rows = table.find_all('tr')
    print(f"Found {len(rows)} rows.")
    rows = rows[1:]

    count = 0

    # Use database.get_db() context manager
    async with database.get_db() as db:
        # PRAGMA is handled by get_db()

        for i, row in enumerate(rows):
            if i % 100 == 0:
                print(f"Processing row {i}...")

            cols = row.find_all('td')
            if not cols: continue

            try:
                pokedex_num = int(cols[0].find('span', class_='infocard-cell-data').text)

                name_col = cols[1]
                name_link = name_col.find('a', class_='ent-name')
                name = name_link.text

                form_text = name_col.find('small', class_='text-muted')
                form = form_text.text if form_text else 'Normal'

                type_links = cols[2].find_all('a')
                type1 = type_links[0].text
                type2 = type_links[1].text if len(type_links) > 1 else None

                hp = int(cols[4].text)
                attack = int(cols[5].text)
                defense = int(cols[6].text)
                sp_atk = int(cols[7].text)
                sp_def = int(cols[8].text)
                speed = int(cols[9].text)

                can_mega = 'Mega' in form
                can_dynamax = False # Will be updated later
                can_gigantamax = 'Gigantamax' in form

                if 'Mega ' in form or 'Primal ' in form:
                    # Update base form if exists
                    async with db.execute("SELECT id FROM pokemon_species WHERE name = ? AND form = 'Normal'", (name,)) as cursor:
                        base_row = await cursor.fetchone()

                    if base_row:
                        # Update can_mega
                        await db.execute("UPDATE pokemon_species SET can_mega = 1 WHERE id = ?", (base_row['id'],))
                        await db.commit()

                    # Continue to upsert this form
                    pass

                icon_span = cols[0].find('span', class_='img-fixed')
                image_url = icon_span.get('data-src') if icon_span else None

                # Upsert Logic
                async with db.execute("SELECT id FROM pokemon_species WHERE pokedex_num = ? AND form = ?", (pokedex_num, form)) as cursor:
                    existing = await cursor.fetchone()

                if existing:
                    await db.execute("""
                        UPDATE pokemon_species
                        SET name=?, type1=?, type2=?, image_url=?, can_dynamax=?, can_gigantamax=?, can_mega=?,
                            hp=?, attack=?, defense=?, sp_atk=?, sp_def=?, speed=?
                        WHERE id=?
                    """, (name, type1, type2, image_url, can_dynamax, can_gigantamax, can_mega,
                          hp, attack, defense, sp_atk, sp_def, speed, existing['id']))
                else:
                    await db.execute("""
                        INSERT INTO pokemon_species (
                            pokedex_num, name, form, type1, type2, image_url,
                            can_dynamax, can_gigantamax, can_mega,
                            hp, attack, defense, sp_atk, sp_def, speed
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (pokedex_num, name, form, type1, type2, image_url,
                          can_dynamax, can_gigantamax, can_mega,
                          hp, attack, defense, sp_atk, sp_def, speed))

                await db.commit()
                count += 1

            except Exception as e:
                logger.error(f"Error parsing row: {e}")
                continue

        print(f"Synced {count} Pokemon species.")

        # Scrape Dynamax/Gigantamax
        async with aiohttp.ClientSession() as session:
             await scrape_dynamax_data(db, session)

        print("Done.")

async def scrape_dynamax_data(db, session):
    """
    Scrapes https://pokemondb.net/go/dynamax-attackers to find which pokemon can Dynamax in GO.
    """
    print("Scraping Dynamax data...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    async with session.get(DYNAMAX_URL, headers=headers) as response:
        if response.status != 200:
            logger.error(f"Failed to fetch Dynamax DB: {response.status}")
            return
        html = await response.text()

    soup = BeautifulSoup(html, 'html.parser')

    table = soup.find('table', class_='data-table')
    if not table:
        tables = soup.find_all('table')
        for t in tables:
            if "Max Move" in t.text:
                table = t
                break

    if not table:
        print("Dynamax table not found.")
        return

    rows = table.find_all('tr')
    print(f"Found {len(rows)} rows in Dynamax table.")

    dynamax_species = set()
    gigantamax_species = set()

    for row in rows[1:]: # Skip header
        cols = row.find_all('td')
        if not cols or len(cols) < 2: continue

        name_cell = cols[1]
        name_span = name_cell.find('span', class_='ent-name')
        if name_span:
            full_name = name_span.text.strip()
        else:
            full_name = name_cell.get_text(separator=" ").strip()

        if "Gigantamax " in full_name:
            base_name = full_name.replace("Gigantamax ", "").strip()
            gigantamax_species.add(base_name)
            dynamax_species.add(base_name)
        elif "Dynamax " in full_name:
            base_name = full_name.replace("Dynamax ", "").strip()
            dynamax_species.add(base_name)

    print(f"Found {len(dynamax_species)} Dynamax species and {len(gigantamax_species)} Gigantamax species in GO.")

    for name in dynamax_species:
        cursor = await db.execute("UPDATE pokemon_species SET can_dynamax = 1 WHERE name = ? AND form = 'Normal'", (name,))

    for name in gigantamax_species:
        await db.execute("UPDATE pokemon_species SET can_gigantamax = 1 WHERE name = ? AND form = 'Normal'", (name,))

    await db.commit()
    print("Dynamax flags updated.")

if __name__ == "__main__":
    try:
        asyncio.run(scrape_pokemon_data())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
