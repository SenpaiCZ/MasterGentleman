import discord
from discord.ext import commands, tasks
from discord import app_commands
import database
import logging
import datetime
import re

logger = logging.getLogger('discord')

class AutoDelete(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.autodelete_task.start()

    def cog_unload(self):
        self.autodelete_task.cancel()

    def parse_duration(self, s: str) -> int:
        """Parses duration string like '1h 30m' into minutes."""
        if not s: return 0
        s = s.lower().replace(" ", "")

        # Simple regex or manual parsing
        # Support d, h, m
        total_minutes = 0

        # Find all pairs of number+unit
        pairs = re.findall(r"(\d+)([dhm])", s)

        if not pairs and s.isdigit():
            # Assume minutes if just number? Or return 0?
            return int(s)

        for val, unit in pairs:
            val = int(val)
            if unit == 'd': total_minutes += val * 24 * 60
            elif unit == 'h': total_minutes += val * 60
            elif unit == 'm': total_minutes += val

        return total_minutes

    @app_commands.command(name="autodelete", description="Nastavit automatické mazání starých zpráv")
    @app_commands.describe(
        channel="Kanál, kde se mají mazat zprávy",
        cas="Přednastavený čas (nebo zvolte 'Custom' a vyplňte 'vlastni_cas')",
        vlastni_cas="Vlastní čas (např. '90m', '1h 30m') - použijte pokud jste vybrali 'Custom'"
    )
    @app_commands.choices(cas=[
        app_commands.Choice(name="5 minut", value="5m"),
        app_commands.Choice(name="10 minut", value="10m"),
        app_commands.Choice(name="30 minut", value="30m"),
        app_commands.Choice(name="1 hodina", value="1h"),
        app_commands.Choice(name="6 hodin", value="6h"),
        app_commands.Choice(name="12 hodin", value="12h"),
        app_commands.Choice(name="1 den", value="1d"),
        app_commands.Choice(name="7 dní", value="7d"),
        app_commands.Choice(name="Custom (Vlastní)", value="custom"),
        app_commands.Choice(name="Vypnout (Off)", value="off")
    ])
    @commands.has_permissions(administrator=True)
    async def autodelete(self, interaction: discord.Interaction, channel: discord.TextChannel, cas: str, vlastni_cas: str = None):
        """Nastaví autodelete pro daný kanál."""

        if cas == "off":
            await database.delete_autodelete_config(channel.id)
            await interaction.response.send_message(f"✅ Automatické mazání pro kanál {channel.mention} bylo vypnuto.", ephemeral=True)
            logger.info(f"User {interaction.user.id} disabled autodelete for channel {channel.id}")
            return

        time_str = cas
        if cas == "custom":
            if not vlastni_cas:
                await interaction.response.send_message("❌ Zvolili jste 'Custom', ale nevyplnili jste 'vlastni_cas'.", ephemeral=True)
                return
            time_str = vlastni_cas

        minutes = self.parse_duration(time_str)
        if minutes <= 0:
            await interaction.response.send_message(f"❌ Neplatný formát času: '{time_str}'. Použijte např. '1h 30m', '5m', '2d'.", ephemeral=True)
            return

        # Minimum safe limit? e.g. 1 minute
        if minutes < 1:
            await interaction.response.send_message("❌ Minimální čas je 1 minuta.", ephemeral=True)
            return

        await database.set_autodelete_config(channel.id, interaction.guild_id, minutes)

        duration_desc = f"{minutes} minut"
        if minutes >= 60:
            h = minutes // 60
            m = minutes % 60
            duration_desc = f"{h}h {m}m" if m > 0 else f"{h}h"

        await interaction.response.send_message(f"✅ Automatické mazání pro kanál {channel.mention} nastaveno na zprávy starší než **{duration_desc}**.", ephemeral=True)
        logger.info(f"User {interaction.user.id} set autodelete for channel {channel.id} to {minutes}m")

    @tasks.loop(minutes=5)
    async def autodelete_task(self):
        configs = await database.get_autodelete_configs()
        if not configs:
            return

        for config in configs:
            try:
                channel_id = config['channel_id']
                duration = config['duration_minutes']

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    # Maybe fetch? But task runs often, fetching might be rate limit risky if deleted.
                    # Just skip if not in cache or try fetch once.
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except:
                        # Channel deleted or no access
                        # Optionally delete config?
                        continue

                if not isinstance(channel, discord.TextChannel):
                    continue

                # Calculate cutoff time (UTC)
                cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=duration)

                # Purge
                # Limit is important. If many messages, we delete in batches.
                deleted = await channel.purge(limit=100, before=cutoff, reason="AutoDelete Task")

                if len(deleted) > 0:
                    logger.info(f"AutoDelete: Deleted {len(deleted)} messages in channel {channel.name} ({channel.id})")

            except Exception as e:
                logger.error(f"Error in autodelete task for channel {config['channel_id']}: {e}")

    @autodelete_task.before_loop
    async def before_autodelete_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(AutoDelete(bot))
