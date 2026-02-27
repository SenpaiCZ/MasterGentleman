import discord
from discord.ext import commands
from discord import app_commands
import database
from services.image_gen import ImageGenerator, MAX_ITEMS
import logging

logger = logging.getLogger('discord')

TEAMS = {
    "Mystic": discord.Color.blue(),
    "Valor": discord.Color.red(),
    "Instinct": discord.Color.gold()
}

class AccountSelect(discord.ui.Select):
    def __init__(self, accounts, typ, cog):
        self.accounts = accounts
        self.typ = typ
        self.cog = cog

        options = []
        for acc in accounts:
            label = f"{acc['account_name']} ({acc['team']})"
            desc = f"FC: {acc['friend_code']}"
            options.append(discord.SelectOption(label=label, description=desc, value=str(acc['id'])))

        super().__init__(placeholder="Vyberte účet...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        account_id = int(self.values[0])
        account = next((a for a in self.accounts if a['id'] == account_id), None)

        if not account:
            await interaction.followup.send("❌ Chyba při výběru účtu.", ephemeral=True)
            return

        await self.cog.generate_and_send(interaction, account, self.typ)

class AccountSelectView(discord.ui.View):
    def __init__(self, accounts, typ, cog):
        super().__init__()
        self.add_item(AccountSelect(accounts, typ, cog))

class Printing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generator = ImageGenerator()

    async def generate_and_send(self, interaction: discord.Interaction, account, typ: str):
        try:
            # Fetch listings for specific account
            listings = await database.get_account_listings(account['id'])

            # Filter by type
            filtered_listings = [{k: l[k] for k in l.keys()} for l in listings if l['listing_type'] == typ]

            if not filtered_listings:
                await interaction.followup.send(f"❌ Účet **{account['account_name']}** nemá žádné záznamy typu '{typ}'.", ephemeral=True)
                return

            # Warning if too many
            if len(filtered_listings) > MAX_ITEMS:
                warning_msg = f"⚠️ Zobrazeno pouze prvních {MAX_ITEMS} záznamů (z celkových {len(filtered_listings)})."
            else:
                warning_msg = ""

            # Get team color
            team_color = TEAMS.get(account['team'], discord.Color.default())
            color_rgb = team_color.to_rgb()

            title = "Chci" if typ == "WANT" else "Nabízím"
            # Use In-Game Name
            user_name = account['account_name']
            friend_code = account.get('friend_code')

            # Generate Image
            image_buffer = await self.generator.generate_card(filtered_listings, title, user_name, color_rgb, friend_code)

            if not image_buffer:
                await interaction.followup.send("❌ Nepodařilo se vygenerovat obrázek (možná chybí data).", ephemeral=True)
                return

            # Send
            file = discord.File(image_buffer, filename=f"{typ.lower()}_list_{user_name}.png")
            content = f"📄 Seznam **{title}** pro **{user_name}**:"
            if warning_msg:
                content += f"\n{warning_msg}"

            await interaction.followup.send(content=content, file=file, ephemeral=True)
            logger.info(f"Generated print card for account {account['id']} type {typ}")

        except Exception as e:
            logger.error(f"Error in generating card: {e}")
            await interaction.followup.send("❌ Nastala chyba při generování obrázku.", ephemeral=True)

    @app_commands.command(name="tisk", description="Vytvoří obrázek seznamu Pokémonů (Create listing image)")
    @app_commands.describe(typ="Typ seznamu (List type)")
    @app_commands.choices(typ=[
        app_commands.Choice(name="Hledám (WANT)", value="WANT"),
        app_commands.Choice(name="Nabízím (HAVE)", value="HAVE")
    ])
    async def tisk(self, interaction: discord.Interaction, typ: str):
        """Generates an image of the selected list."""
        await interaction.response.defer()

        try:
            accounts = await database.get_user_accounts(interaction.user.id)

            if not accounts:
                await interaction.followup.send("❌ Nemáte žádný registrovaný účet. Použijte `/registrace`.", ephemeral=True)
                return

            if len(accounts) == 1:
                # Direct generation
                await self.generate_and_send(interaction, accounts[0], typ)
            else:
                # Ask user to select account
                view = AccountSelectView(accounts, typ, self)
                await interaction.followup.send("Vyberte účet, pro který chcete vygenerovat seznam:", view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in /tisk command: {e}")
            await interaction.followup.send("❌ Nastala chyba při přípravě příkazu.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Printing(bot))
