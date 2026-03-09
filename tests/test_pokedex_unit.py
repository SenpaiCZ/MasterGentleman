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

class TestPokedexStatBar(unittest.TestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.cog = Pokedex(self.bot)

    def test_create_stat_bar_half(self):
        """Test a partially filled stat bar (exactly 50%)."""
        # value=5, max_val=10, length=10 -> 5 filled, 5 empty
        result = self.cog._create_stat_bar(5, max_val=10, length=10)
        self.assertEqual(result, "`█████░░░░░` 5")

    def test_create_stat_bar_full(self):
        """Test a fully filled stat bar (100%)."""
        # value=10, max_val=10, length=10 -> 10 filled, 0 empty
        result = self.cog._create_stat_bar(10, max_val=10, length=10)
        self.assertEqual(result, "`██████████` 10")

    def test_create_stat_bar_empty(self):
        """Test an empty stat bar (0%)."""
        # value=0, max_val=10, length=10 -> 0 filled, 10 empty
        result = self.cog._create_stat_bar(0, max_val=10, length=10)
        self.assertEqual(result, "`░░░░░░░░░░` 0")

    def test_create_stat_bar_overfill(self):
        """Test a stat bar where value exceeds max_val."""
        # value=15, max_val=10, length=10 -> should clamp to length 10
        result = self.cog._create_stat_bar(15, max_val=10, length=10)
        self.assertEqual(result, "`██████████` 15")

    def test_create_stat_bar_underfill(self):
        """Test a stat bar where value is less than 0."""
        # value=-5, max_val=10, length=10 -> should clamp to 0
        result = self.cog._create_stat_bar(-5, max_val=10, length=10)
        self.assertEqual(result, "`░░░░░░░░░░` -5")

    def test_create_stat_bar_custom_length(self):
        """Test a stat bar with a custom length."""
        # value=5, max_val=10, length=5 -> 2.5 filled (int=2), 3 empty
        result = self.cog._create_stat_bar(5, max_val=10, length=5)
        self.assertEqual(result, "`██░░░` 5")

    def test_create_stat_bar_zero_max_val(self):
        """Test that max_val=0 raises a ZeroDivisionError."""
        with self.assertRaises(ZeroDivisionError):
            self.cog._create_stat_bar(5, max_val=0, length=10)


if __name__ == "__main__":
    unittest.main()
