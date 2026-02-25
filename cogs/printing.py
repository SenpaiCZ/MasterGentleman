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

async def get_user_team_color(user_id):
    accounts = await database.get_user_accounts(user_id)
    if not accounts:
        return discord.Color.default()

    # Try to find main account
    main = next((acc for acc in accounts if acc['is_main']), accounts[0])
    team_name = main['team']
    return TEAMS.get(team_name, discord.Color.default())

class Printing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generator = ImageGenerator()

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
            # Fetch listings
            listings = await database.get_user_listings(interaction.user.id)

            # Filter by type
            filtered_listings = [l for l in listings if l['listing_type'] == typ]

            if not filtered_listings:
                await interaction.followup.send(f"❌ Nemáte žádné záznamy typu '{typ}'.", ephemeral=True)
                return

            # Warning if too many
            if len(filtered_listings) > MAX_ITEMS:
                warning_msg = f"⚠️ Zobrazeno pouze prvních {MAX_ITEMS} záznamů (z celkových {len(filtered_listings)})."
            else:
                warning_msg = ""

            # Get user info for card
            color = await get_user_team_color(interaction.user.id)
            color_rgb = color.to_rgb()

            title = "SEZNAM POPTÁVKY" if typ == "WANT" else "SEZNAM NABÍDKY"
            user_name = interaction.user.display_name

            # Generate Image
            image_buffer = await self.generator.generate_card(filtered_listings, title, user_name, color_rgb)

            if not image_buffer:
                await interaction.followup.send("❌ Nepodařilo se vygenerovat obrázek (možná chybí data).", ephemeral=True)
                return

            # Send
            file = discord.File(image_buffer, filename=f"{typ.lower()}_list.png")
            content = f"📄 Váš seznam **{title}**:"
            if warning_msg:
                content += f"\n{warning_msg}"

            await interaction.followup.send(content=content, file=file)
            logger.info(f"Generated print card for user {interaction.user.id} type {typ}")

        except Exception as e:
            logger.error(f"Error in /tisk command: {e}")
            await interaction.followup.send("❌ Nastala chyba při generování obrázku.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Printing(bot))
