import aiosqlite
import os
import logging
import asyncio

logger = logging.getLogger('discord')

DB_NAME = "trade_bot.db"

def dict_factory(cursor, row):
    """
    Factory to return dictionary instead of sqlite3.Row or tuple.
    """
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db():
    """Returns an aiosqlite connection context manager."""
    # We return the connect() context manager directly.
    # The caller uses: async with get_db() as db:
    # Inside the block, we can't easily enforce PRAGMA unless we wrap it.
    # So let's wrap it in an async context manager.
    return DBContext()

class DBContext:
    def __init__(self):
        self.db = None

    async def __aenter__(self):
        self.db = await aiosqlite.connect(DB_NAME)
        self.db.row_factory = dict_factory
        await self.db.execute("PRAGMA foreign_keys = ON")
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        if self.db:
            await self.db.close()

async def init_db():
    try:
        async with get_db() as db:
            # We explicitly DROP listings/pokemon_species if they exist to force schema update as requested
            # CAUTION: This wipes data. User approved "Reset Database".

            # Since we are re-defining schema, let's just drop everything to be safe and clean.
            tables = ['trades', 'listings', 'pokemon_species', 'users', 'events', 'guild_config', 'autodelete_config', 'user_departures']
            for table in tables:
                await db.execute(f"DROP TABLE IF EXISTS {table}")

            # 1. Users
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

            # 2. Pokemon Species (New Table)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pokemon_species (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pokedex_num INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    form TEXT DEFAULT 'Normal',
                    type1 TEXT,
                    type2 TEXT,
                    image_url TEXT,
                    can_dynamax BOOLEAN DEFAULT 0,
                    can_gigantamax BOOLEAN DEFAULT 0,
                    can_mega BOOLEAN DEFAULT 0,
                    is_legendary BOOLEAN DEFAULT 0,
                    is_mythical BOOLEAN DEFAULT 0,
                    UNIQUE(pokedex_num, form)
                )
            """)

            # 3. Listings
            # Changed pokemon_id (int) to species_id (FK)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    account_id INTEGER NOT NULL,
                    listing_type TEXT NOT NULL CHECK(listing_type IN ('HAVE', 'WANT')),
                    species_id INTEGER NOT NULL,
                    is_shiny BOOLEAN DEFAULT 0,
                    is_purified BOOLEAN DEFAULT 0,
                    is_dynamax BOOLEAN DEFAULT 0,
                    is_gigantamax BOOLEAN DEFAULT 0,
                    is_background BOOLEAN DEFAULT 0,
                    is_adventure_effect BOOLEAN DEFAULT 0,
                    is_mirror BOOLEAN DEFAULT 0,
                    details TEXT,
                    status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'PENDING', 'COMPLETED', 'CANCELLED')),
                    message_id INTEGER,
                    channel_id INTEGER,
                    guild_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (species_id) REFERENCES pokemon_species (id) ON DELETE RESTRICT
                )
            """)

            # 4. Trades
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER,
                    listing_a_id INTEGER NOT NULL,
                    listing_b_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'CLOSED')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (listing_a_id) REFERENCES listings (id) ON DELETE CASCADE,
                    FOREIGN KEY (listing_b_id) REFERENCES listings (id) ON DELETE CASCADE
                )
            """)

            # 5. Events
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
            await db.execute("CREATE INDEX IF NOT EXISTS idx_start_time ON events (start_time)")

            # 6. Guild Config
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id INTEGER PRIMARY KEY,
                    event_channel_id INTEGER,
                    event_role_id INTEGER,
                    have_channel_id INTEGER,
                    want_channel_id INTEGER,
                    trade_category_id INTEGER
                )
            """)

            # 7. Autodelete Config
            await db.execute("""
                CREATE TABLE IF NOT EXISTS autodelete_config (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    duration_minutes INTEGER
                )
            """)

            # 8. User Departures
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_departures (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    departed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.commit()
            logger.info("Database initialized successfully with new schema.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

# --- User Accounts ---

async def add_user_account(user_id, friend_code, team, region, account_name="Main", is_main=False):
    async with get_db() as db:
        # Check if first account
        async with db.execute("SELECT COUNT(*) as count FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row['count'] == 0:
                is_main = True

        await db.execute("""
            INSERT INTO users (user_id, friend_code, team, region, account_name, is_main, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, friend_code, team, region, account_name, is_main))
        await db.commit()

async def update_user_account(account_id, **kwargs):
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

    async with get_db() as db:
        await db.execute(query, tuple(params))
        await db.commit()
    return True

async def get_user_accounts(user_id):
    async with get_db() as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ? ORDER BY is_main DESC, id ASC", (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_account(account_id):
    async with get_db() as db:
        async with db.execute("SELECT * FROM users WHERE id = ?", (account_id,)) as cursor:
            return await cursor.fetchone()

# --- Pokemon Species ---

async def upsert_pokemon_species(pokedex_num, name, form, type1, type2=None, image_url=None,
                                 can_dynamax=False, can_gigantamax=False, can_mega=False):
    """Inserts or updates a pokemon species."""
    async with get_db() as db:
        # Check if exists
        async with db.execute("SELECT id FROM pokemon_species WHERE pokedex_num = ? AND form = ?", (pokedex_num, form)) as cursor:
            row = await cursor.fetchone()

        if row:
            # Update
            await db.execute("""
                UPDATE pokemon_species
                SET name=?, type1=?, type2=?, image_url=?, can_dynamax=?, can_gigantamax=?, can_mega=?
                WHERE id=?
            """, (name, type1, type2, image_url, can_dynamax, can_gigantamax, can_mega, row['id']))
            await db.commit()
            return row['id']
        else:
            # Insert
            cursor = await db.execute("""
                INSERT INTO pokemon_species (pokedex_num, name, form, type1, type2, image_url, can_dynamax, can_gigantamax, can_mega)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pokedex_num, name, form, type1, type2, image_url, can_dynamax, can_gigantamax, can_mega))
            await db.commit()
            return cursor.lastrowid

async def get_pokemon_species_by_name(name):
    """
    Finds a species by name.
    Note: 'name' here might be just the species name (e.g. 'Bulbasaur') or name+form.
    For autocomplete purposes, we might need a LIKE query.
    """
    async with get_db() as db:
        # Exact match first
        async with db.execute("SELECT * FROM pokemon_species WHERE name = ? COLLATE NOCASE", (name,)) as cursor:
            row = await cursor.fetchone()
            if row: return row

        # Try finding by name where form is 'Normal'
        async with db.execute("SELECT * FROM pokemon_species WHERE name = ? COLLATE NOCASE AND form = 'Normal'", (name,)) as cursor:
            return await cursor.fetchone()

async def search_pokemon_species(query, limit=25):
    """Search for autocomplete."""
    async with get_db() as db:
        # Search by name or form
        sql = """
            SELECT * FROM pokemon_species
            WHERE name LIKE ? OR (name || ' ' || form) LIKE ?
            LIMIT ?
        """
        like_query = f"{query}%"
        async with db.execute(sql, (like_query, like_query, limit)) as cursor:
            return await cursor.fetchall()

# --- Listings ---

async def add_listing(user_id, account_id, listing_type, species_id,
                     is_shiny=False, is_purified=False,
                     is_dynamax=False, is_gigantamax=False,
                     is_background=False, is_adventure_effect=False,
                     is_mirror=False,
                     details=None,
                     guild_id=None):
    async with get_db() as db:
        cursor = await db.execute("""
            INSERT INTO listings (
                user_id, account_id, listing_type, species_id,
                is_shiny, is_purified, is_dynamax, is_gigantamax,
                is_background, is_adventure_effect, is_mirror, details,
                guild_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, account_id, listing_type, species_id,
            is_shiny, is_purified, is_dynamax, is_gigantamax,
            is_background, is_adventure_effect, is_mirror, details,
            guild_id
        ))
        await db.commit()
        return cursor.lastrowid

async def update_listing_message(listing_id, message_id, channel_id):
    async with get_db() as db:
        await db.execute("UPDATE listings SET message_id = ?, channel_id = ? WHERE id = ?", (message_id, channel_id, listing_id))
        await db.commit()

async def update_listing_details(listing_id, details):
    async with get_db() as db:
        await db.execute("UPDATE listings SET details = ? WHERE id = ?", (details, listing_id))
        await db.commit()

async def get_listing(listing_id):
    async with get_db() as db:
        # Join users and pokemon_species
        sql = """
            SELECT l.*,
                   u.friend_code, u.account_name, u.team, u.region,
                   p.name as pokemon_name, p.form as pokemon_form, p.pokedex_num as pokemon_id, p.image_url
            FROM listings l
            JOIN users u ON l.account_id = u.id
            JOIN pokemon_species p ON l.species_id = p.id
            WHERE l.id = ?
        """
        async with db.execute(sql, (listing_id,)) as cursor:
            return await cursor.fetchone()

async def get_user_listings(user_id, status='ACTIVE'):
    async with get_db() as db:
        sql = """
            SELECT l.*, u.account_name,
                   p.name as pokemon_name, p.form as pokemon_form, p.pokedex_num as pokemon_id, p.image_url
            FROM listings l
            JOIN users u ON l.account_id = u.id
            JOIN pokemon_species p ON l.species_id = p.id
            WHERE l.user_id = ? AND l.status = ?
            ORDER BY l.created_at DESC, l.id DESC
        """
        async with db.execute(sql, (user_id, status)) as cursor:
            return await cursor.fetchall()

async def get_account_listings(account_id, status='ACTIVE'):
    async with get_db() as db:
        sql = """
            SELECT l.*, u.account_name,
                   p.name as pokemon_name, p.form as pokemon_form, p.pokedex_num as pokemon_id, p.image_url
            FROM listings l
            JOIN users u ON l.account_id = u.id
            JOIN pokemon_species p ON l.species_id = p.id
            WHERE l.account_id = ? AND l.status = ?
            ORDER BY l.created_at DESC, l.id DESC
        """
        async with db.execute(sql, (account_id, status)) as cursor:
            return await cursor.fetchall()

async def update_listing_status(listing_id, status):
    async with get_db() as db:
        await db.execute("UPDATE listings SET status = ? WHERE id = ?", (status, listing_id))
        await db.commit()

async def delete_listing(listing_id):
    async with get_db() as db:
        await db.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
        await db.commit()

# --- Trades ---

async def create_trade(listing_a_id, listing_b_id, channel_id):
    async with get_db() as db:
        cursor = await db.execute("""
            INSERT INTO trades (listing_a_id, listing_b_id, channel_id)
            VALUES (?, ?, ?)
        """, (listing_a_id, listing_b_id, channel_id))
        await db.commit()
        return cursor.lastrowid

async def get_trade_by_channel(channel_id):
    async with get_db() as db:
        async with db.execute("SELECT * FROM trades WHERE channel_id = ?", (channel_id,)) as cursor:
            return await cursor.fetchone()

async def close_trade(trade_id):
    async with get_db() as db:
        await db.execute("UPDATE trades SET status = 'CLOSED' WHERE id = ?", (trade_id,))
        await db.commit()

async def update_trade_channel(trade_id, channel_id):
    async with get_db() as db:
        await db.execute("UPDATE trades SET channel_id = ? WHERE id = ?", (channel_id, trade_id))
        await db.commit()

async def get_expired_trades(days=7):
    async with get_db() as db:
        sql = "SELECT * FROM trades WHERE status = 'OPEN' AND created_at < datetime('now', '-' || ? || ' days')"
        async with db.execute(sql, (days,)) as cursor:
            return await cursor.fetchall()

async def check_trade_history(listing_a_id, listing_b_id):
    async with get_db() as db:
        sql = """
            SELECT * FROM trades
            WHERE (listing_a_id = ? AND listing_b_id = ?)
            OR (listing_a_id = ? AND listing_b_id = ?)
        """
        async with db.execute(sql, (listing_a_id, listing_b_id, listing_b_id, listing_a_id)) as cursor:
            return await cursor.fetchone()

async def find_candidates(listing_type, species_id,
                          is_shiny, is_purified,
                          is_dynamax, is_gigantamax,
                          is_background, is_adventure_effect,
                          is_mirror,
                          exclude_user_id):
    """
    Finds all ACTIVE listings that match the criteria.
    Now uses species_id.
    """
    async with get_db() as db:
        sql = """
            SELECT l.*, u.friend_code, u.account_name,
                   p.name as pokemon_name, p.form as pokemon_form, p.pokedex_num as pokemon_id
            FROM listings l
            JOIN users u ON l.account_id = u.id
            JOIN pokemon_species p ON l.species_id = p.id
            WHERE l.listing_type = ?
            AND l.species_id = ?
            AND l.is_shiny = ?
            AND l.is_purified = ?
            AND l.is_dynamax = ?
            AND l.is_gigantamax = ?
            AND l.is_background = ?
            AND l.is_adventure_effect = ?
            AND l.is_mirror = ?
            AND l.user_id != ?
            AND l.status = 'ACTIVE'
            ORDER BY l.created_at ASC
        """
        async with db.execute(sql, (
            listing_type, species_id,
            is_shiny, is_purified,
            is_dynamax, is_gigantamax,
            is_background, is_adventure_effect,
            is_mirror,
            exclude_user_id
        )) as cursor:
            return await cursor.fetchall()

# --- Events ---

async def upsert_event(name, link, image_url, start_time, end_time):
    async with get_db() as db:
        async with db.execute("SELECT id FROM events WHERE link = ?", (link,)) as cursor:
            row = await cursor.fetchone()
            if row:
                await db.execute("""
                    UPDATE events
                    SET name = ?, image_url = ?, start_time = ?, end_time = ?
                    WHERE id = ?
                """, (name, image_url, start_time, end_time, row['id']))
                await db.commit()
                return row['id']
            else:
                cursor = await db.execute("""
                    INSERT INTO events (name, link, image_url, start_time, end_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, link, image_url, start_time, end_time))
                await db.commit()
                return cursor.lastrowid

async def get_upcoming_events(from_time, to_time=None):
    async with get_db() as db:
        sql = "SELECT * FROM events WHERE start_time >= ?"
        params = [from_time]
        if to_time:
            sql += " AND start_time <= ?"
            params.append(to_time)
        sql += " ORDER BY start_time ASC"
        async with db.execute(sql, tuple(params)) as cursor:
            return await cursor.fetchall()

async def get_events_for_notification(threshold_start, threshold_end, notification_type):
    async with get_db() as db:
        col_name = f"notified_{notification_type}"
        sql = f"SELECT * FROM events WHERE start_time BETWEEN ? AND ? AND {col_name} = 0"
        async with db.execute(sql, (threshold_start, threshold_end)) as cursor:
            return await cursor.fetchall()

async def mark_event_notified(event_id, notification_type):
    async with get_db() as db:
        col_name = f"notified_{notification_type}"
        await db.execute(f"UPDATE events SET {col_name} = 1 WHERE id = ?", (event_id,))
        await db.commit()

# --- Configs ---

async def set_guild_config(guild_id, **kwargs):
    allowed_fields = {'event_channel_id', 'event_role_id', 'have_channel_id', 'want_channel_id', 'trade_category_id'}
    updates = []
    params = []

    for key, value in kwargs.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            params.append(value)

    if not updates:
        return

    async with get_db() as db:
        async with db.execute("SELECT 1 FROM guild_config WHERE guild_id = ?", (guild_id,)) as cursor:
            exists = await cursor.fetchone()

        if exists:
            params.append(guild_id)
            sql = f"UPDATE guild_config SET {', '.join(updates)} WHERE guild_id = ?"
            await db.execute(sql, tuple(params))
        else:
            await db.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
            params.append(guild_id)
            sql = f"UPDATE guild_config SET {', '.join(updates)} WHERE guild_id = ?"
            await db.execute(sql, tuple(params))

        await db.commit()

async def get_guild_config(guild_id):
    async with get_db() as db:
        async with db.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchone()

async def set_autodelete_config(channel_id, guild_id, duration_minutes):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO autodelete_config (channel_id, guild_id, duration_minutes)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET duration_minutes = ?
        """, (channel_id, guild_id, duration_minutes, duration_minutes))
        await db.commit()

async def get_autodelete_configs():
    async with get_db() as db:
        async with db.execute("SELECT * FROM autodelete_config") as cursor:
            return await cursor.fetchall()

async def delete_autodelete_config(channel_id):
    async with get_db() as db:
        await db.execute("DELETE FROM autodelete_config WHERE channel_id = ?", (channel_id,))
        await db.commit()

async def add_user_departure(user_id, guild_id):
    async with get_db() as db:
        await db.execute("""
            INSERT OR REPLACE INTO user_departures (user_id, guild_id, departed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (user_id, guild_id))
        await db.commit()

async def remove_user_departure(user_id):
    async with get_db() as db:
        await db.execute("DELETE FROM user_departures WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_departed_users(hours=24):
    async with get_db() as db:
        sql = "SELECT * FROM user_departures WHERE departed_at < datetime('now', '-' || ? || ' hours')"
        async with db.execute(sql, (hours,)) as cursor:
            return await cursor.fetchall()

if __name__ == "__main__":
    asyncio.run(init_db())
