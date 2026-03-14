import sqlite3
import asyncio
import unittest
from unittest.mock import MagicMock
import sys
import os

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class MockCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def __await__(self):
        async def _wrap():
            return self
        return _wrap().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def fetchall(self):
        return self._cursor.fetchall()

    async def fetchone(self):
        return self._cursor.fetchone()

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

class MockConnection:
    def __init__(self, conn):
        self._conn = conn
        self._row_factory = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def execute(self, sql, params=()):
        return MockCursor(self._conn.execute(sql, params))

    async def commit(self):
        self._conn.commit()

    async def close(self):
        # We don't actually close the shared connection to keep it alive
        pass

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, factory):
        self._row_factory = factory
        self._conn.row_factory = factory

# Global mock connection to persist in-memory across connect calls
shared_conn = None

async def mock_connect(database, **kwargs):
    global shared_conn
    if database == ":memory:":
        if shared_conn is None:
            shared_conn = sqlite3.connect(":memory:")
        return MockConnection(shared_conn)
    return MockConnection(sqlite3.connect(database))

# Mock aiosqlite
mock_aiosqlite = MagicMock()
mock_aiosqlite.connect = mock_connect
sys.modules['aiosqlite'] = mock_aiosqlite

import database

class TestDatabaseUsers(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database.DB_NAME = ":memory:"
        # Re-initialize shared connection for each test to have a clean state
        global shared_conn
        if shared_conn:
            shared_conn.close()
        shared_conn = sqlite3.connect(":memory:")
        await database.init_db()

    async def test_get_users_wanting_friends_limit(self):
        """Verify get_users_wanting_friends respects the limit and filters correctly."""
        # Insert 30 users who want friends
        for i in range(30):
            await database.add_user_account(
                user_id=i,
                friend_code=f"code{i}",
                team="Mystic",
                region="Region",
                account_name=f"User{i}",
                want_more_friends=True
            )

        # Insert 5 users who DON'T want friends
        for i in range(30, 35):
            await database.add_user_account(
                user_id=i,
                friend_code=f"code{i}",
                team="Mystic",
                region="Region",
                account_name=f"User{i}",
                want_more_friends=False
            )

        # 1. Test default limit (25)
        users = await database.get_users_wanting_friends()
        self.assertEqual(len(users), 25)
        for user in users:
            self.assertEqual(user['want_more_friends'], 1)

        # 2. Test custom limit (10)
        users = await database.get_users_wanting_friends(limit=10)
        self.assertEqual(len(users), 10)

        # 3. Test fewer users than limit
        # Clear users and add only 5
        async with database.get_db() as db:
            await db.execute("DELETE FROM users")
            await db.commit()

        for i in range(5):
            await database.add_user_account(
                user_id=i+100,
                friend_code=f"code{i}",
                team="Mystic",
                region="Region",
                account_name=f"User{i}",
                want_more_friends=True
            )

        users = await database.get_users_wanting_friends(limit=25)
        self.assertEqual(len(users), 5)

if __name__ == '__main__':
    unittest.main()
