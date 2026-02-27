import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
import database
import aiosqlite

logger = logging.getLogger('discord')
logging.basicConfig(level=logging.INFO)

POKEMON_DB_URL = "https://pokemondb.net/pokedex/all"
DYNAMAX_URL = "https://pokemondb.net/go/dynamax-attackers"

async def scrape_pokemon_data():
    """
    Scrapes Pokemon data from pokemondb.net and populates the pokemon_species table.
    Uses a single DB connection for performance.
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

    # Open DB connection ONCE
    async with aiosqlite.connect(database.DB_NAME) as db:
        # Enable FKs and dict factory (though we don't strictly need dicts for inserts)
        await db.execute("PRAGMA foreign_keys = ON")

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

                # Extract Stats (Total, HP, Atk, Def, SpA, SpD, Spe)
                # Cols indices:
                # 0: #
                # 1: Name
                # 2: Type
                # 3: Total
                # 4: HP
                # 5: Attack
                # 6: Defense
                # 7: Sp. Atk
                # 8: Sp. Def
                # 9: Speed
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
                    # We need to find base form ID or Name.
                    # Base name is 'name'.

                    # Search for base form
                    async with db.execute("SELECT id FROM pokemon_species WHERE name = ? AND form = 'Normal'", (name,)) as cursor:
                        base_row = await cursor.fetchone()

                    if base_row:
                        # Update can_mega
                        await db.execute("UPDATE pokemon_species SET can_mega = 1 WHERE id = ?", (base_row[0],))
                        await db.commit()

                    # We usually want to store Megas as separate forms too, so continue to upsert below
                    # but if we wanted to skip them we would `continue` here.
                    # The user said "Evolution, forms, the more the better", so we keep them.
                    pass

                icon_span = cols[0].find('span', class_='img-fixed')
                image_url = icon_span.get('data-src') if icon_span else None

                # Upsert Logic
                # Using the expanded schema from database.py
                async with db.execute("SELECT id FROM pokemon_species WHERE pokedex_num = ? AND form = ?", (pokedex_num, form)) as cursor:
                    existing = await cursor.fetchone()

                if existing:
                    await db.execute("""
                        UPDATE pokemon_species
                        SET name=?, type1=?, type2=?, image_url=?, can_dynamax=?, can_gigantamax=?, can_mega=?,
                            hp=?, attack=?, defense=?, sp_atk=?, sp_def=?, speed=?
                        WHERE id=?
                    """, (name, type1, type2, image_url, can_dynamax, can_gigantamax, can_mega,
                          hp, attack, defense, sp_atk, sp_def, speed, existing[0]))
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

        # Scrape Dynamax/Gigantamax from GO Hub
        # We need to pass a new session or manage it better
        async with aiohttp.ClientSession() as session:
             await scrape_dynamax_data(db, session)

        print("Done.")

async def scrape_dynamax_data(db, session):
    """
    Scrapes https://pokemondb.net/go/dynamax-attackers to find which pokemon can Dynamax in GO.
    """
    print("Scraping Dynamax data...")
    # Add User-Agent header to avoid 403 or different content
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    async with session.get(DYNAMAX_URL, headers=headers) as response:
        if response.status != 200:
            logger.error(f"Failed to fetch Dynamax DB: {response.status}")
            return
        html = await response.text()

    soup = BeautifulSoup(html, 'html.parser')

    # Try finding table by class "data-table" first
    table = soup.find('table', class_='data-table')

    # If not found, try searching by content
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

        # Look for name in column 1 (index 1)
        name_cell = cols[1]

        # Name is usually in a span class 'ent-name' or just text
        name_span = name_cell.find('span', class_='ent-name')
        if name_span:
            full_name = name_span.text.strip()
        else:
            full_name = name_cell.get_text(separator=" ").strip()

        # Parse "Gigantamax [Name]" or "Dynamax [Name]"
        # The site seems to prefix them: "Gigantamax Venusaur", "Dynamax Bulbasaur"

        if "Gigantamax " in full_name:
            base_name = full_name.replace("Gigantamax ", "").strip()
            gigantamax_species.add(base_name)
            dynamax_species.add(base_name) # Assuming GMAX implies DMAX
        elif "Dynamax " in full_name:
            base_name = full_name.replace("Dynamax ", "").strip()
            dynamax_species.add(base_name)
        else:
            # Fallback check if it just lists name
            pass

    print(f"Found {len(dynamax_species)} Dynamax species and {len(gigantamax_species)} Gigantamax species in GO.")

    # Update DB
    # We strip " (Single Strike Style)" etc for lookup if needed, but 'Normal' form usually matches base name.
    # We might need to handle form mapping if DB uses "Urshifu (Single Strike)" vs just "Urshifu"

    for name in dynamax_species:
        # Simple name matching first
        cursor = await db.execute("UPDATE pokemon_species SET can_dynamax = 1 WHERE name = ? AND form = 'Normal'", (name,))
        if cursor.rowcount == 0:
            # Try fuzzy match?
            pass

    for name in gigantamax_species:
        await db.execute("UPDATE pokemon_species SET can_gigantamax = 1 WHERE name = ? AND form = 'Normal'", (name,))

    await db.commit()
    print("Dynamax flags updated.")

if __name__ == "__main__":
    try:
        asyncio.run(scrape_pokemon_data())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
