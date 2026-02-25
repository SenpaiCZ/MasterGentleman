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

class ProfileView(ui.View):
    def __init__(self, friend_code):
        super().__init__(timeout=None)
        self.friend_code = friend_code

    @discord.ui.button(label="📱 Zkopírovat Friend Code", style=discord.ButtonStyle.primary, emoji="📋")
    async def copy_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Reply with just the code, hidden (ephemeral) so user can copy it easily on mobile
        await interaction.response.send_message(f"{self.friend_code}", ephemeral=True)

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name="Zobrazit profil",
            callback=self.show_profile_context
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def _show_profile(self, interaction: discord.Interaction, user: discord.Member):
        try:
            db_user = await database.get_user(user.id)

            if not db_user:
                await interaction.response.send_message(
                    f"❌ Uživatel {user.display_name} není registrován.",
                    ephemeral=True
                )
                return

            # Prepare data
            friend_code = db_user['friend_code']
            team = db_user['team']
            region = db_user['region']

            # Format Friend Code for display (#### #### ####)
            formatted_fc = f"{friend_code[:4]} {friend_code[4:8]} {friend_code[8:]}"

            # Embed
            color = TEAMS.get(team, discord.Color.default())
            embed = discord.Embed(title=f"Profil trenéra {user.display_name}", color=color)
            embed.set_thumbnail(url=user.display_avatar.url)

            embed.add_field(name="🛡️ Tým", value=team, inline=True)
            embed.add_field(name="📍 Region", value=region, inline=True)
            embed.add_field(name="🆔 Friend Code", value=f"`{formatted_fc}`", inline=False)

            embed.set_footer(text="Pro zkopírování kódu stiskni tlačítko níže.")

            await interaction.response.send_message(
                embed=embed,
                view=ProfileView(friend_code),
                ephemeral=False
            )

        except Exception as e:
            logger.error(f"Error fetching profile for {user.id}: {e}")
            await interaction.response.send_message("❌ Nastala chyba při načítání profilu.", ephemeral=True)

    @app_commands.command(name="profil", description="Zobrazí profil trenéra (Show Trainer Profile)")
    @app_commands.describe(uzivatel="Uživatel, jehož profil chcete zobrazit (volitelné)")
    async def profil(self, interaction: discord.Interaction, uzivatel: discord.Member = None):
        """Zobrazí profil uživatele (nebo váš, pokud není zadán)."""
        target = uzivatel or interaction.user
        await self._show_profile(interaction, target)

    async def show_profile_context(self, interaction: discord.Interaction, member: discord.Member):
        await self._show_profile(interaction, member)

async def setup(bot):
    await bot.add_cog(Profile(bot))
