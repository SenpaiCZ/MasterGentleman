import pytest
import pytest_asyncio
import aiosqlite
import os
import time
from database import init_db, upsert_event, get_upcoming_events, get_events_for_notification, mark_event_notified, set_guild_config, get_guild_config, delete_obsolete_events, DB_NAME

@pytest_asyncio.fixture
async def setup_db():
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
    await init_db()
    yield
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)

@pytest.mark.asyncio
async def test_upsert_event(setup_db):
    event_id = await upsert_event(
        name="Test Event",
        link="http://example.com/event1",
        image_url="http://example.com/img1.jpg",
        start_time=1000,
        end_time=2000
    )
    assert event_id is not None

    # Update same event (same link)
    event_id_2 = await upsert_event(
        name="Test Event Updated",
        link="http://example.com/event1",
        image_url="http://example.com/img2.jpg",
        start_time=1000,
        end_time=3000
    )
    assert event_id == event_id_2

    events = await get_upcoming_events(0)
    assert len(events) == 1
    assert events[0]['name'] == "Test Event Updated"
    assert events[0]['end_time'] == 3000

@pytest.mark.asyncio
async def test_notifications(setup_db):
    await upsert_event("Event 1", "link1", "img1", 1000, 2000)
    await upsert_event("Event 2", "link2", "img2", 5000, 6000)

    # Get events starting between 0 and 2000
    events = await get_events_for_notification(0, 2000, '2h')
    assert len(events) == 1
    assert events[0]['name'] == "Event 1"

    # Mark as notified
    await mark_event_notified(events[0]['id'], '2h')

    # Check again
    events = await get_events_for_notification(0, 2000, '2h')
    assert len(events) == 0

    # Check 5m notification (still pending)
    events = await get_events_for_notification(0, 2000, '5m')
    assert len(events) == 1

@pytest.mark.asyncio
async def test_config(setup_db):
    await set_guild_config(123, event_channel_id=456)
    config = await get_guild_config(123)
    assert config['event_channel_id'] == 456
    assert config['event_role_id'] is None

    await set_guild_config(123, event_role_id=789)
    config = await get_guild_config(123)
    assert config['event_channel_id'] == 456
    assert config['event_role_id'] == 789

@pytest.mark.asyncio
async def test_delete_obsolete_events(setup_db):
    # 1. Setup events
    # Normal event 1
    await upsert_event("Event 1", "link1", "img1", 1000, 2000)
    # Normal event 2
    await upsert_event("Event 2", "link2", "img2", 1500, 2500)
    # Obsolete event
    await upsert_event("Obsolete Event", "obsolete_link", "img3", 2000, 3000)
    # Internal event
    await upsert_event("Internal Event", "internal:some_id", "img4", 2500, 3500)

    # 2. Test empty active_links (protection)
    deleted_count = await delete_obsolete_events([])
    assert deleted_count == 0
    events = await get_upcoming_events(0)
    assert len(events) == 4

    # 3. Test deletion of obsolete events while keeping internal ones
    active_links = ["link1", "link2"]
    deleted_count = await delete_obsolete_events(active_links)

    # "obsolete_link" should be deleted.
    # "internal:some_id" should NOT be deleted even though it's not in active_links.
    # "link1" and "link2" should be kept.
    assert deleted_count == 1

    events = await get_upcoming_events(0)
    assert len(events) == 3
    links = [e['link'] for e in events]
    assert "link1" in links
    assert "link2" in links
    assert "internal:some_id" in links
    assert "obsolete_link" not in links

    # 4. Test when all events are active
    active_links_all = ["link1", "link2"] # internal event is kept by logic, not by being in this list
    deleted_count = await delete_obsolete_events(active_links_all)
    assert deleted_count == 0
    events = await get_upcoming_events(0)
    assert len(events) == 3
