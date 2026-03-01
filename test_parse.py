import asyncio
from bs4 import BeautifulSoup
import sys
import os

# add parent directory to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from services.pokemon_sync import parse_stats, parse_best_moveset, parse_images, parse_types

def test_file(filename):
    print(f"Testing {filename}:")
    with open(filename, 'r') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    stats = parse_stats(soup)
    moveset = parse_best_moveset(soup)
    images = parse_images(soup)
    types = parse_types(soup)

    print(f"  Stats: {stats}")
    print(f"  Moveset: {moveset}")
    print(f"  Images: {images}")
    print(f"  Types: {types}")
    print("-" * 40)

test_file('Mewtwo (Pokémon GO) – Best Moveset, Counters, Max CP & Stats.html')
test_file('Armored Mewtwo (Pokémon GO) – Best Moveset, Counters, Max CP & Stats.html')
test_file('Mega Mewtwo X (Pokémon GO) – Best Moveset, Counters, Max CP & Stats.html')
