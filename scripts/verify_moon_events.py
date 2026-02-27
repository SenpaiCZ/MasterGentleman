import asyncio
import sys
import os
import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import database

async def verify_moon_events():
    print("Verifying moon events in database...")

    # Initialize DB connection
    await database.init_db()

    # Query for moon events
    # We look for events with the specific name
    async with database.get_db() as db:
        async with db.execute("SELECT * FROM events WHERE name = ? ORDER BY start_time ASC", ("Úplněk (Evoluce Ursaluny)",)) as cursor:
            events = await cursor.fetchall()

    print(f"Found {len(events)} moon events.")

    for event in events:
        start_dt = datetime.datetime.fromtimestamp(event['start_time'])
        end_dt = datetime.datetime.fromtimestamp(event['end_time'])
        print(f"ID: {event['id']} | Name: {event['name']} | Start: {start_dt} | End: {end_dt} | Link: {event['link']}")

    if len(events) == 24:
        print("✅ SUCCESS: All 24 events found.")
    else:
        print(f"❌ FAILURE: Expected 24 events, found {len(events)}.")

if __name__ == "__main__":
    asyncio.run(verify_moon_events())
