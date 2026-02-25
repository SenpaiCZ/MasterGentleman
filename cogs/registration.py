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

async def save_user_registration(interaction, friend_code, team, region, account_name, is_main):
    """Helper to save user and update roles."""
    # Show loading state first
    await interaction.response.edit_message(content="⏳ Ukládám údaje...", view=None, embed=None)

    try:
        await database.add_user_account(
            interaction.user.id,
            friend_code,
            team,
            region,
            account_name,
            is_main
        )
    except Exception as e:
        logger.error(f"Error saving user registration: {e}")
        await interaction.edit_original_response(content="❌ Nastala chyba při ukládání registrace.", view=None)
        return

    # Update roles
    cog = interaction.client.get_cog("Registration")
    if cog:
        await cog.update_user_roles(interaction.guild, interaction.user, team, region)

    type_str = "Hlavní" if is_main else "Vedlejší"
    embed = discord.Embed(
        title="✅ Registrace Dokončena",
        description=f"**Účet:** {account_name} ({type_str})\n**FC:** `{friend_code}`\n**Tým:** {team}\n**Region:** {region}",
        color=TEAMS.get(team, discord.Color.green())
    )
    embed.set_footer(text="Tip: Použijte /nabidka pro přidání Pokémonů.")

    await interaction.edit_original_response(content="", embed=embed, view=None)

class AccountTypeSelect(ui.Select):
    def __init__(self, friend_code, team, region, account_name):
        self.friend_code = friend_code
        self.team = team
        self.region = region
        self.account_name = account_name
        options = [
            discord.SelectOption(label="Hlavní účet (Main)", value="True", description="Toto bude můj hlavní účet"),
            discord.SelectOption(label="Vedlejší účet (Alt)", value="False", description="Toto je vedlejší účet")
        ]
        super().__init__(placeholder="Je toto hlavní účet?", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        is_main = self.values[0] == "True"
        await save_user_registration(interaction, self.friend_code, self.team, self.region, self.account_name, is_main)

class AccountTypeView(ui.View):
    def __init__(self, friend_code, team, region, account_name):
        super().__init__()
        self.add_item(AccountTypeSelect(friend_code, team, region, account_name))

class RegionSelect(ui.Select):
    def __init__(self, friend_code, team, account_name, mode):
        self.friend_code = friend_code
        self.team = team
        self.account_name = account_name
        self.mode = mode
        options = [discord.SelectOption(label=region) for region in REGIONS]
        super().__init__(placeholder="Vyberte region (Select Region)", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        region = self.values[0]

        if self.mode == "REGISTER":
            # Direct save as Main
            await save_user_registration(interaction, self.friend_code, self.team, region, self.account_name, True)
        else:
            # ADD_ACCOUNT: Ask for Main/Alt
            embed = discord.Embed(
                title="Krok 3/3: Typ Účtu",
                description=f"Vybrán region: **{region}**.\nJe tento účet hlavní nebo vedlejší?",
                color=TEAMS.get(self.team, discord.Color.light_grey())
            )
            await interaction.response.edit_message(
                content="",
                embed=embed,
                view=AccountTypeView(self.friend_code, self.team, region, self.account_name)
            )

class RegionSelectView(ui.View):
    def __init__(self, friend_code, team, account_name, mode):
        super().__init__()
        self.add_item(RegionSelect(friend_code, team, account_name, mode))

class TeamSelect(ui.Select):
    def __init__(self, friend_code, account_name, mode):
        self.friend_code = friend_code
        self.account_name = account_name
        self.mode = mode
        options = [
            discord.SelectOption(label="Mystic (Blue)", value="Mystic", emoji="💙"),
            discord.SelectOption(label="Valor (Red)", value="Valor", emoji="❤️"),
            discord.SelectOption(label="Instinct (Yellow)", value="Instinct", emoji="💛")
        ]
        super().__init__(placeholder="Vyberte tým (Select Team)", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        team = self.values[0]
        embed = discord.Embed(
            title="Krok 2: Vyberte Region",
            description=f"Vybrán tým: **{team}**.\nKde nejčastěji hrajete?",
            color=TEAMS.get(team, discord.Color.light_grey())
        )
        await interaction.response.edit_message(
            content="",
            embed=embed,
            view=RegionSelectView(self.friend_code, team, self.account_name, self.mode)
        )

class TeamSelectView(ui.View):
    def __init__(self, friend_code, account_name, mode):
        super().__init__()
        self.add_item(TeamSelect(friend_code, account_name, mode))

class RegistrationModal(ui.Modal, title="Registrace Trenéra"):
    friend_code = ui.TextInput(
        label="Friend Code (12 číslic)",
        placeholder="1234 5678 9012",
        min_length=12,
        max_length=15
    )

    async def on_submit(self, interaction: discord.Interaction):
        code = self.friend_code.value.replace(" ", "")

        if not code.isdigit() or len(code) != 12:
            await interaction.response.send_message("❌ Friend Code musí obsahovat přesně 12 číslic.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Krok 1: Vyberte Tým",
            description=f"Friend Code **{code}** přijat.\nZa jaký tým hrajete?",
            color=discord.Color.light_grey()
        )
        await interaction.response.send_message(
            embed=embed,
            view=TeamSelectView(code, "Main", "REGISTER"),
            ephemeral=True
        )

class AddAccountModal(ui.Modal, title="Přidat další účet"):
    friend_code = ui.TextInput(
        label="Friend Code (12 číslic)",
        placeholder="1234 5678 9012",
        min_length=12,
        max_length=15
    )
    account_name = ui.TextInput(
        label="Název účtu (např. Alt 1)",
        placeholder="Alt 1",
        min_length=1,
        max_length=20,
        default="Alt"
    )

    async def on_submit(self, interaction: discord.Interaction):
        code = self.friend_code.value.replace(" ", "")
        name = self.account_name.value.strip()

        if not code.isdigit() or len(code) != 12:
            await interaction.response.send_message("❌ Friend Code musí obsahovat přesně 12 číslic.", ephemeral=True)
            return

        if not name:
            name = "Alt"

        embed = discord.Embed(
            title="Krok 1: Vyberte Tým",
            description=f"Účet **{name}** (FC: {code}) připraven.\nZa jaký tým hraje?",
            color=discord.Color.light_grey()
        )
        await interaction.response.send_message(
            embed=embed,
            view=TeamSelectView(code, name, "ADD_ACCOUNT"),
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

        # 2. Add roles (we don't remove old ones anymore to support mixed roles, or maybe we should?)
        # If user has Main Mystic and Alt Valor, having both roles might be confusing.
        # But usually Discord roles denote 'identity'.
        # Let's just ADD.

        try:
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

    @app_commands.command(name="registrace", description="Zaregistrujte svůj první (hlavní) účet")
    async def registrace(self, interaction: discord.Interaction):
        """Spustí registrační proces pro nový účet."""
        # Check if user already exists
        accounts = await database.get_user_accounts(interaction.user.id)
        if accounts:
            await interaction.response.send_message(
                "❌ Už máte registrovaný účet. Pokud chcete přidat další, použijte příkaz `/pridat_ucet`.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(RegistrationModal())

    @app_commands.command(name="pridat_ucet", description="Přidat další herní účet (multi-account)")
    async def pridat_ucet(self, interaction: discord.Interaction):
        """Přidá další účet pro uživatele."""
        # Check if user registered first
        accounts = await database.get_user_accounts(interaction.user.id)
        if not accounts:
            await interaction.response.send_message(
                "❌ Nemáte žádný účet. Nejprve použijte `/registrace`.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(AddAccountModal())

async def setup(bot):
    await bot.add_cog(Registration(bot))
