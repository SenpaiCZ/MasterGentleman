import aiohttp
from bs4 import BeautifulSoup
import datetime
import pytz
import logging

logger = logging.getLogger('discord')

LEEKDUCK_URL = "https://leekduck.com/events/"
TZ_PRAGUE = pytz.timezone('Europe/Prague')

def parse_iso_time(iso_str, is_local):
    if not iso_str:
        return None

    try:
        # ISO format: YYYY-MM-DDTHH:MM:SS
        # If is_local is True, we assume it's naive and assign TZ_PRAGUE
        # If is_local is False, we parse it as is (hopefully with offset) or assume UTC?

        dt = datetime.datetime.fromisoformat(iso_str)

        if is_local:
            # It is a naive datetime representing local time
            # We treat "Local Time" as "Prague Time" for this bot
            if dt.tzinfo is None:
                dt = TZ_PRAGUE.localize(dt)
        else:
            # It should have timezone info if not local
            if dt.tzinfo is None:
                # If naive but not local, assume UTC
                dt = dt.replace(tzinfo=datetime.timezone.utc)

        return dt.timestamp()

    except ValueError:
        logger.error(f"Invalid date format: {iso_str}")
        return None

async def scrape_leekduck():
    """
    Scrapes LeekDuck events page and returns a list of event dictionaries.
    Each event dict contains:
    - name: str
    - link: str
    - image_url: str
    - start_time: int (timestamp)
    - end_time: int (timestamp) or None
    """
    logger.info("Starting LeekDuck scrape...")
    events = []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(LEEKDUCK_URL) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch LeekDuck: {response.status}")
                    return []
                html = await response.text()

        soup = BeautifulSoup(html, 'html.parser')

        # Select all event items. They seem to be inside .event-header-item-wrapper
        event_wrappers = soup.select('.event-header-item-wrapper')

        for wrapper in event_wrappers:
            try:
                # Extract data attributes
                start_iso = wrapper.get('data-event-start-date')
                # If start date is missing, try start-date-check (often used for currently running events)
                if not start_iso:
                    start_iso = wrapper.get('data-event-start-date-check')

                end_iso = wrapper.get('data-event-end-date')
                is_local = wrapper.get('data-event-local-time') == 'true'

                # Find the link element inside
                link_elem = wrapper.select_one('a.event-item-link')
                if not link_elem:
                    continue

                link_href = link_elem.get('href')
                if link_href and link_href.startswith('/'):
                    link_href = "https://leekduck.com" + link_href

                # Find name and image inside the link
                name_elem = link_elem.select_one('h2')
                name = name_elem.text.strip() if name_elem else "Unknown Event"

                img_elem = link_elem.select_one('img')
                image_url = img_elem.get('src') if img_elem else None
                if image_url and image_url.startswith('/'):
                    image_url = "https://leekduck.com" + image_url

                # Type and Time Text
                heading_span = link_elem.select_one('.event-tag-badge')
                event_type = heading_span.text.strip() if heading_span else "Event"

                time_elem = link_elem.select_one('p')
                time_text = time_elem.text.strip() if time_elem else ""

                # Parse times
                start_ts = parse_iso_time(start_iso, is_local)
                end_ts = parse_iso_time(end_iso, is_local)

                # Fix "Calculating..." time string by using Discord timestamp
                if "Calculating..." in time_text and start_ts:
                    try:
                        time_text = f"<t:{int(start_ts)}:f>"
                    except Exception as e:
                        logger.error(f"Error calculating timestamp for {name}: {e}")

                if start_ts:
                    events.append({
                        'name': name,
                        'link': link_href,
                        'image_url': image_url,
                        'start_time': int(start_ts),
                        'end_time': int(end_ts) if end_ts else None,
                        'type': event_type,
                        'time_text': time_text
                    })

            except Exception as e:
                logger.error(f"Error parsing event item: {e}")
                continue

        logger.info(f"Scraped {len(events)} events from LeekDuck.")
        return events

    except Exception as e:
        logger.error(f"Error scraping LeekDuck: {e}")
        return []
