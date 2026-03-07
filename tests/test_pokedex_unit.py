import sys
from unittest.mock import MagicMock

# Mock dependencies before importing the cog
mock_discord = MagicMock()
mock_database = MagicMock()

# Mocking discord.ext.commands.Cog so it doesn't return mocks when called/initialized
class MockCog:
    def __init__(self, *args, **kwargs):
        pass

mock_discord.ext.commands.Cog = MockCog

sys.modules["discord"] = mock_discord
sys.modules["discord.app_commands"] = mock_discord.app_commands
sys.modules["discord.ext"] = mock_discord.ext
sys.modules["discord.ext.commands"] = mock_discord.ext.commands
sys.modules["database"] = mock_database

# Now we can import Pokedex
from cogs.pokedex import Pokedex
import unittest

class TestPokedexColors(unittest.TestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.cog = Pokedex(self.bot)

    def test_get_color_by_type_valid(self):
        """Test that valid Pokemon types return the correct hex color codes."""
        test_cases = [
            ("Normal", 0xA8A77A),
            ("Fire", 0xEE8130),
            ("Water", 0x6390F0),
            ("Electric", 0xF7D02C),
            ("Grass", 0x7AC74C),
            ("Ice", 0x96D9D6),
            ("Fighting", 0xC22E28),
            ("Poison", 0xA33EA1),
            ("Ground", 0xE2BF65),
            ("Flying", 0xA98FF3),
            ("Psychic", 0xF95587),
            ("Bug", 0xA6B91A),
            ("Rock", 0xB6A136),
            ("Ghost", 0x735797),
            ("Dragon", 0x6F35FC),
            ("Steel", 0xB7B7CE),
            ("Fairy", 0xD685AD),
        ]
        for pokemon_type, expected_color in test_cases:
            with self.subTest(pokemon_type=pokemon_type):
                self.assertEqual(self.cog._get_color_by_type(pokemon_type), expected_color)

    def test_get_color_by_type_invalid(self):
        """Test that unknown or None types return the default white color (0xFFFFFF)."""
        self.assertEqual(self.cog._get_color_by_type("Unknown"), 0xFFFFFF)
        self.assertEqual(self.cog._get_color_by_type(None), 0xFFFFFF)
        self.assertEqual(self.cog._get_color_by_type(""), 0xFFFFFF)

    def test_get_color_by_type_case_sensitivity(self):
        """Test that the mapping is case-sensitive as currently implemented."""
        # "Fire" is valid, "fire" is not in the dictionary
        self.assertEqual(self.cog._get_color_by_type("Fire"), 0xEE8130)
        self.assertEqual(self.cog._get_color_by_type("fire"), 0xFFFFFF)

if __name__ == "__main__":
    unittest.main()
