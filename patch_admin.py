import re

with open("cogs/admin.py", "r") as f:
    content = f.read()

# Replace the !updatebot command
new_updatebot = """    @commands.command()
    async def updatebot(self, ctx):
        \"\"\"Updates the bot from the repository.\"\"\"
        # Check if user is owner
        is_owner = await self.bot.is_owner(ctx.author)
        if not is_owner:
            # Fallback: check application info directly
            app_info = await self.bot.application_info()
            if ctx.author.id != app_info.owner.id:
                return await ctx.send("You do not have permission to use this command.")

        msg = await ctx.send("Starting update process...")
        logger.info("Starting bot update...")

        db_file = database.DB_NAME
        backup_file = f"{db_file}.bak"
        owner = None

        try:
            # 1. Send backup to owner
            app_info = await self.bot.application_info()
            owner = app_info.owner

            if os.path.exists(db_file):
                try:
                    await owner.send(
                        content="Automatic backup before updatebot.",
                        file=discord.File(db_file)
                    )
                    await msg.edit(content="Backup sent to owner's DM. Creating local backup...")
                    logger.info(f"Pre-update database backup sent to {owner}.")
                except discord.Forbidden:
                    await msg.edit(content="Could not send DM to owner for backup, but continuing update...")
                    logger.error("Could not send DM to owner for pre-update backup.")

                # 2. Create local backup for rollback
                import shutil
                shutil.copy2(db_file, backup_file)
                logger.info(f"Local backup created at {backup_file}")
            else:
                await msg.edit(content="No database file found to backup. Continuing update...")

            # 3. git pull
            await msg.edit(content="Updating bot from repository...")
            process = await asyncio.create_subprocess_shell(
                "git pull",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Git pull failed: {stderr.decode()}")
                return await msg.edit(content=f"Git pull failed:\\n```{stderr.decode()}```")

            logger.info(f"Git pull successful: {stdout.decode()}")
            await msg.edit(content=f"Git pull successful. Installing dependencies...")

            # 4. pip install
            process = await asyncio.create_subprocess_shell(
                f'"{sys.executable}" -m pip install -r requirements.txt',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Dependency install failed: {stderr.decode()}")
                return await msg.edit(content=f"Dependency install failed:\\n```{stderr.decode()}```")

            logger.info("Dependencies installed. Restarting...")
            await msg.edit(content="Update complete. Restarting...")

            # 5. Restart
            os.execv(sys.executable, ['python'] + sys.argv)

        except Exception as e:
            logger.error(f"Update failed: {e}")
            await msg.edit(content=f"An error occurred: {e}")"""

# find updatebot implementation
updatebot_pattern = r"    @commands\.command\(\)\n    async def updatebot\(self, ctx\):.*?except Exception as e:\n            logger\.error\(f\"Update failed: \{e\}\"\)\n            await msg\.edit\(content=f\"An error occurred: \{e\}\"\)"
content = re.sub(updatebot_pattern, new_updatebot, content, flags=re.DOTALL)

with open("cogs/admin.py", "w") as f:
    f.write(content)
