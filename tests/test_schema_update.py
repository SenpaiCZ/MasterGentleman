import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import database

class TestDatabaseSchema(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.init_db()

    async def test_schema_columns(self):
        """Verify that new columns exist in the database schema."""
        async with database.get_db() as db:
            # Check users table
            async with db.execute("PRAGMA table_info(users)") as cursor:
                columns = [row['name'] for row in await cursor.fetchall()]
                self.assertIn('want_more_friends', columns)

            # Check listings table
            async with db.execute("PRAGMA table_info(listings)") as cursor:
                columns = [row['name'] for row in await cursor.fetchall()]
                self.assertIn('count', columns)

    async def test_listing_count_default(self):
        """Verify default count is 1."""
        # Create dummy user
        await database.add_user_account(123, "111122223333", "Mystic", "Praha", "TestUser")
        acc = await database.get_user_accounts(123)
        acc_id = acc[0]['id']

        # Create dummy species
        s_id = await database.upsert_pokemon_species(1, "Bulbasaur", "Normal", "Grass")

        # Add listing without count
        l_id = await database.add_listing(123, acc_id, 'HAVE', s_id)

        listing = await database.get_listing(l_id)
        self.assertEqual(listing['count'], 1)

        # Add listing with count
        l_id_2 = await database.add_listing(123, acc_id, 'HAVE', s_id, count=5)
        listing_2 = await database.get_listing(l_id_2)
        self.assertEqual(listing_2['count'], 5)

if __name__ == '__main__':
    unittest.main()
