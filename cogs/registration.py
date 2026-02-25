import discord
from discord.ext import commands
from discord import app_commands, ui
import database
import logging

logger = logging.getLogger('discord')

TEAMS = {
    "Mystic": discord.Color.blue(),
    "Valor": discord.Color.red(),
    "Instinct": discord.Color.gold()
}

REGIONS = [
    "Hlavní město Praha",
    "Středočeský kraj",
    "Jihočeský kraj",
    "Plzeňský kraj",
    "Karlovarský kraj",
    "Ústecký kraj",
    "Liberecký kraj",
    "Královéhradecký kraj",
    "Pardubický kraj",
    "Kraj Vysočina",
    "Jihomoravský kraj",
    "Olomoucký kraj",
    "Moravskoslezský kraj",
    "Zlínský kraj"
]

class RegionSelect(ui.Select):
    def __init__(self, friend_code, team):
        self.friend_code = friend_code
        self.team = team
        options = [discord.SelectOption(label=region) for region in REGIONS]
        super().__init__(placeholder="Vyberte region (Select Region)", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        region = self.values[0]
        await interaction.response.defer(ephemeral=True)

        # Save to database
        try:
            await database.upsert_user(interaction.user.id, self.friend_code, self.team, region)
        except Exception as e:
            logger.error(f"Error saving user registration: {e}")
            await interaction.followup.send("❌ Nastala chyba při ukládání registrace.", ephemeral=True)
            return

        # Update roles
        cog = interaction.client.get_cog("Registration")
        if cog:
            await cog.update_user_roles(interaction.guild, interaction.user, self.team, region)

        await interaction.followup.send(
            f"✅ **Registrace dokončena!**\n\n"
            f"👤 **Friend Code:** {self.friend_code}\n"
            f"🛡️ **Tým:** {self.team}\n"
            f"📍 **Region:** {region}\n\n"
            f"💡 *Tip: Použijte `/profil` pro zobrazení karty trenéra nebo `/nabidka` pro přidání Pokémonů.*",
            ephemeral=True
        )

class RegionSelectView(ui.View):
    def __init__(self, friend_code, team):
        super().__init__()
        self.add_item(RegionSelect(friend_code, team))

class TeamSelect(ui.Select):
    def __init__(self, friend_code):
        self.friend_code = friend_code
        options = [
            discord.SelectOption(label="Mystic (Blue)", value="Mystic", emoji="💙"),
            discord.SelectOption(label="Valor (Red)", value="Valor", emoji="❤️"),
            discord.SelectOption(label="Instinct (Yellow)", value="Instinct", emoji="💛")
        ]
        super().__init__(placeholder="Vyberte tým (Select Team)", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        team = self.values[0]
        await interaction.response.send_message(
            f"Vybrán tým: **{team}**. Nyní vyberte region.",
            view=RegionSelectView(self.friend_code, team),
            ephemeral=True
        )

class TeamSelectView(ui.View):
    def __init__(self, friend_code):
        super().__init__()
        self.add_item(TeamSelect(friend_code))

class RegistrationModal(ui.Modal, title="Registrace Trenéra"):
    friend_code = ui.TextInput(
        label="Friend Code (12 číslic)",
        placeholder="1234 5678 9012",
        min_length=12,
        max_length=15 # Allow spaces
    )

    async def on_submit(self, interaction: discord.Interaction):
        code = self.friend_code.value.replace(" ", "")

        if not code.isdigit() or len(code) != 12:
            await interaction.response.send_message("❌ Friend Code musí obsahovat přesně 12 číslic.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Friend Code **{code}** přijat. Nyní vyberte svůj tým.",
            view=TeamSelectView(code),
            ephemeral=True
        )

class Registration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _ensure_role(self, guild, role_name, color=discord.Color.default()):
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            try:
                role = await guild.create_role(name=role_name, color=color, reason="Bot Setup: Registration Role")
                logger.info(f"Created role {role_name} in guild {guild.name}")
            except discord.Forbidden:
                logger.error(f"Missing permissions to create role {role_name} in {guild.name}")
                return None
        return role

    async def update_user_roles(self, guild, member, new_team, new_region):
        if not guild:
            return

        # 1. Ensure new roles exist
        team_role = await self._ensure_role(guild, new_team, TEAMS.get(new_team, discord.Color.default()))
        region_role = await self._ensure_role(guild, new_region)

        if not team_role or not region_role:
            logger.warning("Could not assign roles due to missing permissions or errors.")
            return

        # 2. Identify old roles to remove
        roles_to_remove = []
        for role in member.roles:
            if role.name in TEAMS and role.name != new_team:
                roles_to_remove.append(role)
            if role.name in REGIONS and role.name != new_region:
                roles_to_remove.append(role)

        # 3. Apply changes
        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Registration Update")

            roles_to_add = []
            if team_role not in member.roles:
                roles_to_add.append(team_role)
            if region_role not in member.roles:
                roles_to_add.append(region_role)

            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="Registration Update")
                logger.info(f"Updated roles for {member.display_name}: +{new_team}, +{new_region}")

        except discord.Forbidden:
            logger.error(f"Missing permissions to manage roles for {member.display_name}")

    @app_commands.command(name="registrace", description="Zaregistrujte se (Friend Code, Tým, Region)")
    async def registrace(self, interaction: discord.Interaction):
        """Spustí registrační proces."""
        await interaction.response.send_modal(RegistrationModal())

async def setup(bot):
    await bot.add_cog(Registration(bot))
