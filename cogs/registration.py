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
    if not interaction.response.is_done():
        await interaction.response.edit_message(content="⏳ Ukládám údaje...", view=None, embed=None)
    else:
        await interaction.edit_original_response(content="⏳ Ukládám údaje...", view=None, embed=None)

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
        await cog.sync_roles_with_main_account(interaction.guild, interaction.user)

    type_str = "Hlavní" if is_main else "Rodina/Přátelé"
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
            discord.SelectOption(label="Účet pro dalšího hráče bez Discordu", value="False", description="Např. pro rodinu nebo přátele")
        ]
        super().__init__(placeholder="Je toto hlavní účet?", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        is_main = self.values[0] == "True"
        await save_user_registration(interaction, self.friend_code, self.team, self.region, self.account_name, is_main)

class AccountTypeView(ui.View):
    def __init__(self, friend_code, team, region, account_name):
        super().__init__()
        self.add_item(AccountTypeSelect(friend_code, team, region, account_name))

class EventNotificationView(ui.View):
    def __init__(self, friend_code, team, region, account_name):
        super().__init__()
        self.friend_code = friend_code
        self.team = team
        self.region = region
        self.account_name = account_name

    @ui.button(label="Ano, chci upozornění", style=discord.ButtonStyle.success, emoji="🔔")
    async def yes_notifications(self, interaction: discord.Interaction, button: ui.Button):
        # Defer immediately to allow time for role update
        await interaction.response.defer()
        await self._toggle_role(interaction, True)
        await save_user_registration(interaction, self.friend_code, self.team, self.region, self.account_name, is_main=True)

    @ui.button(label="Ne, děkuji", style=discord.ButtonStyle.secondary, emoji="🔕")
    async def no_notifications(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await save_user_registration(interaction, self.friend_code, self.team, self.region, self.account_name, is_main=True)

    async def _toggle_role(self, interaction, enable):
        if not interaction.guild:
            return

        config = await database.get_guild_config(interaction.guild.id)
        if not config or not config['event_role_id']:
            return

        role = interaction.guild.get_role(config['event_role_id'])
        if not role:
            return

        try:
            if enable:
                await interaction.user.add_roles(role, reason="Registration: Accepted Event Alerts")
        except:
            pass

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
            # Ask for Notifications
            embed = discord.Embed(
                title="Krok 3: Upozornění na Eventy",
                description=f"Vybrán region: **{region}**.\n\nChcete dostávat upozornění na blížící se události (Eventy)?",
                color=TEAMS.get(self.team, discord.Color.light_grey())
            )
            await interaction.response.edit_message(
                content="",
                embed=embed,
                view=EventNotificationView(self.friend_code, self.team, region, self.account_name)
            )
        else:
            # ADD_ACCOUNT: Ask for Main/Alt
            embed = discord.Embed(
                title="Krok 3/3: Typ Účtu",
                description=f"Vybrán region: **{region}**.\nJe tento účet váš hlavní, nebo pro dalšího hráče?",
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
    account_name = ui.TextInput(
        label="Jméno Trenéra (In-Game Name)",
        placeholder="Váš přesný nick ve hře",
        min_length=3,
        max_length=20,
        required=True
    )
    friend_code = ui.TextInput(
        label="Friend Code (12 číslic)",
        placeholder="1234 5678 9012",
        min_length=12,
        max_length=15
    )

    async def on_submit(self, interaction: discord.Interaction):
        code = self.friend_code.value.replace(" ", "")
        name = self.account_name.value.strip()

        if not code.isdigit() or len(code) != 12:
            await interaction.response.send_message("❌ Friend Code musí obsahovat přesně 12 číslic.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Krok 1: Vyberte Tým",
            description=f"Trenér **{name}** (FC: {code}) registrován.\nZa jaký tým hrajete?",
            color=discord.Color.light_grey()
        )
        await interaction.response.send_message(
            embed=embed,
            view=TeamSelectView(code, name, "REGISTER"),
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
        label="Jméno Trenéra (In-Game Name)",
        placeholder="Váš přesný nick ve hře",
        min_length=1,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        code = self.friend_code.value.replace(" ", "")
        name = self.account_name.value.strip()

        if not code.isdigit() or len(code) != 12:
            await interaction.response.send_message("❌ Friend Code musí obsahovat přesně 12 číslic.", ephemeral=True)
            return

        if not name:
            await interaction.response.send_message("❌ Musíte zadat jméno účtu.", ephemeral=True)
            return

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

async def show_update_actions(interaction, account):
    embed = discord.Embed(
        title=f"Úprava účtu: {account['account_name']}",
        description=f"**FC:** {account['friend_code']}\n**Tým:** {account['team']}\n**Region:** {account['region']}",
        color=TEAMS.get(account['team'], discord.Color.default())
    )
    view = UpdateActionSelectView(account)
    if interaction.response.is_done():
        await interaction.edit_original_response(content="", embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def confirm_update(interaction, account, field, value):
    embed = discord.Embed(
        title="✅ Aktualizace Úspěšná",
        description=f"**{field}** byl změněn na: **{value}**",
        color=discord.Color.green()
    )
    if not interaction.response.is_done():
        await interaction.response.edit_message(content="", embed=embed, view=None)
    else:
        await interaction.edit_original_response(content="", embed=embed, view=None)

class UpdateAccountSelect(ui.Select):
    def __init__(self, accounts):
        options = []
        for acc in accounts:
            is_main = "⭐ " if acc['is_main'] else ""
            label = f"{is_main}{acc['account_name']} ({acc['team']})"
            options.append(discord.SelectOption(label=label, value=str(acc['id'])))
        super().__init__(placeholder="Vyberte účet...", min_values=1, max_values=1, options=options)
        self.accounts = accounts

    async def callback(self, interaction: discord.Interaction):
        account_id = int(self.values[0])
        account = next((a for a in self.accounts if a['id'] == account_id), None)
        if account:
            await show_update_actions(interaction, account)

class UpdateAccountSelectView(ui.View):
    def __init__(self, accounts):
        super().__init__()
        self.add_item(UpdateAccountSelect(accounts))

class UpdateActionSelect(ui.Select):
    def __init__(self, account):
        self.account = account
        options = [
            discord.SelectOption(label="Změnit Jméno (Name)", value="name", description="Upravit In-Game Name"),
            discord.SelectOption(label="Změnit Friend Code", value="fc", description="Upravit Friend Code"),
            discord.SelectOption(label="Změnit Tým (Team)", value="team", description="Změnit herní tým"),
            discord.SelectOption(label="Změnit Region", value="region", description="Změnit region hraní")
        ]
        super().__init__(placeholder="Co chcete upravit?", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "name":
            await interaction.response.send_modal(UpdateNameModal(self.account))
        elif action == "fc":
            await interaction.response.send_modal(UpdateFCModal(self.account))
        elif action == "team":
            await interaction.response.send_message("Vyberte nový tým:", view=UpdateTeamView(self.account), ephemeral=True)
        elif action == "region":
            await interaction.response.send_message("Vyberte nový region:", view=UpdateRegionView(self.account), ephemeral=True)

class UpdateActionSelectView(ui.View):
    def __init__(self, account):
        super().__init__()
        self.add_item(UpdateActionSelect(account))

class UpdateNameModal(ui.Modal):
    def __init__(self, account):
        super().__init__(title="Změna Jména")
        self.account = account
        self.name_input = ui.TextInput(label="Nové Jméno", default=account['account_name'], min_length=1, max_length=20)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value.strip()
        await database.update_user_account(self.account['id'], account_name=new_name)
        await confirm_update(interaction, self.account, "Jméno", new_name)

class UpdateFCModal(ui.Modal):
    def __init__(self, account):
        super().__init__(title="Změna Friend Code")
        self.account = account
        self.fc_input = ui.TextInput(label="Nový Friend Code", default=account['friend_code'], min_length=12, max_length=15)
        self.add_item(self.fc_input)

    async def on_submit(self, interaction: discord.Interaction):
        code = self.fc_input.value.replace(" ", "")
        if not code.isdigit() or len(code) != 12:
            await interaction.response.send_message("❌ Friend Code musí obsahovat přesně 12 číslic.", ephemeral=True)
            return

        await database.update_user_account(self.account['id'], friend_code=code)
        await confirm_update(interaction, self.account, "Friend Code", code)

class UpdateTeamSelect(ui.Select):
    def __init__(self, account):
        self.account = account
        options = [
            discord.SelectOption(label="Mystic (Blue)", value="Mystic", emoji="💙"),
            discord.SelectOption(label="Valor (Red)", value="Valor", emoji="❤️"),
            discord.SelectOption(label="Instinct (Yellow)", value="Instinct", emoji="💛")
        ]
        super().__init__(placeholder="Vyberte nový tým", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        new_team = self.values[0]
        await database.update_user_account(self.account['id'], team=new_team)

        # Sync roles if main
        if self.account['is_main']:
            cog = interaction.client.get_cog("Registration")
            if cog:
                await cog.sync_roles_with_main_account(interaction.guild, interaction.user)

        await confirm_update(interaction, self.account, "Tým", new_team)

class UpdateTeamView(ui.View):
    def __init__(self, account):
        super().__init__()
        self.add_item(UpdateTeamSelect(account))

class UpdateRegionSelect(ui.Select):
    def __init__(self, account):
        self.account = account
        options = [discord.SelectOption(label=region) for region in REGIONS]
        super().__init__(placeholder="Vyberte nový region", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        new_region = self.values[0]
        await database.update_user_account(self.account['id'], region=new_region)

        # Sync roles if main
        if self.account['is_main']:
            cog = interaction.client.get_cog("Registration")
            if cog:
                await cog.sync_roles_with_main_account(interaction.guild, interaction.user)

        await confirm_update(interaction, self.account, "Region", new_region)

class UpdateRegionView(ui.View):
    def __init__(self, account):
        super().__init__()
        self.add_item(UpdateRegionSelect(account))

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

    async def sync_roles_with_main_account(self, guild, member):
        """Ensures the member has roles matching their Main account only."""
        if not guild:
            return

        accounts = await database.get_user_accounts(member.id)
        if not accounts:
            return

        # Find Main Account
        main_account = next((acc for acc in accounts if acc['is_main']), None)
        if not main_account:
            # Fallback to first account if no main is explicitly set
            main_account = accounts[0]

        target_team = main_account['team']
        target_region = main_account['region']

        # Ensure roles exist
        target_team_role = await self._ensure_role(guild, target_team, TEAMS.get(target_team, discord.Color.default()))
        target_region_role = await self._ensure_role(guild, target_region)

        if not target_team_role or not target_region_role:
            return

        # Identify roles to remove
        all_team_names = set(TEAMS.keys())
        all_region_names = set(REGIONS)

        roles_to_remove = []
        roles_to_add = []

        for role in member.roles:
            if role.name in all_team_names and role.name != target_team:
                roles_to_remove.append(role)
            if role.name in all_region_names and role.name != target_region:
                roles_to_remove.append(role)

        if target_team_role not in member.roles:
            roles_to_add.append(target_team_role)
        if target_region_role not in member.roles:
            roles_to_add.append(target_region_role)

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Syncing Main Account Roles (Removal)")
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="Syncing Main Account Roles (Addition)")

            if roles_to_remove or roles_to_add:
                logger.info(f"Synced roles for {member.display_name}: +{len(roles_to_add)}, -{len(roles_to_remove)}")
        except discord.Forbidden:
            logger.error(f"Missing permissions to sync roles for {member.display_name}")

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

    @app_commands.command(name="pridat_ucet", description="Přidat účet pro dalšího hráče bez Discordu")
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

    @app_commands.command(name="upravit_profil", description="Upravit údaje profilu (jméno, FC, tým, region)")
    async def upravit_profil(self, interaction: discord.Interaction):
        """Umožňuje upravit údaje registrovaného účtu."""
        accounts = await database.get_user_accounts(interaction.user.id)
        if not accounts:
            await interaction.response.send_message(
                "❌ Nemáte žádný registrovaný účet. Použijte `/registrace`.",
                ephemeral=True
            )
            return

        if len(accounts) == 1:
            # Auto-select the only account
            await show_update_actions(interaction, accounts[0])
        else:
            # Show selection view
            view = UpdateAccountSelectView(accounts)
            await interaction.response.send_message("Vyberte účet k úpravě:", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Registration(bot))
