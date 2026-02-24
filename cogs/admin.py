from discord.ext import commands
import os
import sys
import logging

logger = logging.getLogger('discord')

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx):
        """Syncs the slash commands globally."""
        logger.info("Syncing commands...")
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} command(s).")
            logger.info(f"Synced {len(synced)} commands.")
        except Exception as e:
            await ctx.send(f"Failed to sync: {e}")
            logger.error(f"Failed to sync commands: {e}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def restart(self, ctx):
        """Restarts the bot process."""
        await ctx.send("Restarting bot...")
        logger.info("Restarting bot...")
        os.execv(sys.executable, ['python'] + sys.argv)

async def setup(bot):
    await bot.add_cog(Admin(bot))
