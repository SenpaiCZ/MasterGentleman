from discord.ext import commands
import discord
import os
import sys
import logging
import asyncio
import database

logger = logging.getLogger('discord')

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx, option: str = None):
        """
        Syncs the slash commands.
        Usage:
        !sync             - Syncs to current guild and clears global commands.
        !sync global      - Syncs globally.
        !sync clear       - Clears ALL commands (global and guild).
        !sync clearguild  - Clears GUILD commands.
        """
        logger.info(f"Sync command called with option: {option}")
        try:
            if option == "clear":
                # Clear global and guild commands
                self.bot.tree.clear_commands(guild=None)
                await self.bot.tree.sync()
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send("Cleared global and guild commands.")
                logger.info("Cleared global and guild commands.")

            elif option == "clearguild":
                # Clear guild commands
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send("Cleared guild commands.")
                logger.info("Cleared guild commands.")

            elif option == "global":
                # Sync global commands
                synced = await self.bot.tree.sync()
                await ctx.send(f"Synced {len(synced)} global command(s).")
                logger.info(f"Synced {len(synced)} global commands.")

            else:
                # Default: Sync to current guild and clear global

                # 1. Clear current guild commands to ensure fresh start
                self.bot.tree.clear_commands(guild=ctx.guild)

                # 2. Copy global commands to guild
                self.bot.tree.copy_global_to(guild=ctx.guild)

                # 3. Sync to Guild
                synced_guild = await self.bot.tree.sync(guild=ctx.guild)

                # 4. Clear Global (but preserve in tree for future use)
                # Snapshot current global commands
                global_cmds = [c for c in self.bot.tree.get_commands(guild=None)]

                # Clear and Sync (removes from Discord)
                self.bot.tree.clear_commands(guild=None)
                await self.bot.tree.sync()

                # Restore to tree
                for cmd in global_cmds:
                    self.bot.tree.add_command(cmd)

                await ctx.send(f"Synced {len(synced_guild)} commands to guild. Global commands cleared from Discord.")
                logger.info(f"Synced {len(synced_guild)} commands to guild {ctx.guild.name}. Global commands cleared.")

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

    @commands.command()
    async def backup(self, ctx):
        """Sends a backup of the database to the bot owner."""
        # Check if user is owner
        is_owner = await self.bot.is_owner(ctx.author)
        if not is_owner:
            # Fallback: check application info directly
            app_info = await self.bot.application_info()
            if ctx.author.id != app_info.owner.id:
                return await ctx.send("You do not have permission to use this command.")

        try:
            db_file = database.DB_NAME
            if not os.path.exists(db_file):
                return await ctx.send("Database file not found.")

            app_info = await self.bot.application_info()
            owner = app_info.owner

            await owner.send(
                content="Here is the database backup.",
                file=discord.File(db_file)
            )
            await ctx.send("Backup sent to owner's DM.")
            logger.info(f"Database backup sent to {owner}.")

        except discord.Forbidden:
            await ctx.send("Could not send DM to owner. Please check privacy settings.")
            logger.error("Could not send DM to owner.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
            logger.error(f"Backup failed: {e}")

async def setup(bot):
    await bot.add_cog(Admin(bot))
