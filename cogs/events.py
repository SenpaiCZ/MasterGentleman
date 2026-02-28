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
        self.daily_summary_task.start()

    def cog_unload(self):
        self.scrape_task.cancel()
        self.notification_task.cancel()
        self.weekly_summary_task.cancel()
        self.daily_summary_task.cancel()

    # --- Commands ---

    @app_commands.command(name="scrape_events", description="Manuálně spustit stahování eventů (Admin)")
    @commands.has_permissions(administrator=True)
    async def manual_scrape(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self._run_scrape()
        await interaction.followup.send(f"✅ Staženo/aktualizováno {count} eventů.")

    @app_commands.command(name="upozorneni_udalosti", description="Přepnout zasílání upozornění na eventy (Toggle Event Alerts)")
    async def toggle_event_alerts(self, interaction: discord.Interaction):
        """Zapne nebo vypne roli pro upozornění na eventy."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Tento příkaz funguje pouze na serveru.", ephemeral=True)
            return

        config = await database.get_guild_config(interaction.guild.id)
        if not config or not config['event_role_id']:
            await interaction.response.send_message("❌ Role pro upozornění není nastavena. Kontaktujte administrátora.", ephemeral=True)
            return

        role = interaction.guild.get_role(config['event_role_id'])
        if not role:
            await interaction.response.send_message("❌ Nastavená role již neexistuje.", ephemeral=True)
            return

        if role in interaction.user.roles:
            try:
                await interaction.user.remove_roles(role, reason="User toggled off event alerts")
                await interaction.response.send_message(f"🔕 Role {role.mention} byla odebrána. Už nebudete dostávat upozornění.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Nemám oprávnění spravovat tuto roli.", ephemeral=True)
        else:
            try:
                await interaction.user.add_roles(role, reason="User toggled on event alerts")
                await interaction.response.send_message(f"🔔 Role {role.mention} byla přidána. Budete dostávat upozornění.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Nemám oprávnění spravovat tuto roli.", ephemeral=True)

    udalosti_group = app_commands.Group(name="udalosti", description="Příkazy pro události (Events)")

    @udalosti_group.command(name="tyden", description="Zobrazit eventy na příštích 7 dní (Next 7 days)")
    async def udalosti_tyden(self, interaction: discord.Interaction):
        """Zobrazí přehled událostí na příštích 7 dní."""
        await interaction.response.defer(ephemeral=True)

        now = datetime.datetime.now(TZ_PRAGUE)
        start_ts = now.timestamp()
        end_dt = now + datetime.timedelta(days=7)
        end_ts = end_dt.timestamp()

        upcoming_events = await database.get_upcoming_events(start_ts, end_ts)

        if not upcoming_events:
            await interaction.followup.send("❌ Žádné nadcházející eventy na příštích 7 dní.", ephemeral=True)
            return

        embed = self._create_summary_embed(upcoming_events, "📅 Přehled Eventů (7 Dní)")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @udalosti_group.command(name="dnes", description="Zobrazit dnešní eventy (Today's Events)")
    async def udalosti_dnes(self, interaction: discord.Interaction):
        """Zobrazí eventy pro dnešní den."""
        await interaction.response.defer(ephemeral=True)

        now = datetime.datetime.now(TZ_PRAGUE)

        # Start of day
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_ts = start_dt.timestamp()

        # End of day
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        end_ts = end_dt.timestamp()

        upcoming_events = await database.get_upcoming_events(start_ts, end_ts)

        if not upcoming_events:
            await interaction.followup.send("❌ Žádné eventy pro dnešní den.", ephemeral=True)
            return

        embed = self._create_daily_summary_embed(upcoming_events, "📅 Dnešní Eventy")
        await interaction.followup.send(embed=embed, ephemeral=True)

    def _create_summary_embed(self, events, title):
        embed = discord.Embed(
            title=title,
            color=discord.Color.teal()
        )

        description = ""
        for ev in events:
            start_dt = datetime.datetime.fromtimestamp(ev['start_time'], datetime.timezone.utc).astimezone(TZ_PRAGUE)
            day_name_en = start_dt.strftime("%A")
            day_name_cz = self.translate_day(day_name_en)

            time_text = ev.get('time_text') or "TBA"
            link = ev.get('link') or ""
            name = ev.get('name') or "Neznámý event"

            description += f"**{day_name_cz}**: [{name}]({link}) ({time_text} - <t:{int(ev['start_time'])}:R>)\n"

        embed.description = description
        return embed

    def _create_daily_summary_embed(self, events, title):
        embed = discord.Embed(
            title=title,
            color=discord.Color.green()
        )

        for ev in events:
            time_text = ev.get('time_text') or "TBA"
            event_type = ev.get('type') or "Event"
            link = ev.get('link') or ""
            name = ev.get('name') or "Neznámý event"

            embed.add_field(
                name=name,
                value=f"**Typ:** {event_type}\n**Čas:** {time_text} (<t:{int(ev['start_time'])}:R>)\n[Odkaz]({link})",
                inline=False
            )

        return embed

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
                e['name'], e['link'], e['image_url'], e['start_time'], e['end_time'], e.get('type', 'Event'), e.get('time_text', '')
            )
            count += 1
        logger.info(f"Database updated with {count} events.")
        return count

    @tasks.loop(minutes=1)
    async def notification_task(self):
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

        # 2h Warning: [now + 90min, now + 130min]
        events_2h = await database.get_events_for_notification(now_ts + 90*60, now_ts + 130*60, '2h')
        for event in events_2h:
            await self._send_notification(event, '2h')
            await database.mark_event_notified(event['id'], '2h')

        # 5m Warning: [now + 1min, now + 10min]
        events_5m = await database.get_events_for_notification(now_ts + 1*60, now_ts + 10*60, '5m')
        for event in events_5m:
            await self._send_notification(event, '5m')
            await database.mark_event_notified(event['id'], '5m')

    async def _send_notification(self, event, notif_type):
        for guild in self.bot.guilds:
            config = await database.get_guild_config(guild.id)
            if not config or not config['event_channel_id']:
                continue

            channel = guild.get_channel(config['event_channel_id'])
            if not channel:
                continue

            role = guild.get_role(config['event_role_id']) if config['event_role_id'] else None
            role_mention = role.mention if role else ""

            time_str = "2 hodiny" if notif_type == '2h' else "5 minut"
            title_prefix = "⏰ Začíná za"

            discord_ts = f"<t:{int(event['start_time'])}:R>"
            time_text = event.get('time_text') or "TBA"
            event_type = event.get('type') or "Event"

            embed = discord.Embed(
                title=f"⏰ Upozornění na událost: {event['name']}",
                description=f"**Začátek:** {discord_ts}\n**Čas:** {time_text}\n**Typ:** {event_type}",
                color=discord.Color.orange() if notif_type == '2h' else discord.Color.red(),
                url=event.get('link') or ""
            )

            if event['image_url']:
                embed.set_thumbnail(url=event['image_url'])

            msg_suffix = "začíná za 2 hodiny!" if notif_type == '2h' else "začíná za 5 minut!"
            content = f"{role_mention} Událost {msg_suffix}"

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

        today = now.date()
        next_monday = today + datetime.timedelta(days=1)
        next_sunday = next_monday + datetime.timedelta(days=6)

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

        embed = self._create_summary_embed(
            upcoming_events,
            f"📅 Přehled Eventů na Příští Týden ({next_monday.strftime('%d.%m.')} - {next_sunday.strftime('%d.%m.')})"
        )

        for guild in self.bot.guilds:
            config = await database.get_guild_config(guild.id)
            if not config or not config['event_channel_id']:
                continue

            channel = guild.get_channel(config['event_channel_id'])
            if not channel:
                continue

            role = guild.get_role(config['event_role_id']) if config['event_role_id'] else None
            role_mention = role.mention if role else ""

            try:
                await channel.send(content=f"{role_mention} **Týdenní přehled eventů!**", embed=embed)
            except Exception as e:
                logger.error(f"Failed to send summary to guild {guild.id}: {e}")

    @tasks.loop(time=datetime.time(hour=7, minute=0, tzinfo=TZ_PRAGUE))
    async def daily_summary_task(self):
        logger.info("Running daily summary task.")

        now = datetime.datetime.now(TZ_PRAGUE)
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_ts = start_dt.timestamp()

        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        end_ts = end_dt.timestamp()

        # We will reuse the get_events_for_notification logic or just query direct
        events = await database.get_events_for_notification(start_ts, end_ts, 'morning')
        if not events:
            logger.info("No upcoming events for today's morning summary.")
            return

        embed = self._create_daily_summary_embed(events, "📅 Dnešní Eventy")

        for guild in self.bot.guilds:
            config = await database.get_guild_config(guild.id)
            if not config or not config['event_channel_id']:
                continue

            channel = guild.get_channel(config['event_channel_id'])
            if not channel:
                continue

            role = guild.get_role(config['event_role_id']) if config['event_role_id'] else None
            role_mention = role.mention if role else ""

            try:
                await channel.send(content=f"{role_mention} **Ranní přehled událostí!**", embed=embed)
            except Exception as e:
                logger.error(f"Failed to send morning summary to guild {guild.id}: {e}")

        # Mark as notified after sending
        for ev in events:
            await database.mark_event_notified(ev['id'], 'morning')

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
        logger.info("Running initial scrape on boot.")
        await self._run_scrape()

    @daily_summary_task.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    @notification_task.before_loop
    async def before_notif(self):
        await self.bot.wait_until_ready()

    @weekly_summary_task.before_loop
    async def before_summary(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Events(bot))
