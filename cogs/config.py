import discord
from discord.ext import commands
from discord import app_commands
import database
import logging

logger = logging.getLogger('discord')

class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    setup_group = app_commands.Group(name="setup", description="Nastavení bota")
    events_group = app_commands.Group(name="udalosti", description="Nastavení upozornění na Pokémon GO eventy", parent=setup_group)

    @setup_group.command(name="nabidka", description="Nastavit kanál pro nové nabídky (HAVE)")
    @app_commands.describe(channel="Textový kanál pro nabídky")
    @commands.has_permissions(administrator=True)
    async def set_have_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_guild_config(interaction.guild_id, have_channel_id=channel.id)
        await interaction.response.send_message(f"✅ Kanál pro **Nabídky** byl nastaven na: {channel.mention}", ephemeral=True)
        logger.info(f"User {interaction.user.id} set HAVE channel to {channel.id} for guild {interaction.guild_id}")

    @setup_group.command(name="poptavka", description="Nastavit kanál pro nové poptávky (WANT)")
    @app_commands.describe(channel="Textový kanál pro poptávky")
    @commands.has_permissions(administrator=True)
    async def set_want_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_guild_config(interaction.guild_id, want_channel_id=channel.id)
        await interaction.response.send_message(f"✅ Kanál pro **Poptávky** byl nastaven na: {channel.mention}", ephemeral=True)
        logger.info(f"User {interaction.user.id} set WANT channel to {channel.id} for guild {interaction.guild_id}")

    # --- Events Subgroup ---

    @events_group.command(name="kanal", description="Nastavit kanál pro upozornění na eventy")
    @app_commands.describe(channel="Textový kanál pro zprávy")
    @commands.has_permissions(administrator=True)
    async def set_event_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_guild_config(interaction.guild_id, event_channel_id=channel.id)
        await interaction.response.send_message(f"✅ Kanál pro **Eventy** nastaven na: {channel.mention}", ephemeral=True)

    @events_group.command(name="role", description="Nastavit roli, která bude označena při eventu")
    @app_commands.describe(role="Role pro označení (ping)")
    @commands.has_permissions(administrator=True)
    async def set_event_role(self, interaction: discord.Interaction, role: discord.Role):
        await database.set_guild_config(interaction.guild_id, event_role_id=role.id)
        await interaction.response.send_message(f"✅ Role pro eventy nastavena na: {role.mention}", ephemeral=True)

    @events_group.command(name="stav", description="Zobrazit aktuální nastavení")
    @commands.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        config = await database.get_guild_config(interaction.guild_id)

        # Prepare display values
        event_ch = "Nenastaveno"
        event_role = "Nenastaveno"
        have_ch = "Nenastaveno"
        want_ch = "Nenastaveno"

        if config:
            if config['event_channel_id']:
                ch = interaction.guild.get_channel(config['event_channel_id'])
                if ch: event_ch = ch.mention
                else: event_ch = f"Invalid ID ({config['event_channel_id']})"

            if config['event_role_id']:
                r = interaction.guild.get_role(config['event_role_id'])
                if r: event_role = r.mention
                else: event_role = f"Invalid ID ({config['event_role_id']})"

            if config['have_channel_id']:
                ch = interaction.guild.get_channel(config['have_channel_id'])
                if ch: have_ch = ch.mention
                else: have_ch = f"Invalid ID ({config['have_channel_id']})"

            if config['want_channel_id']:
                ch = interaction.guild.get_channel(config['want_channel_id'])
                if ch: want_ch = ch.mention
                else: want_ch = f"Invalid ID ({config['want_channel_id']})"

        msg = (
            f"**⚙️ Nastavení Bota:**\n\n"
            f"**📅 Udalosti (Events):**\n"
            f"📢 Kanál: {event_ch}\n"
            f"🔔 Role: {event_role}\n\n"
            f"**🤝 Obchody:**\n"
            f"📥 Nabídky (HAVE): {have_ch}\n"
            f"📤 Poptávky (WANT): {want_ch}"
        )
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Config(bot))
