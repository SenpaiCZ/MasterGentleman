import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import datetime
import pytz
import database
import services.scraper as scraper

logger = logging.getLogger('discord')

# Timezone for scheduling tasks and display
TZ_PRAGUE = pytz.timezone('Europe/Prague')

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scrape_task.start()
        self.notification_task.start()
        self.weekly_summary_task.start()

    def cog_unload(self):
        self.scrape_task.cancel()
        self.notification_task.cancel()
        self.weekly_summary_task.cancel()

    # --- Commands ---

    events_group = app_commands.Group(name="nastaveni_udalosti", description="Nastavení upozornění na Pokémon GO eventy")

    @events_group.command(name="kanal", description="Nastavit kanál pro upozornění")
    @app_commands.describe(channel="Textový kanál pro zprávy")
    @commands.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_event_config(interaction.guild_id, channel_id=channel.id)
        await interaction.response.send_message(f"✅ Kanál pro upozornění nastaven na: {channel.mention}", ephemeral=True)

    @events_group.command(name="role", description="Nastavit roli, která bude označena")
    @app_commands.describe(role="Role pro označení (ping)")
    @commands.has_permissions(administrator=True)
    async def set_role(self, interaction: discord.Interaction, role: discord.Role):
        await database.set_event_config(interaction.guild_id, role_id=role.id)
        await interaction.response.send_message(f"✅ Role pro označení nastavena na: {role.mention}", ephemeral=True)

    @events_group.command(name="stav", description="Zobrazit aktuální nastavení")
    @commands.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        config = await database.get_event_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message("❌ Nastavení zatím neexistuje.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(config['channel_id']) if config['channel_id'] else None
        role = interaction.guild.get_role(config['role_id']) if config['role_id'] else None

        msg = (
            f"**Nastavení Udalostí:**\n"
            f"📢 Kanál: {channel.mention if channel else 'Nenastaveno'}\n"
            f"🔔 Role: {role.mention if role else 'Nenastaveno'}"
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @events_group.command(name="scrape", description="Manuálně spustit stahování eventů (Admin)")
    @commands.has_permissions(administrator=True)
    async def manual_scrape(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self._run_scrape()
        await interaction.followup.send(f"✅ Staženo/aktualizováno {count} eventů.")

    # --- Tasks ---

    @tasks.loop(time=datetime.time(hour=3, minute=0, tzinfo=TZ_PRAGUE))
    async def scrape_task(self):
        logger.info("Running daily scrape task.")
        await self._run_scrape()

    async def _run_scrape(self):
        events = await scraper.scrape_leekduck()
        count = 0
        for e in events:
            # Upsert
            await database.upsert_event(
                e['name'], e['link'], e['image_url'], e['start_time'], e['end_time']
            )
            count += 1
        logger.info(f"Database updated with {count} events.")
        return count

    @tasks.loop(minutes=1)
    async def notification_task(self):
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

        # 2 Hours Before (range: now+2h-1m to now+2h+1m is tricky with discrete checks)
        # Better: check for events starting between [now + 1h 59m, now + 2h 00m]
        # Or simply: check events starting < now + 2h AND > now (don't notify past) AND notified=0
        # But we want to notify roughly 2h before.
        # So we query for start_time <= now + 2h AND start_time > now + 1h 50m ?
        # Actually, let's use a small window. If we run every minute, window of 2 mins is enough.
        # But if bot is down, we miss it.
        # Robust way: start_time < now + 2h AND start_time > now AND notified_2h = 0.
        # This will notify even if we are late (e.g. 1h 50m before), which is better than missing.
        # But we don't want to notify if it's 5 mins before (that's the 5m warning).
        # So for 2h warning: start_time <= now + 125 mins AND start_time > now + 30 mins.

        target_2h = now_ts + 2 * 3600 # 2 hours from now
        # Look for events that start soon (within next 2h + buffer) but haven't been notified
        # Let's say we notify if it starts within [1h 55m, 2h 05m] from now.
        # window_start = target_2h - 300
        # window_end = target_2h + 300

        # Actually, "Every event will have notification 2h before start."
        # If I use "start_time <= now + 2h", I catch it immediately when it enters the window.
        # To avoid notifying too late (e.g. restart after downtime), maybe limit the window.
        # Let's say: Notify if start_time is in [now + 90min, now + 130min].

        events_2h = await database.get_events_for_notification(now_ts + 90*60, now_ts + 130*60, '2h')
        for event in events_2h:
            await self._send_notification(event, '2h')
            await database.mark_event_notified(event['id'], '2h')

        # 5 Minutes Before
        # Window: [now + 1min, now + 10min]
        events_5m = await database.get_events_for_notification(now_ts + 1*60, now_ts + 10*60, '5m')
        for event in events_5m:
            await self._send_notification(event, '5m')
            await database.mark_event_notified(event['id'], '5m')

    async def _send_notification(self, event, notif_type):
        # We need to find which guilds to notify. Assuming single guild or iteration.
        # But `event_config` is by guild_id.
        # We don't have a list of guilds in DB, but we can iterate over bot.guilds

        for guild in self.bot.guilds:
            config = await database.get_event_config(guild.id)
            if not config or not config['channel_id']:
                continue

            channel = guild.get_channel(config['channel_id'])
            if not channel:
                continue

            role = guild.get_role(config['role_id']) if config['role_id'] else None
            role_mention = role.mention if role else ""

            # Embed
            time_str = "2 hodiny" if notif_type == '2h' else "5 minut"
            title_prefix = "⏰ Začíná za"

            # Format start time
            # Convert timestamp to DT with Prague TZ
            dt_start = datetime.datetime.fromtimestamp(event['start_time'], datetime.timezone.utc).astimezone(TZ_PRAGUE)
            start_str = dt_start.strftime("%H:%M") # Today?

            # If notification is 2h before, it might be different day? Unlikely for 2h/5m.
            # But just in case, use Discord relative timestamp
            discord_ts = f"<t:{int(event['start_time'])}:R>"

            embed = discord.Embed(
                title=f"{event['name']}",
                description=f"{title_prefix} {time_str}!\n\n**Začátek:** {discord_ts}",
                color=discord.Color.orange() if notif_type == '2h' else discord.Color.red(),
                timestamp=datetime.datetime.now()
            )

            if event['image_url']:
                embed.set_image(url=event['image_url'])

            if event['link']:
                embed.url = event['link']

            content = f"{role_mention} **Upozornění na Event!**"

            try:
                await channel.send(content=content, embed=embed)
            except Exception as e:
                logger.error(f"Failed to send notification to guild {guild.id}: {e}")

    @tasks.loop(time=datetime.time(hour=20, minute=0, tzinfo=TZ_PRAGUE))
    async def weekly_summary_task(self):
        # Only run on Sunday
        now = datetime.datetime.now(TZ_PRAGUE)
        if now.weekday() != 6: # Sunday is 6
            return

        logger.info("Running weekly summary task.")

        # Calculate range: Next Monday 00:00 to Next Sunday 23:59
        today = now.date()
        next_monday = today + datetime.timedelta(days=1)
        next_sunday = next_monday + datetime.timedelta(days=6)

        # Create timestamps (naive -> localize -> timestamp)
        # Assuming database timestamps are UTC

        start_dt = datetime.datetime.combine(next_monday, datetime.time.min)
        start_dt_aware = TZ_PRAGUE.localize(start_dt)
        start_ts = start_dt_aware.timestamp()

        end_dt = datetime.datetime.combine(next_sunday, datetime.time.max)
        end_dt_aware = TZ_PRAGUE.localize(end_dt)
        end_ts = end_dt_aware.timestamp()

        upcoming_events = await database.get_upcoming_events(start_ts, end_ts)

        if not upcoming_events:
            logger.info("No upcoming events for next week.")
            return

        # Build Embeds (grouped or list)
        # If too many events, might need multiple embeds?
        # For now, one embed.

        embed = discord.Embed(
            title="📅 Přehled Eventů na Příští Týden",
            description=f"Od {next_monday.strftime('%d.%m.')} do {next_sunday.strftime('%d.%m.')}",
            color=discord.Color.blue()
        )

        # Group by day
        events_by_day = {}
        for e in upcoming_events:
            dt = datetime.datetime.fromtimestamp(e['start_time'], datetime.timezone.utc).astimezone(TZ_PRAGUE)
            day_key = dt.strftime("%A %d.%m.") # e.g. Monday 25.02.
            # Localize day names?
            # We can map %A to Czech names
            day_name_en = dt.strftime("%A")
            day_name_cz = self.translate_day(day_name_en)
            day_key = f"{day_name_cz} {dt.strftime('%d.%m.')}"

            if day_key not in events_by_day:
                events_by_day[day_key] = []
            events_by_day[day_key].append(e)

        for day, events in events_by_day.items():
            lines = []
            for e in events:
                time_str = f"<t:{int(e['start_time'])}:t>" # Short time (12:00)
                link_md = f"[{e['name']}]({e['link']})" if e['link'] else e['name']
                lines.append(f"• {time_str} {link_md}")

            embed.add_field(name=day, value="\n".join(lines), inline=False)

        # Send to all configured channels
        for guild in self.bot.guilds:
            config = await database.get_event_config(guild.id)
            if not config or not config['channel_id']:
                continue

            channel = guild.get_channel(config['channel_id'])
            if not channel:
                continue

            # Maybe ping role here too?
            role = guild.get_role(config['role_id']) if config['role_id'] else None
            role_mention = role.mention if role else ""

            try:
                await channel.send(content=f"{role_mention} **Týdenní přehled eventů!**", embed=embed)
            except Exception as e:
                logger.error(f"Failed to send summary to guild {guild.id}: {e}")

    def translate_day(self, en_day):
        days = {
            "Monday": "Pondělí", "Tuesday": "Úterý", "Wednesday": "Středa",
            "Thursday": "Čtvrtek", "Friday": "Pátek", "Saturday": "Sobota",
            "Sunday": "Neděle"
        }
        return days.get(en_day, en_day)

    @scrape_task.before_loop
    async def before_scrape(self):
        await self.bot.wait_until_ready()
        # Run once on startup
        logger.info("Running initial scrape on boot.")
        await self._run_scrape()

    @notification_task.before_loop
    async def before_notif(self):
        await self.bot.wait_until_ready()

    @weekly_summary_task.before_loop
    async def before_summary(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Events(bot))
