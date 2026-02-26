from discord.ext import commands
import os
import sys
import logging
import asyncio

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

    @commands.command()
    async def updatebot(self, ctx):
        """Updates the bot from the repository."""
        # Check if user is owner
        is_owner = await self.bot.is_owner(ctx.author)
        if not is_owner:
            # Fallback: check application info directly
            app_info = await self.bot.application_info()
            if ctx.author.id != app_info.owner.id:
                return await ctx.send("You do not have permission to use this command.")

        msg = await ctx.send("Updating bot from repository...")
        logger.info("Starting bot update...")

        try:
            # git pull
            process = await asyncio.create_subprocess_shell(
                "git pull",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Git pull failed: {stderr.decode()}")
                return await msg.edit(content=f"Git pull failed:\n```{stderr.decode()}```")

            logger.info(f"Git pull successful: {stdout.decode()}")
            await msg.edit(content=f"Git pull successful. Installing dependencies...")

            # pip install
            process = await asyncio.create_subprocess_shell(
                f'"{sys.executable}" -m pip install -r requirements.txt',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Dependency install failed: {stderr.decode()}")
                return await msg.edit(content=f"Dependency install failed:\n```{stderr.decode()}```")

            logger.info("Dependencies installed. Restarting...")
            await msg.edit(content="Update complete. Restarting...")

            # Restart
            os.execv(sys.executable, ['python'] + sys.argv)

        except Exception as e:
            logger.error(f"Update failed: {e}")
            await msg.edit(content=f"An error occurred: {e}")

async def setup(bot):
    await bot.add_cog(Admin(bot))
