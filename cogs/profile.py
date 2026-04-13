import discord
import asyncio
from discord.ext import commands
from discord import app_commands, ui
import database
import logging
import qrcode
from io import BytesIO

logger = logging.getLogger('discord')

TEAMS = {
    "Mystic": discord.Color.blue(),
    "Valor": discord.Color.red(),
    "Instinct": discord.Color.gold()
}

class ProfileView(ui.View):
    def __init__(self, accounts):
        super().__init__(timeout=None)
        # Add buttons for each account (limit to 5 due to Discord button limit per row, max 25 total)
        # We'll just show buttons for first 5 accounts.
        for i, acc in enumerate(accounts[:5]):
            label = f"Kopírovat {acc['account_name']}"
            if acc['is_main']:
                label = f"📋 {acc['account_name']} (Main)"
            else:
                label = f"📋 {acc['account_name']}"

            button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary, custom_id=f"copy_fc_{acc['id']}")
            button.callback = self.create_callback(acc['friend_code'])
            self.add_item(button)

    def create_callback(self, code):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_message(f"{code}", ephemeral=True)
        return callback

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ctx_menu_profile = app_commands.ContextMenu(
            name="Zobrazit profil",
            callback=self.show_profile_context
        )
        self.ctx_menu_qr = app_commands.ContextMenu(
            name="Generovat QR kódy",
            callback=self.generate_qr_context
        )
        self.bot.tree.add_command(self.ctx_menu_profile)
        self.bot.tree.add_command(self.ctx_menu_qr)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu_profile.name, type=self.ctx_menu_profile.type)
        self.bot.tree.remove_command(self.ctx_menu_qr.name, type=self.ctx_menu_qr.type)

    async def _show_profile(self, interaction: discord.Interaction, user: discord.Member):
        try:
            accounts = await database.get_user_accounts(user.id)

            if not accounts:
                await interaction.response.send_message(
                    f"❌ Uživatel {user.display_name} nemá registrovaný žádný účet.",
                    ephemeral=True
                )
                return

            # Find Main account for embed color
            main_account = next((acc for acc in accounts if acc['is_main']), accounts[0])
            team_color = TEAMS.get(main_account['team'], discord.Color.default())

            embed = discord.Embed(title=f"Profil trenéra {user.display_name}", color=team_color)
            embed.set_thumbnail(url=user.display_avatar.url)

            for acc in accounts:
                name = acc['account_name']
                is_main = "⭐ " if acc['is_main'] else ""
                fc = f"{acc['friend_code'][:4]} {acc['friend_code'][4:8]} {acc['friend_code'][8:]}"

                team_emoji = ""
                if acc['team'] == "Mystic": team_emoji = "💙"
                elif acc['team'] == "Valor": team_emoji = "❤️"
                elif acc['team'] == "Instinct": team_emoji = "💛"

                value = (
                    f"**FC:** `{fc}`\n"
                    f"**Tým:** {team_emoji} {acc['team']}\n"
                    f"**Region:** 📍 {acc['region']}"
                )
                embed.add_field(name=f"{is_main}{name}", value=value, inline=False)

            embed.set_footer(text="Pro zkopírování kódu stiskni tlačítko níže.")

            await interaction.response.send_message(
                embed=embed,
                view=ProfileView(accounts),
                ephemeral=True
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

    def _generate_qr_sync(self, fc: str) -> BytesIO:
        """Helper to generate QR code in a thread."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(fc)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    async def generate_qr_context(self, interaction: discord.Interaction, member: discord.Member):
        """Generuje QR kódy pro friend codes uživatele."""
        await interaction.response.defer(ephemeral=True)

        try:
            accounts = await database.get_user_accounts(member.id)
            if not accounts:
                await interaction.followup.send(f"❌ Uživatel {member.display_name} nemá žádný registrovaný účet.", ephemeral=True)
                return

            files = []
            embed = discord.Embed(title=f"QR Kódy: {member.display_name}", color=discord.Color.blue())

            # Generate all QR codes concurrently in threads
            tasks = [asyncio.to_thread(self._generate_qr_sync, acc['friend_code']) for acc in accounts]
            buffers = await asyncio.gather(*tasks)

            for acc, buffer in zip(accounts, buffers):
                fc = acc['friend_code']
                name = acc['account_name']
                is_main = "⭐ " if acc['is_main'] else ""

                filename = f"qr_{name}_{fc}.png".replace(" ", "_")
                file = discord.File(buffer, filename=filename)
                files.append(file)

                embed.add_field(name=f"{is_main}{name}", value=f"FC: `{fc}`", inline=False)

            await interaction.followup.send(embed=embed, files=files)

        except Exception as e:
            logger.error(f"Error generating QR codes for {member.id}: {e}")
            await interaction.followup.send("❌ Nastala chyba při generování QR kódů.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Profile(bot))
