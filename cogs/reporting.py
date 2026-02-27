import discord
from discord.ext import commands
from discord import app_commands, ui
import traceback
import logging

logger = logging.getLogger('discord')

class ReportModal(ui.Modal, title="Nahlásit Chybu (Report Bug)"):
    description = ui.TextInput(
        label="Popis Chyby",
        placeholder="Co se stalo? Kdy? Jak?",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Fetch owner
        app_info = await interaction.client.application_info()
        owner = app_info.owner

        embed = discord.Embed(
            title="🐛 Nahlášení Chyby (Bug Report)",
            description=self.description.value,
            color=discord.Color.red(),
            timestamp=interaction.created_at
        )
        embed.set_author(name=f"{interaction.user} (ID: {interaction.user.id})", icon_url=interaction.user.display_avatar.url)
        if interaction.guild:
            embed.add_field(name="Guild", value=f"{interaction.guild.name} ({interaction.guild.id})", inline=False)
        else:
            embed.add_field(name="Guild", value="DM", inline=False)

        if interaction.channel:
            embed.add_field(name="Channel", value=f"{interaction.channel.name} ({interaction.channel.id})", inline=False)

        try:
            await owner.send(embed=embed)
            await interaction.response.send_message("✅ Chyba byla nahlášena vývojáři. Děkujeme!", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send bug report to owner: {e}")
            await interaction.response.send_message("❌ Nepodařilo se odeslat hlášení.", ephemeral=True)

class MessageReportModal(ui.Modal, title="Nahlásit Zprávu (Report Message)"):
    reason = ui.TextInput(
        label="Důvod Nahlášení",
        placeholder="Proč nahlašujete tuto zprávu?",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=500,
        required=True
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        app_info = await interaction.client.application_info()
        owner = app_info.owner

        embed = discord.Embed(
            title="🚩 Nahlášení Zprávy (Message Report)",
            description=f"**Důvod:** {self.reason.value}",
            color=discord.Color.orange(),
            timestamp=interaction.created_at
        )
        embed.set_author(name=f"Reporter: {interaction.user} ({interaction.user.id})", icon_url=interaction.user.display_avatar.url)

        # Link to message
        embed.add_field(name="Odkaz na zprávu", value=self.message.jump_url, inline=False)
        embed.add_field(name="Obsah zprávy", value=self.message.content[:1000] if self.message.content else "[No Content]", inline=False)
        embed.add_field(name="Autor zprávy", value=f"{self.message.author} ({self.message.author.id})", inline=False)

        if self.message.channel:
             embed.add_field(name="Kanál", value=f"{self.message.channel.name} ({self.message.channel.id})", inline=False)
        if self.message.guild:
            embed.add_field(name="Guild", value=f"{self.message.guild.name} ({self.message.guild.id})", inline=False)

        try:
            await owner.send(embed=embed)
            await interaction.response.send_message("✅ Zpráva byla nahlášena administrátorovi.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send message report to owner: {e}")
            await interaction.response.send_message("❌ Nepodařilo se odeslat hlášení.", ephemeral=True)


class Reporting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Register context menu - we need to attach it to the tree
        self.ctx_menu = app_commands.ContextMenu(
            name="Nahlásit zprávu",
            callback=self.report_message_context
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    @app_commands.command(name="nahlasit_chybu", description="Nahlásit chybu bota vývojáři (Report Bug)")
    async def nahlasit_chybu(self, interaction: discord.Interaction):
        """Otevře formulář pro nahlášení chyby."""
        await interaction.response.send_modal(ReportModal())

    async def report_message_context(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_modal(MessageReportModal(message))

    # App Command Error Handler (since we use slash commands mostly)
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Notify user ephemeral
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Nastala neočekávaná chyba. Vývojář byl upozorněn.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Nastala neočekávaná chyba. Vývojář byl upozorněn.", ephemeral=True)

        await self._send_error_to_owner(interaction, error)

    async def _send_error_to_owner(self, source, error):
        try:
            app_info = await self.bot.application_info()
            owner = app_info.owner

            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            # Truncate if too long
            if len(tb) > 1900:
                tb = tb[:1900] + "..."

            command_name = "Unknown"
            user_info = "Unknown"
            guild_info = "Unknown"

            if isinstance(source, discord.Interaction):
                command_name = source.command.name if source.command else "Unknown Interaction"
                user_info = f"{source.user} ({source.user.id})"
                guild_info = f"{source.guild.name} ({source.guild.id})" if source.guild else "DM"
            elif isinstance(source, commands.Context):
                command_name = source.command.name if source.command else "Unknown Command"
                user_info = f"{source.author} ({source.author.id})"
                guild_info = f"{source.guild.name} ({source.guild.id})" if source.guild else "DM"

            embed = discord.Embed(
                title="🚨 Unhandled Exception",
                description=f"**Command:** {command_name}\n**User:** {user_info}\n**Guild:** {guild_info}\n\n**Traceback:**\n```py\n{tb}\n```",
                color=discord.Color.dark_red(),
                timestamp=discord.utils.utcnow()
            )

            await owner.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send error log to owner: {e}")

async def setup(bot):
    cog = Reporting(bot)
    await bot.add_cog(cog)
    # Register app command error handler
    bot.tree.on_error = cog.on_app_command_error
