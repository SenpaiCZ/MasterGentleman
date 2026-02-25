import discord
from discord.ext import commands
from discord import app_commands, ui
import database
import services.matcher as matcher
import views.trade
import logging
from data.pokemon import POKEMON_NAMES, POKEMON_IDS

logger = logging.getLogger('discord')

class AccountSelect(ui.Select):
    def __init__(self, accounts, listing_type, pokemon_id, pokemon_name, is_shiny, is_purified, details):
        self.listing_type = listing_type
        self.pokemon_id = pokemon_id
        self.pokemon_name = pokemon_name
        self.is_shiny = is_shiny
        self.is_purified = is_purified
        self.details = details

        options = []
        for acc in accounts:
            label = f"{acc['account_name']} ({acc['friend_code']})"
            if acc['is_main']:
                label = "⭐ " + label
            options.append(discord.SelectOption(label=label, value=str(acc['id'])))

        super().__init__(placeholder="Vyberte účet pro tuto nabídku", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        account_id = int(self.values[0])

        # Call the logic to actually create listing
        cog = interaction.client.get_cog("Listings")
        if cog:
            # We defer update to avoid "interaction failed" and allow followups
            await interaction.response.edit_message(content=f"Vybrán účet. Vytvářím záznam...", view=None)
            await cog.create_listing_final(interaction, account_id, self.listing_type, self.pokemon_id, self.pokemon_name, self.is_shiny, self.is_purified, self.details)

class AccountSelectView(ui.View):
    def __init__(self, accounts, listing_type, pokemon_id, pokemon_name, is_shiny, is_purified, details):
        super().__init__()
        self.add_item(AccountSelect(accounts, listing_type, pokemon_id, pokemon_name, is_shiny, is_purified, details))

class Listings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def pokemon_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()
        choices = []
        # Prioritize starts with, then contains
        for name in POKEMON_NAMES.keys():
            if name.lower().startswith(current):
                choices.append(app_commands.Choice(name=name, value=name))
                if len(choices) >= 25:
                    return choices

        if len(choices) < 25:
            for name in POKEMON_NAMES.keys():
                if current in name.lower() and name not in [c.value for c in choices]:
                    choices.append(app_commands.Choice(name=name, value=name))
                    if len(choices) >= 25:
                        break

        return choices

    async def _create_trade_channel(self, guild: discord.Guild, trade_id: int, listing_a_id: int, listing_b: dict):
        """Creates a private trade channel and notifies users."""
        try:
            # Get listing details (now includes account info)
            listing_a = await database.get_listing(listing_a_id)
            # listing_b is already fetched as dict (Row)

            user_a = guild.get_member(listing_a['user_id'])
            user_b = guild.get_member(listing_b['user_id'])

            if not user_a or not user_b:
                logger.warning(f"Could not find members for trade {trade_id}: {listing_a['user_id']}, {listing_b['user_id']}")

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }

            if user_a:
                overwrites[user_a] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            if user_b:
                overwrites[user_b] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            name_a = POKEMON_IDS.get(listing_a['pokemon_id'], str(listing_a['pokemon_id']))
            name_b = POKEMON_IDS.get(listing_b['pokemon_id'], str(listing_b['pokemon_id']))

            # Sanitize channel name (lowercase, replace spaces)
            safe_name_a = name_a.replace(" ", "-").lower()
            safe_name_b = name_b.replace(" ", "-").lower()

            channel_name = f"trade-{safe_name_a}-{safe_name_b}"
            channel = await guild.create_text_channel(channel_name, overwrites=overwrites, reason="Trade Match")

            # Update DB with channel ID
            await database.update_trade_channel(trade_id, channel.id)

            # Send Embed
            embed = discord.Embed(title="🤝 Shoda Obchodu! (Trade Match!)", description="Byla nalezena shoda pro vaši nabídku/poptávku.", color=discord.Color.green())

            desc_a = f"{name_a} {'✨' if listing_a['is_shiny'] else ''} {'🕊️' if listing_a['is_purified'] else ''} {listing_a['details'] or ''}"
            desc_b = f"{name_b} {'✨' if listing_b['is_shiny'] else ''} {'🕊️' if listing_b['is_purified'] else ''} {listing_b['details'] or ''}"

            # Add Account info
            acc_a = f"{listing_a['account_name']} (FC: {listing_a['friend_code']})"
            acc_b = f"{listing_b['account_name']} (FC: {listing_b['friend_code']})"

            embed.add_field(name=f"Uživatel A ({user_a.display_name if user_a else 'Unknown'})", value=f"**Účet:** {acc_a}\n{listing_a['listing_type']}: {desc_a}", inline=False)
            embed.add_field(name=f"Uživatel B ({user_b.display_name if user_b else 'Unknown'})", value=f"**Účet:** {acc_b}\n{listing_b['listing_type']}: {desc_b}", inline=False)

            embed.set_footer(text="Dohodněte se na výměně zde. Až bude hotovo, stiskněte 'Obchod Dokončen'.")

            await channel.send(
                content=f"{user_a.mention if user_a else ''} {user_b.mention if user_b else ''}",
                embed=embed,
                view=views.trade.TradeView()
            )

            logger.info(f"Created trade channel {channel.id} for trade {trade_id}")

        except Exception as e:
            logger.error(f"Error creating trade channel: {e}")

    async def create_listing_final(self, interaction: discord.Interaction, account_id: int, listing_type: str, pokemon_id: int, pokemon_name: str, shiny: bool, purified: bool, popis: str):
        try:
            listing_id = await database.add_listing(
                user_id=interaction.user.id,
                account_id=account_id,
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

            # Fetch account name for confirmation
            account = await database.get_account(account_id)
            acc_name = account['account_name'] if account else "Unknown"

            msg = (
                f"✅ **{type_str} vytvořena!** (ID: {listing_id})\n"
                f"👤 **Účet:** {acc_name}\n"
                f"{type_str}: {pokemon_name} {shiny_str} {purified_str} {details_str}"
            )

            if interaction.response.is_done():
                 await interaction.followup.send(msg, ephemeral=False)
            else:
                 await interaction.response.send_message(msg, ephemeral=False)

            logger.info(f"User {interaction.user.id} added listing {listing_type} {pokemon_name} (#{pokemon_id}) for account {account_id} (ID: {listing_id})")

            # Check for matches
            if interaction.guild:
                trade_id, match = await matcher.find_match(listing_id)
                if trade_id:
                    await self._create_trade_channel(interaction.guild, trade_id, listing_id, match)

        except Exception as e:
            logger.error(f"Error adding listing: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Nastala chyba při vytváření záznamu.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Nastala chyba při vytváření záznamu.", ephemeral=True)

    async def _handle_listing_creation(self, interaction: discord.Interaction, listing_type: str, pokemon_name: str, shiny: bool, purified: bool, popis: str):
        # Resolve Pokemon ID
        pokemon_id = POKEMON_NAMES.get(pokemon_name.title())
        if not pokemon_id:
            for name, pid in POKEMON_NAMES.items():
                if name.lower() == pokemon_name.lower():
                    pokemon_id = pid
                    pokemon_name = name
                    break

        if not pokemon_id:
            if pokemon_name.isdigit():
                pokemon_id = int(pokemon_name)
                pokemon_name = POKEMON_IDS.get(pokemon_id, f"Unknown #{pokemon_id}")
            else:
                await interaction.response.send_message(f"❌ Neznámý Pokémon '{pokemon_name}'. Prosím vyberte ze seznamu.", ephemeral=True)
                return

        # Check for accounts
        accounts = await database.get_user_accounts(interaction.user.id)

        if not accounts:
            await interaction.response.send_message("❌ Nemáte registrovaný žádný účet. Použijte `/registrace`.", ephemeral=True)
            return

        if len(accounts) == 1:
            # Auto-select the only account
            await self.create_listing_final(interaction, accounts[0]['id'], listing_type, pokemon_id, pokemon_name, shiny, purified, popis)
        else:
            # Ask user to select account
            view = AccountSelectView(accounts, listing_type, pokemon_id, pokemon_name, shiny, purified, popis)
            await interaction.response.send_message("Vyberte účet, pro který chcete tuto nabídku vytvořit:", view=view, ephemeral=True)

    @app_commands.command(name="nabidka", description="Nabídni Pokémona k výměně (Offer a Pokemon)")
    @app_commands.describe(
        pokemon="Jméno Pokémona (začněte psát pro našeptávač)",
        shiny="Je shiny? (Is it shiny?)",
        purified="Je purified? (Is it purified?)",
        popis="Další detaily (kostým, útoky, atd.) - volitelné"
    )
    @app_commands.autocomplete(pokemon=pokemon_autocomplete)
    async def nabidka(self, interaction: discord.Interaction, pokemon: str, shiny: bool = False, purified: bool = False, popis: str = None):
        """Vytvoří novou nabídku (HAVE)."""
        await self._handle_listing_creation(interaction, 'HAVE', pokemon, shiny, purified, popis)

    @app_commands.command(name="poptavka", description="Hledám Pokémona (Request a Pokemon)")
    @app_commands.describe(
        pokemon="Jméno Pokémona (začněte psát pro našeptávač)",
        shiny="Je shiny? (Is it shiny?)",
        purified="Je purified? (Is it purified?)",
        popis="Další detaily (kostým, útoky, atd.) - volitelné"
    )
    @app_commands.autocomplete(pokemon=pokemon_autocomplete)
    async def poptavka(self, interaction: discord.Interaction, pokemon: str, shiny: bool = False, purified: bool = False, popis: str = None):
        """Vytvoří novou poptávku (WANT)."""
        await self._handle_listing_creation(interaction, 'WANT', pokemon, shiny, purified, popis)

    @app_commands.command(name="seznam", description="Zobrazit mé aktivní nabídky a poptávky")
    async def seznam(self, interaction: discord.Interaction):
        """Zobrazí seznam aktivních záznamů uživatele."""
        try:
            listings = await database.get_user_listings(interaction.user.id)

            if not listings:
                await interaction.response.send_message("Nemáte žádné aktivní nabídky ani poptávky.", ephemeral=True)
                return

            embed = discord.Embed(title="Moje Seznamy (My Lists)", color=discord.Color.blue())

            # Group by Listing Type, but mention Account
            nabidky_text = ""
            poptavky_text = ""

            for l in listings:
                l_id = l['id']
                l_type = l['listing_type']
                p_id = l['pokemon_id']
                acc_name = l['account_name']

                p_name = POKEMON_IDS.get(p_id, f"Unknown #{p_id}")

                shiny = "✨" if l['is_shiny'] else ""
                purified = "🕊️" if l['is_purified'] else ""
                details = f"({l['details']})" if l['details'] else ""

                line = f"**#{l_id}** [{acc_name}] | {p_name} {shiny} {purified} {details}\n"

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
