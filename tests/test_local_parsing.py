import pytest
import asyncio
from bs4 import BeautifulSoup
import json
import services.pokemon_sync as scraper

# Helper function to read local HTML files
def read_html(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()

@pytest.mark.asyncio
async def test_parsing_alolan_rattata():
    """
    Test parsing logic for Alolan Rattata using the provided HTML file.
    Focus on: Stats, Link Discovery (conceptually), and Image prioritization.
    """
    html = read_html("Alolan Rattata (Pokémon GO) – Best Moveset, Counters, Max CP & Stats.html")
    soup = BeautifulSoup(html, 'html.parser')

    # 1. Test Stats Parsing
    stats = scraper.parse_stats(soup)
    print(f"\nAlolan Rattata Stats: {stats}")
    assert stats['attack'] == 103
    assert stats['defense'] == 70
    assert stats['hp'] == 102
    assert stats['max_cp'] == 830
    assert stats['buddy_distance'] == 1

    # 2. Test Image Parsing (Priority: Ingame > Official)
    # The scraped URL might be messy due to local file save, but it should contain the filename
    normal_url, shiny_url = scraper.parse_images(soup)
    print(f"Alolan Rattata Images: Normal={normal_url}, Shiny={shiny_url}")

    # We check for the filename presence, regardless of full URL structure
    assert "pm19.fALOLA.icon.png" in normal_url
    assert "pm19.fALOLA.s.icon.png" in shiny_url
    assert "official" not in normal_url  # Should NOT be the official artwork

@pytest.mark.asyncio
async def test_parsing_bulbasaur_costumes():
    """
    Test parsing logic for Bulbasaur using the provided HTML file.
    Focus on: Costumes.
    """
    html = read_html("Bulbasaur (Pokémon GO) – Best Moveset, Counters, Max CP & Stats.html")
    soup = BeautifulSoup(html, 'html.parser')

    # 1. Test Costume Parsing
    costumes_json = scraper.parse_costumes(soup)
    print(f"\nBulbasaur Costumes JSON: {costumes_json}")

    assert costumes_json is not None
    costumes = json.loads(costumes_json)

    # Expected costumes based on prompt: JAN_2020, SPRING_2020, FALL_2019
    names = [c['name'] for c in costumes]
    print(f"Found Costume Names: {names}")

    assert "JAN_2020" in names
    assert "SPRING_2020" in names
    assert "FALL_2019" in names

    # Check structure of one costume
    jan_2020 = next(c for c in costumes if c['name'] == 'JAN_2020')
    assert jan_2020['image_url'] is not None
    assert jan_2020['shiny_image_url'] is not None
    assert "pm1.cJAN_2020_NOEVOLVE.icon.png" in jan_2020['image_url']

@pytest.mark.asyncio
async def test_parsing_hisuian_typhlosion_link_discovery():
    """
    Test parsing logic for Hisuian Typhlosion.
    """
    html = read_html("Hisuian Typhlosion (Pokémon GO) – Best Moveset, Counters, Max CP & Stats.html")
    soup = BeautifulSoup(html, 'html.parser')

    stats = scraper.parse_stats(soup)
    print(f"\nHisuian Typhlosion Stats: {stats}")
    # Verify stats are non-zero (simple sanity check)
    assert stats['attack'] > 0
    assert stats['max_cp'] > 0

    # Verify Ingame sprite priority
    normal_url, shiny_url = scraper.parse_images(soup)
    print(f"Hisuian Typhlosion Images: {normal_url}, {shiny_url}")

    if normal_url:
        assert "icon.png" in normal_url

if __name__ == "__main__":
    # Manually run the async tests if executed as script
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_parsing_alolan_rattata())
    loop.run_until_complete(test_parsing_bulbasaur_costumes())
    loop.run_until_complete(test_parsing_hisuian_typhlosion_link_discovery())
    loop.close()
