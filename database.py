import aiosqlite
import os
import logging

logger = logging.getLogger('discord')

DB_NAME = "trade_bot.db"

async def init_db():
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    friend_code TEXT NOT NULL,
                    team TEXT,
                    region TEXT,
                    account_name TEXT DEFAULT 'Main',
                    is_main BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    account_id INTEGER NOT NULL,
                    listing_type TEXT NOT NULL CHECK(listing_type IN ('HAVE', 'WANT')),
                    pokemon_id INTEGER NOT NULL,
                    is_shiny BOOLEAN DEFAULT 0,
                    is_purified BOOLEAN DEFAULT 0,
                    details TEXT,
                    status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'PENDING', 'COMPLETED', 'CANCELLED')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES users (id)
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
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    link TEXT NOT NULL,
                    image_url TEXT,
                    start_time INTEGER NOT NULL,
                    end_time INTEGER,
                    notified_2h BOOLEAN DEFAULT 0,
                    notified_5m BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(link)
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_start_time ON events (start_time)
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id INTEGER PRIMARY KEY,
                    event_channel_id INTEGER,
                    event_role_id INTEGER,
                    have_channel_id INTEGER,
                    want_channel_id INTEGER
                )
            """)

            # Migration: Check if event_config exists
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_config'") as cursor:
                if await cursor.fetchone():
                    logger.info("Migrating event_config to guild_config...")
                    await db.execute("""
                        INSERT OR IGNORE INTO guild_config (guild_id, event_channel_id, event_role_id)
                        SELECT guild_id, channel_id, role_id FROM event_config
                    """)
                    await db.execute("DROP TABLE event_config")
                    logger.info("Migration complete.")

            await db.commit()
            logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

async def add_user_account(user_id, friend_code, team, region, account_name="Main", is_main=False):
    """Adds a new account for a user."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Check if this is the first account for the user, if so, force is_main=True
        async with db.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,)) as cursor:
            count = (await cursor.fetchone())[0]
            if count == 0:
                is_main = True
                # account_name = "Main" # User should specify name now

        await db.execute("""
            INSERT INTO users (user_id, friend_code, team, region, account_name, is_main, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, friend_code, team, region, account_name, is_main))
        await db.commit()

async def update_user_account(account_id, **kwargs):
    """Updates specific fields of a user account."""
    allowed_fields = {'account_name', 'friend_code', 'team', 'region', 'is_main'}
    updates = []
    params = []

    for key, value in kwargs.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            params.append(value)

    if not updates:
        return False

    params.append(account_id)
    query = f"UPDATE users SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(query, tuple(params))
        await db.commit()
    return True

async def get_user_accounts(user_id):
    """Returns all accounts associated with a Discord user ID."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ? ORDER BY is_main DESC, id ASC", (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_account(account_id):
    """Returns a specific account by its ID."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (account_id,)) as cursor:
            return await cursor.fetchone()

async def add_listing(user_id, account_id, listing_type, pokemon_id, is_shiny=False, is_purified=False, details=None):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO listings (user_id, account_id, listing_type, pokemon_id, is_shiny, is_purified, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, account_id, listing_type, pokemon_id, is_shiny, is_purified, details))
        await db.commit()
        return cursor.lastrowid

async def get_listing(listing_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # We might want to join users to get account details
        sql = """
            SELECT l.*, u.friend_code, u.account_name, u.team, u.region
            FROM listings l
            JOIN users u ON l.account_id = u.id
            WHERE l.id = ?
        """
        async with db.execute(sql, (listing_id,)) as cursor:
            return await cursor.fetchone()

async def get_user_listings(user_id, status='ACTIVE'):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = """
            SELECT l.*, u.account_name
            FROM listings l
            JOIN users u ON l.account_id = u.id
            WHERE l.user_id = ? AND l.status = ?
            ORDER BY l.created_at DESC, l.id DESC
        """
        async with db.execute(sql, (user_id, status)) as cursor:
            return await cursor.fetchall()

async def get_account_listings(account_id, status='ACTIVE'):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = """
            SELECT l.*, u.account_name
            FROM listings l
            JOIN users u ON l.account_id = u.id
            WHERE l.account_id = ? AND l.status = ?
            ORDER BY l.created_at DESC, l.id DESC
        """
        async with db.execute(sql, (account_id, status)) as cursor:
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
    exclude_user_id: The Discord User ID to exclude (so we don't match our own alts).
    """
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = """
            SELECT l.*, u.friend_code, u.account_name
            FROM listings l
            JOIN users u ON l.account_id = u.id
            WHERE l.listing_type = ?
            AND l.pokemon_id = ?
            AND l.is_shiny = ?
            AND l.is_purified = ?
            AND l.user_id != ?
            AND l.status = 'ACTIVE'
            ORDER BY l.created_at ASC
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

async def upsert_event(name, link, image_url, start_time, end_time):
    async with aiosqlite.connect(DB_NAME) as db:
        # Check if exists
        async with db.execute("SELECT id FROM events WHERE link = ?", (link,)) as cursor:
            row = await cursor.fetchone()
            if row:
                # Update info if needed, but don't reset notified flags unless intended
                # We update start_time and end_time in case they changed
                await db.execute("""
                    UPDATE events
                    SET name = ?, image_url = ?, start_time = ?, end_time = ?
                    WHERE id = ?
                """, (name, image_url, start_time, end_time, row[0]))
                await db.commit()
                return row[0]
            else:
                cursor = await db.execute("""
                    INSERT INTO events (name, link, image_url, start_time, end_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, link, image_url, start_time, end_time))
                await db.commit()
                return cursor.lastrowid

async def get_upcoming_events(from_time, to_time=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM events WHERE start_time >= ?"
        params = [from_time]
        if to_time:
            sql += " AND start_time <= ?"
            params.append(to_time)
        sql += " ORDER BY start_time ASC"
        async with db.execute(sql, tuple(params)) as cursor:
            return await cursor.fetchall()

async def get_events_for_notification(threshold_start, threshold_end, notification_type):
    """
    Get events starting between threshold_start and threshold_end
    that haven't been notified yet for the given type.
    notification_type: '2h' or '5m'
    """
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        col_name = f"notified_{notification_type}"
        sql = f"SELECT * FROM events WHERE start_time BETWEEN ? AND ? AND {col_name} = 0"
        async with db.execute(sql, (threshold_start, threshold_end)) as cursor:
            return await cursor.fetchall()

async def mark_event_notified(event_id, notification_type):
    async with aiosqlite.connect(DB_NAME) as db:
        col_name = f"notified_{notification_type}"
        await db.execute(f"UPDATE events SET {col_name} = 1 WHERE id = ?", (event_id,))
        await db.commit()

async def set_guild_config(guild_id, **kwargs):
    allowed_fields = {'event_channel_id', 'event_role_id', 'have_channel_id', 'want_channel_id'}
    updates = []
    params = []

    for key, value in kwargs.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            params.append(value)

    if not updates:
        return

    async with aiosqlite.connect(DB_NAME) as db:
        # Upsert logic
        async with db.execute("SELECT 1 FROM guild_config WHERE guild_id = ?", (guild_id,)) as cursor:
            exists = await cursor.fetchone()

        if exists:
            params.append(guild_id)
            sql = f"UPDATE guild_config SET {', '.join(updates)} WHERE guild_id = ?"
            await db.execute(sql, tuple(params))
        else:
            # For insert, we need to handle specific columns
            # This is a bit tricky with dynamic kwargs, so we can do INSERT OR IGNORE then UPDATE
            await db.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
            params.append(guild_id)
            sql = f"UPDATE guild_config SET {', '.join(updates)} WHERE guild_id = ?"
            await db.execute(sql, tuple(params))

        await db.commit()

async def get_guild_config(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchone()

# For debugging/verification
if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    print("Database initialized successfully.")
