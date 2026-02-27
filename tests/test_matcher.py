import unittest
import os
import asyncio
import database
import services.matcher as matcher

class TestMatcher(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # We need to monkeypatch DB_NAME or rely on it being changeable.
        # Since database.py uses DB_NAME global, we can change it.
        self.original_db_name = database.DB_NAME
        database.DB_NAME = "test_matcher.db"

        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)
        await database.init_db()
        self.pikachu_id = await database.upsert_pokemon_species(25, "Pikachu", "Normal", "Electric")

    async def asyncTearDown(self):
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)
        database.DB_NAME = self.original_db_name

    async def _create_account(self, user_id):
        await database.add_user_account(user_id=user_id, friend_code="123456789012", team="Mystic", region="Praha", account_name="Main")
        accounts = await database.get_user_accounts(user_id)
        return accounts[0]['id']

    async def test_match_creation(self):
        acc1 = await self._create_account(1)
        acc2 = await self._create_account(2)

        # User A wants Pikachu
        listing_a = await database.add_listing(user_id=1, account_id=acc1, listing_type='WANT', species_id=self.pikachu_id)

        # User B has Pikachu
        listing_b = await database.add_listing(user_id=2, account_id=acc2, listing_type='HAVE', species_id=self.pikachu_id)

        # Trigger match for listing_b
        trade_id, match = await matcher.find_match(listing_b)

        self.assertIsNotNone(trade_id)
        # match is the *other* listing (listing_a)
        self.assertEqual(match['id'], listing_a)

    async def test_no_match_same_user(self):
        acc1 = await self._create_account(1)

        # User A wants Pikachu
        listing_a = await database.add_listing(user_id=1, account_id=acc1, listing_type='WANT', species_id=self.pikachu_id)

        # User A has Pikachu (unlikely but possible listing)
        listing_b = await database.add_listing(user_id=1, account_id=acc1, listing_type='HAVE', species_id=self.pikachu_id)

        trade_id, match = await matcher.find_match(listing_b)
        self.assertIsNone(trade_id)

    async def test_match_shiny_strict(self):
        acc1 = await self._create_account(1)
        acc2 = await self._create_account(2)
        acc3 = await self._create_account(3)

        # User A wants Shiny Pikachu
        listing_a = await database.add_listing(user_id=1, account_id=acc1, listing_type='WANT', species_id=self.pikachu_id, is_shiny=True)

        # User B has Normal Pikachu
        listing_b = await database.add_listing(user_id=2, account_id=acc2, listing_type='HAVE', species_id=self.pikachu_id, is_shiny=False)

        trade_id, match = await matcher.find_match(listing_b)
        self.assertIsNone(trade_id)

        # User C has Shiny Pikachu
        listing_c = await database.add_listing(user_id=3, account_id=acc3, listing_type='HAVE', species_id=self.pikachu_id, is_shiny=True)

        trade_id, match = await matcher.find_match(listing_c)
        self.assertIsNotNone(trade_id)
        self.assertEqual(match['id'], listing_a)

if __name__ == '__main__':
    unittest.main()
