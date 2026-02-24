import discord
import os
import asyncio
from discord.ext import commands
import config
import logging
import database

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

intents = discord.Intents.default()
intents.message_content = True

class TradeBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # Initialize database
        await database.init_db()
        logger.info("Database initialized.")

        # Load extensions
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f'Loaded extension: {filename}')
                except Exception as e:
                    logger.error(f'Failed to load extension {filename}: {e}')

        # Register persistent views
        try:
            import views.trade
            self.add_view(views.trade.TradeView())
            logger.info("Registered TradeView")
        except Exception as e:
            logger.error(f"Failed to register TradeView: {e}")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')

bot = TradeBot()

if __name__ == '__main__':
    if not config.TOKEN:
        logger.error("No token found. Please check your .env file.")
    else:
        bot.run(config.TOKEN)
