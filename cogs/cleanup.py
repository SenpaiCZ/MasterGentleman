import discord
from discord.ext import commands, tasks
import database
import logging

logger = logging.getLogger('discord')

class Cleanup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_trades.start()
        self.cleanup_departed_users_task.start()

    def cog_unload(self):
        self.cleanup_trades.cancel()
        self.cleanup_departed_users_task.cancel()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Records user departure."""
        await database.add_user_departure(member.id, member.guild.id)
        logger.info(f"User {member.id} left guild {member.guild.id}. Departure recorded.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Removes departure record if user returns."""
        await database.remove_user_departure(member.id)
        logger.info(f"User {member.id} joined guild {member.guild.id}. Departure record removed.")

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

    @tasks.loop(hours=1)
    async def cleanup_departed_users_task(self):
        """Cleans up listings of users who departed > 24h ago."""
        logger.info("Running departed users cleanup...")
        try:
            departed_users = await database.get_departed_users(hours=24)
            if not departed_users:
                return

            logger.info(f"Found {len(departed_users)} users who left > 24h ago.")

            for dep in departed_users:
                user_id = dep['user_id']
                guild_id = dep['guild_id']

                # Fetch all listings for this user
                listings = await database.get_user_listings(user_id)

                if listings:
                    for listing in listings:
                        should_delete = False

                        # Check Guild ID in DB (if populated)
                        if listing['guild_id'] is not None:
                            if listing['guild_id'] == guild_id:
                                should_delete = True

                        # Fallback: Check Channel Guild
                        elif listing['channel_id']:
                            try:
                                channel = self.bot.get_channel(listing['channel_id'])
                                if not channel:
                                    channel = await self.bot.fetch_channel(listing['channel_id'])

                                if channel and channel.guild.id == guild_id:
                                    should_delete = True
                            except:
                                # Can't confirm guild
                                pass

                        if should_delete:
                            try:
                                # Delete Discord Message
                                if listing['channel_id'] and listing['message_id']:
                                    try:
                                        channel = self.bot.get_channel(listing['channel_id'])
                                        if not channel:
                                            channel = await self.bot.fetch_channel(listing['channel_id'])
                                        if channel:
                                            msg = await channel.fetch_message(listing['message_id'])
                                            await msg.delete()
                                    except Exception as e:
                                        pass # Ignore errors

                                # Delete Listing from DB
                                await database.delete_listing(listing['id'])
                                logger.info(f"Deleted listing {listing['id']} for departed user {user_id}")

                            except Exception as e:
                                logger.error(f"Error deleting listing {listing['id']} for departed user {user_id}: {e}")

                # Remove from departure table
                await database.remove_user_departure(user_id)
                logger.info(f"Cleaned up for departed user {user_id}.")

        except Exception as e:
            logger.error(f"Error in cleanup_departed_users_task: {e}")

    @cleanup_trades.before_loop
    async def before_cleanup_trades(self):
        await self.bot.wait_until_ready()

    @cleanup_departed_users_task.before_loop
    async def before_cleanup_departed(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Cleanup(bot))
