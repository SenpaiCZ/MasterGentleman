import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
import database
import aiosqlite

logger = logging.getLogger('discord')
logging.basicConfig(level=logging.INFO)

POKEMON_DB_URL = "https://pokemondb.net/pokedex/all"

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
            print(f"Downloaded HTML, length: {len(html)}")

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

                can_mega = 'Mega' in form
                can_dynamax = False
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

                    continue

                icon_span = cols[0].find('span', class_='img-fixed')
                image_url = icon_span.get('data-src') if icon_span else None

                # Upsert Logic
                async with db.execute("SELECT id FROM pokemon_species WHERE pokedex_num = ? AND form = ?", (pokedex_num, form)) as cursor:
                    existing = await cursor.fetchone()

                if existing:
                    await db.execute("""
                        UPDATE pokemon_species
                        SET name=?, type1=?, type2=?, image_url=?, can_dynamax=?, can_gigantamax=?, can_mega=?
                        WHERE id=?
                    """, (name, type1, type2, image_url, can_dynamax, can_gigantamax, can_mega, existing[0]))
                else:
                    await db.execute("""
                        INSERT INTO pokemon_species (pokedex_num, name, form, type1, type2, image_url, can_dynamax, can_gigantamax, can_mega)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (pokedex_num, name, form, type1, type2, image_url, can_dynamax, can_gigantamax, can_mega))

                await db.commit()
                count += 1

            except Exception as e:
                logger.error(f"Error parsing row: {e}")
                continue

        print(f"Synced {count} Pokemon species.")

        # Gmax Update
        gmax_species = [
            "Venusaur", "Charizard", "Blastoise", "Butterfree", "Pikachu", "Meowth", "Machamp", "Gengar",
            "Kingler", "Lapras", "Eevee", "Snorlax", "Garbodor", "Melmetal", "Rillaboom", "Cinderace", "Inteleon",
            "Corviknight", "Orbeetle", "Drednaw", "Coalossal", "Flapple", "Appletun", "Sandaconda", "Toxtricity",
            "Centiskorch", "Hatterene", "Grimmsnarl", "Alcremie", "Copperajah", "Duraludon", "Urshifu"
        ]

        print("Updating GMAX flags...")
        for gmax_name in gmax_species:
            # Find ID by name (Normal form)
            async with db.execute("SELECT id, can_mega FROM pokemon_species WHERE name = ? COLLATE NOCASE AND form = 'Normal'", (gmax_name,)) as cursor:
                row = await cursor.fetchone()

            if row:
                # Update
                await db.execute("UPDATE pokemon_species SET can_dynamax = 1, can_gigantamax = 1 WHERE id = ?", (row[0],))
                await db.commit()

        print("Done.")

if __name__ == "__main__":
    try:
        asyncio.run(scrape_pokemon_data())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
