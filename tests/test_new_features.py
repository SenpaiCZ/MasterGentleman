import asyncio
import unittest
from unittest.mock import MagicMock, patch
import database

class TestDatabaseLogic(unittest.IsolatedAsyncioTestCase):
    async def test_update_listing_status(self):
        """Verify update_listing_status function works (was missing before)."""
        # Create dummy user & listing
        await database.add_user_account(999, "999988887777", "Valor", "Brno", "TestStatus")
        acc = await database.get_user_accounts(999)
        s_id = await database.upsert_pokemon_species(25, "Pikachu", "Normal", "Electric")
        l_id = await database.add_listing(999, acc[0]['id'], 'HAVE', s_id)

        # Default status is ACTIVE
        l = await database.get_listing(l_id)
        self.assertEqual(l['status'], 'ACTIVE')

        # Update
        await database.update_listing_status(l_id, 'PENDING')
        l = await database.get_listing(l_id)
        self.assertEqual(l['status'], 'PENDING')

    async def test_suggestion_config(self):
        """Verify guild config supports suggestion fields."""
        guild_id = 12345
        await database.set_guild_config(
            guild_id,
            suggestion_channel_id=555,
            upvote_emoji="UP",
            downvote_emoji="DOWN"
        )

        config = await database.get_guild_config(guild_id)
        self.assertEqual(config['suggestion_channel_id'], 555)
        self.assertEqual(config['upvote_emoji'], "UP")
        self.assertEqual(config['downvote_emoji'], "DOWN")

if __name__ == '__main__':
    unittest.main()
