import discord
import os
import asyncio
from discord.ext import commands
import config
import logging
import database
import services.pokemon_sync as pokemon_sync

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

        # Check if we need to sync pokemon data
        async with database.get_db() as db:
            async with db.execute("SELECT COUNT(*) as count FROM pokemon_species") as cursor:
                row = await cursor.fetchone()
                if row['count'] == 0:
                    logger.warning("Pokemon species table is empty. Please run !scrape as bot owner.")
                    # We can't easily DM the owner here because the bot isn't fully ready/connected to gateway yet.
                    # We will do it in on_ready.
                else:
                    logger.info(f"Pokemon species table has {row['count']} entries.")

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

        # Check if DB is empty and notify owner
        async with database.get_db() as db:
            async with db.execute("SELECT COUNT(*) as count FROM pokemon_species") as cursor:
                row = await cursor.fetchone()
                if row['count'] == 0:
                    try:
                        app_info = await self.application_info()
                        if app_info.owner:
                            await app_info.owner.send("⚠️ **Database Alert**: The Pokémon species table is empty. Please run `!scrape` to populate it.")
                            logger.info("Sent empty DB notification to owner.")
                    except Exception as e:
                        logger.error(f"Failed to send owner notification: {e}")

bot = TradeBot()

if __name__ == '__main__':
    if not config.TOKEN:
        logger.error("No token found. Please check your .env file.")
    else:
        bot.run(config.TOKEN)
