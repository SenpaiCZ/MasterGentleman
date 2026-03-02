import asyncio
import database
import services.pokemon_sync as pokemon_sync
import sqlite3

async def setup_test_db():
    await database.init_db()
    async with database.get_db() as db:
        # Insert a phantom variant with 0 stats
        await db.execute("""
            INSERT INTO pokemon_species (pokedex_num, name, form, hp, attack, defense)
            VALUES (1, 'Bulbasaur', 'Phantom', 0, 0, 0)
        """)
        # Insert a phantom variant with non-zero stats (should not be deleted)
        await db.execute("""
            INSERT INTO pokemon_species (pokedex_num, name, form, hp, attack, defense)
            VALUES (1, 'Bulbasaur', 'Phantom Strong', 10, 10, 10)
        """)

        # Insert a valid form just in case
        await db.execute("""
            INSERT INTO pokemon_species (pokedex_num, name, form, hp, attack, defense)
            VALUES (1, 'Bulbasaur', 'Normal', 118, 118, 111)
        """)
        await db.commit()

async def test_phantom():
    await setup_test_db()
    # Now scrape bulbasaur. Normal and shadow forms will be scraped and updated.
    # Phantom and Phantom Strong will be identified as not in scrape.
    # Phantom should be deleted because stats are 0.
    # Phantom Strong should NOT be deleted because stats are > 0.

    # Mock fetch_url to simulate success with no variants
    original_fetch = pokemon_sync.fetch_url
    async def mock_fetch_url(session, url):
        if url == f"{pokemon_sync.BASE_URL}/pokemon/1":
            return "<html><body><h1>Bulbasaur</h1></body></html>"
        return None
    pokemon_sync.fetch_url = mock_fetch_url

    await pokemon_sync.scrape_pokemon_data(pokedex_num=1)

    pokemon_sync.fetch_url = original_fetch

    async with database.get_db() as db:
        async with db.execute("SELECT form FROM pokemon_species WHERE pokedex_num=1") as cursor:
            rows = await cursor.fetchall()
            forms = [r['form'] for r in rows]
            print(f"Remaining forms for Bulbasaur: {forms}")
            assert 'Phantom' not in forms, "Phantom variant with 0 stats was not deleted!"
            assert 'Phantom Strong' in forms, "Phantom Strong variant with non-zero stats was incorrectly deleted!"
            print("Test passed successfully!")

if __name__ == '__main__':
    asyncio.run(test_phantom())
