import pytest
import pytest_asyncio
import aiosqlite
import os
import time
from database import init_db, upsert_event, get_upcoming_events, get_events_for_notification, mark_event_notified, set_event_config, get_event_config, DB_NAME

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
    await set_event_config(123, channel_id=456)
    config = await get_event_config(123)
    assert config['channel_id'] == 456
    assert config['role_id'] is None

    await set_event_config(123, role_id=789)
    config = await get_event_config(123)
    assert config['channel_id'] == 456
    assert config['role_id'] == 789
