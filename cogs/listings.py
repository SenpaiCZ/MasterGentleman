import discord
from discord.ext import commands
from discord import app_commands
import database
import services.matcher as matcher
import views.trade
import logging

logger = logging.getLogger('discord')

class Listings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _create_trade_channel(self, guild: discord.Guild, trade_id: int, listing_a_id: int, listing_b: dict):
        """Creates a private trade channel and notifies users."""
        try:
            # Get listing details
            listing_a = await database.get_listing(listing_a_id)
            # listing_b is already fetched as dict (Row)

            user_a = guild.get_member(listing_a['user_id'])
            user_b = guild.get_member(listing_b['user_id'])

            if not user_a or not user_b:
                logger.warning(f"Could not find members for trade {trade_id}: {listing_a['user_id']}, {listing_b['user_id']}")
                # Wait, if members left, we can't create channel for them.
                # Should we cancel trade? Ideally yes.
                # For now, just try to create channel for whoever is there.

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }

            if user_a:
                overwrites[user_a] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            if user_b:
                overwrites[user_b] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            channel_name = f"trade-{listing_a['pokemon_id']}-{listing_b['pokemon_id']}"
            channel = await guild.create_text_channel(channel_name, overwrites=overwrites, reason="Trade Match")

            # Update DB with channel ID
            await database.update_trade_channel(trade_id, channel.id)

            # Send Embed
            embed = discord.Embed(title="🤝 Shoda Obchodu! (Trade Match!)", description="Byla nalezena shoda pro vaši nabídku/poptávku.", color=discord.Color.green())

            desc_a = f"#{listing_a['pokemon_id']} {'✨' if listing_a['is_shiny'] else ''} {'🕊️' if listing_a['is_purified'] else ''} {listing_a['details'] or ''}"
            desc_b = f"#{listing_b['pokemon_id']} {'✨' if listing_b['is_shiny'] else ''} {'🕊️' if listing_b['is_purified'] else ''} {listing_b['details'] or ''}"

            embed.add_field(name=f"Uživatel A ({user_a.display_name if user_a else 'Unknown'})", value=f"{listing_a['listing_type']}: {desc_a}", inline=False)
            embed.add_field(name=f"Uživatel B ({user_b.display_name if user_b else 'Unknown'})", value=f"{listing_b['listing_type']}: {desc_b}", inline=False)

            embed.set_footer(text="Dohodněte se na výměně zde. Až bude hotovo, stiskněte 'Obchod Dokončen'.")

            await channel.send(
                content=f"{user_a.mention if user_a else ''} {user_b.mention if user_b else ''}",
                embed=embed,
                view=views.trade.TradeView() # Using the Persistent View logic (custom_id)
            )

            logger.info(f"Created trade channel {channel.id} for trade {trade_id}")

        except Exception as e:
            logger.error(f"Error creating trade channel: {e}")
            # Should revert trade if possible?
            # For MVP, just log error. Ideally we set trade to ERROR or verify permissions.

    async def _handle_listing_creation(self, interaction: discord.Interaction, listing_type: str, pokemon_id: int, shiny: bool, purified: bool, popis: str):
        if pokemon_id < 1 or pokemon_id > 2000:
            await interaction.response.send_message("Neplatné číslo Pokémona. (Invalid Pokemon ID)", ephemeral=True)
            return

        try:
            listing_id = await database.add_listing(
                user_id=interaction.user.id,
                listing_type=listing_type,
                pokemon_id=pokemon_id,
                is_shiny=shiny,
                is_purified=purified,
                details=popis
            )

            shiny_str = "✨ Shiny" if shiny else ""
            purified_str = "🕊️ Purified" if purified else ""
            details_str = f"| {popis}" if popis else ""
            type_str = "Nabízím" if listing_type == 'HAVE' else "Hledám"

            await interaction.response.send_message(
                f"✅ **{type_str} vytvořena!** (ID: {listing_id})\n"
                f"{type_str}: Pokémon #{pokemon_id} {shiny_str} {purified_str} {details_str}",
                ephemeral=False
            )
            logger.info(f"User {interaction.user.id} added listing {listing_type} #{pokemon_id} (ID: {listing_id})")

            # Check for matches
            if interaction.guild:
                trade_id, match = await matcher.find_match(listing_id)
                if trade_id:
                    await self._create_trade_channel(interaction.guild, trade_id, listing_id, match)
            else:
                # If in DM, we can't create channel easily without knowing the guild context.
                # Assuming bot is used in a server.
                pass

        except Exception as e:
            logger.error(f"Error adding listing: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Nastala chyba při vytváření záznamu.", ephemeral=True)


    @app_commands.command(name="nabidka", description="Nabídni Pokémona k výměně (Offer a Pokemon)")
    @app_commands.describe(
        pokemon_id="Číslo Pokémona (Pokédex ID)",
        shiny="Je shiny? (Is it shiny?)",
        purified="Je purified? (Is it purified?)",
        popis="Další detaily (kostým, útoky, atd.) - volitelné"
    )
    async def nabidka(self, interaction: discord.Interaction, pokemon_id: int, shiny: bool = False, purified: bool = False, popis: str = None):
        """Vytvoří novou nabídku (HAVE)."""
        await self._handle_listing_creation(interaction, 'HAVE', pokemon_id, shiny, purified, popis)

    @app_commands.command(name="poptavka", description="Hledám Pokémona (Request a Pokemon)")
    @app_commands.describe(
        pokemon_id="Číslo Pokémona (Pokédex ID)",
        shiny="Je shiny? (Is it shiny?)",
        purified="Je purified? (Is it purified?)",
        popis="Další detaily (kostým, útoky, atd.) - volitelné"
    )
    async def poptavka(self, interaction: discord.Interaction, pokemon_id: int, shiny: bool = False, purified: bool = False, popis: str = None):
        """Vytvoří novou poptávku (WANT)."""
        await self._handle_listing_creation(interaction, 'WANT', pokemon_id, shiny, purified, popis)

    @app_commands.command(name="seznam", description="Zobrazit mé aktivní nabídky a poptávky")
    async def seznam(self, interaction: discord.Interaction):
        """Zobrazí seznam aktivních záznamů uživatele."""
        try:
            listings = await database.get_user_listings(interaction.user.id)

            if not listings:
                await interaction.response.send_message("Nemáte žádné aktivní nabídky ani poptávky.", ephemeral=True)
                return

            embed = discord.Embed(title="Moje Seznamy (My Lists)", color=discord.Color.blue())

            nabidky_text = ""
            poptavky_text = ""

            for l in listings:
                l_id = l['id']
                l_type = l['listing_type']
                p_id = l['pokemon_id']
                shiny = "✨" if l['is_shiny'] else ""
                purified = "🕊️" if l['is_purified'] else ""
                details = f"({l['details']})" if l['details'] else ""

                line = f"**#{l_id}** | Pokémon #{p_id} {shiny} {purified} {details}\n"

                if l_type == 'HAVE':
                    nabidky_text += line
                else:
                    poptavky_text += line

            if nabidky_text:
                embed.add_field(name="📥 Nabízím (HAVE)", value=nabidky_text, inline=False)
            if poptavky_text:
                embed.add_field(name="📤 Hledám (WANT)", value=poptavky_text, inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error fetching listings: {e}")
            await interaction.response.send_message("❌ Nastala chyba při načítání seznamu.", ephemeral=True)

    @app_commands.command(name="smazat", description="Smazat nabídku nebo poptávku podle ID")
    @app_commands.describe(id_zaznamu="ID záznamu k smazání")
    async def smazat(self, interaction: discord.Interaction, id_zaznamu: int):
        """Smaže záznam, pokud patří uživateli."""
        try:
            listing = await database.get_listing(id_zaznamu)

            if not listing:
                await interaction.response.send_message(f"Záznam s ID {id_zaznamu} neexistuje.", ephemeral=True)
                return

            if listing['user_id'] != interaction.user.id:
                await interaction.response.send_message("Tento záznam vám nepatří.", ephemeral=True)
                return

            if listing['status'] == 'PENDING':
                await interaction.response.send_message("⛔ Nemůžete smazat nabídku, která je součástí probíhajícího obchodu. Nejprve zrušte obchod v kanálu.", ephemeral=True)
                return

            await database.delete_listing(id_zaznamu)
            await interaction.response.send_message(f"🗑️ Záznam #{id_zaznamu} byl smazán.", ephemeral=True)
            logger.info(f"User {interaction.user.id} deleted listing {id_zaznamu}")

        except Exception as e:
            logger.error(f"Error deleting listing: {e}")
            await interaction.response.send_message("❌ Nastala chyba při mazání záznamu.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Listings(bot))
