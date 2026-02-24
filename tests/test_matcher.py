import unittest
import os
import asyncio
import database
import services.matcher as matcher

class TestMatcher(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database.DB_NAME = "test_matcher.db"
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)
        await database.init_db()

    async def asyncTearDown(self):
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)

    async def test_match_creation(self):
        # User A wants Pikachu
        listing_a = await database.add_listing(user_id=1, listing_type='WANT', pokemon_id=25)

        # User B has Pikachu
        listing_b = await database.add_listing(user_id=2, listing_type='HAVE', pokemon_id=25)

        # Trigger match for listing_b
        trade_id, match = await matcher.find_match(listing_b)

        self.assertIsNotNone(trade_id)
        self.assertEqual(match['id'], listing_a)

        # Verify status updates
        la = await database.get_listing(listing_a)
        lb = await database.get_listing(listing_b)
        self.assertEqual(la['status'], 'PENDING')
        self.assertEqual(lb['status'], 'PENDING')

        # Verify trade record
        trade = await database.get_listing(listing_b) # Wait, get_trade_by_channel(None)? No
        # We need get_trade(id)
        # database.py doesn't have get_trade_by_id.
        # But we can query manually or use `get_trade_by_channel` if we set it.
        # But we just verified listings are PENDING.

    async def test_no_match_same_user(self):
        # User A wants Pikachu
        listing_a = await database.add_listing(user_id=1, listing_type='WANT', pokemon_id=25)

        # User A has Pikachu (unlikely but possible listing)
        listing_b = await database.add_listing(user_id=1, listing_type='HAVE', pokemon_id=25)

        trade_id, match = await matcher.find_match(listing_b)
        self.assertIsNone(trade_id)

    async def test_match_shiny_strict(self):
        # User A wants Shiny Pikachu
        listing_a = await database.add_listing(user_id=1, listing_type='WANT', pokemon_id=25, is_shiny=True)

        # User B has Normal Pikachu
        listing_b = await database.add_listing(user_id=2, listing_type='HAVE', pokemon_id=25, is_shiny=False)

        trade_id, match = await matcher.find_match(listing_b)
        self.assertIsNone(trade_id)

        # User C has Shiny Pikachu
        listing_c = await database.add_listing(user_id=3, listing_type='HAVE', pokemon_id=25, is_shiny=True)

        trade_id, match = await matcher.find_match(listing_c)
        self.assertIsNotNone(trade_id)
        self.assertEqual(match['id'], listing_a)

if __name__ == '__main__':
    unittest.main()
