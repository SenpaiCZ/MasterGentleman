import discord
from discord.ext import commands
from discord import app_commands, ui
import database
import logging

logger = logging.getLogger('discord')

class SuggestionModal(ui.Modal, title="Návrh na vylepšení (Suggestion)"):
    description = ui.TextInput(
        label="Popis návrhu",
        placeholder="Popište, co byste chtěli přidat nebo zlepšit...",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=2000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Fetch config
        config = await database.get_guild_config(interaction.guild_id)

        if not config or not config.get('suggestion_channel_id'):
            await interaction.response.send_message("❌ Kanál pro návrhy není nastaven. Kontaktujte administrátora.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(config['suggestion_channel_id'])
        if not channel:
            await interaction.response.send_message("❌ Kanál pro návrhy již neexistuje.", ephemeral=True)
            return

        up_emoji = config.get('upvote_emoji', '👍')
        down_emoji = config.get('downvote_emoji', '👎')

        embed = discord.Embed(
            title="💡 Nový Návrh (New Suggestion)",
            description=self.description.value,
            color=discord.Color.gold(),
            timestamp=interaction.created_at
        )
        embed.set_author(name=f"{interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"User ID: {interaction.user.id}")

        try:
            msg = await channel.send(embed=embed)
            # Add reactions
            try:
                await msg.add_reaction(up_emoji)
                await msg.add_reaction(down_emoji)
            except Exception as e:
                logger.error(f"Failed to add reactions to suggestion: {e}")
                # Fallback to standard emojis if custom ones fail
                await msg.add_reaction("👍")
                await msg.add_reaction("👎")

            await interaction.response.send_message("✅ Váš návrh byl odeslán k hlasování!", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to post suggestion: {e}")
            await interaction.response.send_message("❌ Nepodařilo se odeslat návrh.", ephemeral=True)

class Suggestions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="navrh", description="Odeslat návrh na vylepšení bota nebo serveru")
    async def navrh(self, interaction: discord.Interaction):
        """Otevře formulář pro odeslání návrhu."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Tento příkaz funguje pouze na serveru.", ephemeral=True)
            return

        await interaction.response.send_modal(SuggestionModal())

async def setup(bot):
    await bot.add_cog(Suggestions(bot))
