import asyncio
import datetime
import pytz
import sys
import os

# Add project root to sys.path so we can import database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import database

# Full Moon dates (YYYY, MM, DD)
MOON_DATES = [
    (2026, 3, 3),
    (2026, 4, 2),
    (2026, 5, 1),
    (2026, 5, 31),
    (2026, 6, 29),
    (2026, 7, 29),
    (2026, 8, 28),
    (2026, 9, 26),
    (2026, 10, 26),
    (2026, 11, 24),
    (2026, 12, 24),
    (2027, 1, 22),
    (2027, 2, 20),
    (2027, 3, 22),
    (2027, 4, 20),
    (2027, 5, 20),
    (2027, 6, 19),
    (2027, 7, 18),
    (2027, 8, 17),
    (2027, 9, 15),
    (2027, 10, 15),
    (2027, 11, 14),
    (2027, 12, 13),
    (2028, 1, 12),
]

TZ_PRAGUE = pytz.timezone('Europe/Prague')
EVENT_NAME = "Úplněk (Evoluce Ursaluny)"
IMAGE_URL = "https://img.pokemondb.net/sprites/home/normal/2x/ursaluna.jpg"

async def seed_moon_events():
    print(f"Seeding {len(MOON_DATES)} moon events...")

    # Initialize DB (tables creation if needed)
    await database.init_db()

    count = 0
    for year, month, day in MOON_DATES:
        # Create start datetime: 19:00 Prague time
        # Using tz.localize to correctly handle DST
        start_dt = TZ_PRAGUE.localize(datetime.datetime(year, month, day, 19, 0, 0))
        start_ts = int(start_dt.timestamp())

        # Create end datetime: 06:00 Prague time NEXT DAY
        # We add 1 day to the start date, then set time to 6am
        end_dt = start_dt + datetime.timedelta(days=1)
        end_dt = end_dt.replace(hour=6, minute=0, second=0)
        end_ts = int(end_dt.timestamp())

        # Construct unique link
        link = f"internal:moon_{year}_{month:02d}_{day:02d}"

        try:
            # We use upsert_event which returns the ID
            event_id = await database.upsert_event(
                name=EVENT_NAME,
                link=link,
                image_url=IMAGE_URL,
                start_time=start_ts,
                end_time=end_ts
            )
            print(f"Upserted event: {year}-{month:02d}-{day:02d} (ID: {event_id}) -> Start: {start_dt}, End: {end_dt}")
            count += 1
        except Exception as e:
            print(f"Failed to upsert {year}-{month:02d}-{day:02d}: {e}")

    print(f"Finished. Total events processed: {count}")

if __name__ == "__main__":
    asyncio.run(seed_moon_events())
