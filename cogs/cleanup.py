import discord
from discord.ext import commands, tasks
import database
import logging

logger = logging.getLogger('discord')

class Cleanup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_trades.start()

    def cog_unload(self):
        self.cleanup_trades.cancel()

    @tasks.loop(hours=24) # Run once a day
    async def cleanup_trades(self):
        logger.info("Starting trade cleanup...")
        try:
            expired = await database.get_expired_trades(days=7)
            if not expired:
                logger.info("No expired trades found.")
                return

            logger.info(f"Found {len(expired)} expired trades.")
            for trade in expired:
                try:
                    # Close trade in DB
                    await database.close_trade(trade['id'])

                    # Revert listings
                    await database.update_listing_status(trade['listing_a_id'], 'ACTIVE')
                    await database.update_listing_status(trade['listing_b_id'], 'ACTIVE')

                    # Delete channel
                    channel_id = trade['channel_id']
                    if channel_id:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.delete(reason="Trade expired (7 days)")
                            logger.info(f"Deleted expired trade channel {channel_id}")
                        else:
                            # Try to fetch if not in cache
                            try:
                                channel = await self.bot.fetch_channel(channel_id)
                                await channel.delete(reason="Trade expired (7 days)")
                                logger.info(f"Deleted expired trade channel {channel_id} (fetched)")
                            except discord.NotFound:
                                logger.warning(f"Channel {channel_id} not found for expired trade {trade['id']}")
                            except Exception as e:
                                logger.error(f"Error fetching/deleting channel {channel_id}: {e}")
                except Exception as e:
                    logger.error(f"Error cleaning up trade {trade['id']}: {e}")
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")

    @cleanup_trades.before_loop
    async def before_cleanup_trades(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Cleanup(bot))
