import unittest
from unittest.mock import MagicMock, patch
import sys
from io import BytesIO

# Mock dependencies before importing the cog
mock_discord = MagicMock()
mock_discord.app_commands = MagicMock()
mock_discord.ui = MagicMock()
sys.modules['discord'] = mock_discord
sys.modules['discord.ext'] = MagicMock()
sys.modules['discord.ext.commands'] = MagicMock()
sys.modules['database'] = MagicMock()
sys.modules['qrcode'] = MagicMock()

# Avoid the MagicMock issue by ensuring Profile doesn't inherit from a mocked Cog
import discord.ext.commands
class MockCog:
    def __init__(self, *args, **kwargs):
        pass
discord.ext.commands.Cog = MockCog

from cogs.profile import Profile

class TestProfileQR(unittest.TestCase):
    def setUp(self):
        self.bot = MagicMock()
        # Mock the tree to avoid errors when adding context menus
        self.bot.tree = MagicMock()
        self.profile_cog = Profile(self.bot)

    def test_generate_qr_sync(self):
        import qrcode
        # Mock qrcode.QRCode
        mock_qr_instance = MagicMock()
        qrcode.QRCode.return_value = mock_qr_instance

        # Mock img.save
        mock_img = MagicMock()
        mock_qr_instance.make_image.return_value = mock_img

        fc = "123456789012"
        buffer = self.profile_cog._generate_qr_sync(fc)

        self.assertIsInstance(buffer, BytesIO)
        qrcode.QRCode.assert_called_once()
        mock_qr_instance.add_data.assert_called_with(fc)
        mock_qr_instance.make.assert_called_with(fit=True)
        mock_qr_instance.make_image.assert_called_with(fill_color="black", back_color="white")
        mock_img.save.assert_called_once()

if __name__ == '__main__':
    unittest.main()
