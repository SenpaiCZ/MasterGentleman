import aiosqlite
import os

DB_NAME = "trade_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                listing_type TEXT NOT NULL CHECK(listing_type IN ('HAVE', 'WANT')),
                pokemon_id INTEGER NOT NULL,
                is_shiny BOOLEAN DEFAULT 0,
                is_purified BOOLEAN DEFAULT 0,
                details TEXT,
                status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'PENDING', 'COMPLETED', 'CANCELLED')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                listing_a_id INTEGER NOT NULL,
                listing_b_id INTEGER NOT NULL,
                status TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'CLOSED')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (listing_a_id) REFERENCES listings (id),
                FOREIGN KEY (listing_b_id) REFERENCES listings (id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                friend_code TEXT,
                team TEXT,
                region TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def add_listing(user_id, listing_type, pokemon_id, is_shiny=False, is_purified=False, details=None):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO listings (user_id, listing_type, pokemon_id, is_shiny, is_purified, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, listing_type, pokemon_id, is_shiny, is_purified, details))
        await db.commit()
        return cursor.lastrowid

async def get_listing(listing_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)) as cursor:
            return await cursor.fetchone()

async def get_user_listings(user_id, status='ACTIVE'):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM listings WHERE user_id = ? AND status = ?", (user_id, status)) as cursor:
            return await cursor.fetchall()

async def update_listing_status(listing_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE listings SET status = ? WHERE id = ?", (status, listing_id))
        await db.commit()

async def delete_listing(listing_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
        await db.commit()

async def create_trade(listing_a_id, listing_b_id, channel_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO trades (listing_a_id, listing_b_id, channel_id)
            VALUES (?, ?, ?)
        """, (listing_a_id, listing_b_id, channel_id))
        await db.commit()
        return cursor.lastrowid

async def get_trade_by_channel(channel_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM trades WHERE channel_id = ?", (channel_id,)) as cursor:
            return await cursor.fetchone()

async def close_trade(trade_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE trades SET status = 'CLOSED' WHERE id = ?", (trade_id,))
        await db.commit()

async def update_trade_channel(trade_id, channel_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE trades SET channel_id = ? WHERE id = ?", (channel_id, trade_id))
        await db.commit()

async def get_expired_trades(days=7):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM trades WHERE status = 'OPEN' AND created_at < datetime('now', '-' || ? || ' days')"
        async with db.execute(sql, (days,)) as cursor:
            return await cursor.fetchall()

async def find_candidates(listing_type, pokemon_id, is_shiny, is_purified, exclude_user_id):
    """
    Finds all ACTIVE listings that match the criteria, sorted by oldest first.
    listing_type: The type we are LOOKING for (e.g. if we have HAVE, we look for WANT).
    """
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = """
            SELECT * FROM listings
            WHERE listing_type = ?
            AND pokemon_id = ?
            AND is_shiny = ?
            AND is_purified = ?
            AND user_id != ?
            AND status = 'ACTIVE'
            ORDER BY created_at ASC
        """
        async with db.execute(sql, (listing_type, pokemon_id, is_shiny, is_purified, exclude_user_id)) as cursor:
            return await cursor.fetchall()

async def check_trade_history(listing_a_id, listing_b_id):
    """Checks if these two listings have already been paired."""
    async with aiosqlite.connect(DB_NAME) as db:
        sql = """
            SELECT * FROM trades
            WHERE (listing_a_id = ? AND listing_b_id = ?)
            OR (listing_a_id = ? AND listing_b_id = ?)
        """
        async with db.execute(sql, (listing_a_id, listing_b_id, listing_b_id, listing_a_id)) as cursor:
            return await cursor.fetchone()

async def upsert_user(user_id, friend_code, team, region):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (user_id, friend_code, team, region, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                friend_code=excluded.friend_code,
                team=excluded.team,
                region=excluded.region,
                updated_at=CURRENT_TIMESTAMP
        """, (user_id, friend_code, team, region))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

# For debugging/verification
if __name__ == "__main__":
    import asyncio
    try:
        os.remove(DB_NAME)
    except FileNotFoundError:
        pass
    asyncio.run(init_db())
    print("Database initialized successfully.")
