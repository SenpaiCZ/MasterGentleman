import discord
from discord.ext import commands
from discord import app_commands, ui
import database
import services.matcher as matcher
import views.trade
from views.listing import ListingDraftView, ListingManagementView
import logging
from data.pokemon import POKEMON_NAMES, POKEMON_IDS, POKEMON_IMAGES

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

class ListingConfirmationView(ui.View):
    def __init__(self, friend_code):
        super().__init__(timeout=None)
        self.friend_code = friend_code

    @ui.button(label="📋 Zkopírovat můj FC", style=discord.ButtonStyle.secondary)
    async def copy_fc(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(f"{self.friend_code}", ephemeral=True)

class Listings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _format_attributes(self, l):
        attrs = []
        if l.get('is_shiny'): attrs.append("✨")
        if l.get('is_purified'): attrs.append("🕊️")
        if l.get('is_dynamax'): attrs.append("Dyna")
        if l.get('is_gigantamax'): attrs.append("Giga")
        if l.get('is_background'): attrs.append("🌍")
        if l.get('is_adventure_effect'): attrs.append("🪄")
        return " ".join(attrs)

    def _create_listings_embed(self, listings, user_team_color):
        embed = discord.Embed(title="Moje Seznamy (My Lists)", color=user_team_color)

        if not listings:
            embed.description = "Nemáte žádné aktivní nabídky ani poptávky."
            return embed

        # Group by Listing Type
        nabidky_text = ""
        poptavky_text = ""

        for l in listings:
            l_id = l['id']
            l_type = l['listing_type']
            p_id = l['pokemon_id']
            acc_name = l['account_name']

            p_name = POKEMON_IDS.get(p_id, f"Unknown #{p_id}")

            attrs = self._format_attributes(l)
            details = f"({l['details']})" if l['details'] else ""

            # Truncate if too long (Discord limits)
            line = f"**#{l_id}** [{acc_name}] | {p_name} {attrs} {details}\n"

            if l_type == 'HAVE':
                if len(nabidky_text) + len(line) < 1000:
                    nabidky_text += line
            else:
                if len(poptavky_text) + len(line) < 1000:
                    poptavky_text += line

        if nabidky_text:
            embed.add_field(name="📥 Nabízím (HAVE)", value=nabidky_text, inline=False)
        if poptavky_text:
            embed.add_field(name="📤 Hledám (WANT)", value=poptavky_text, inline=False)

        return embed

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

            # Determine Embed Color (User A's team)
            embed_color = await get_user_team_color(listing_a['user_id'])

            # Send Embed
            embed = discord.Embed(title="🤝 Shoda Obchodu! (Trade Match!)", description="Byla nalezena shoda pro vaši nabídku/poptávku.", color=embed_color)

            # Get Image
            img_info = POKEMON_IMAGES.get(listing_a['pokemon_id'])
            if img_info:
                # Use Listing A's shiny preference as default
                img_url = img_info.get('shiny') if listing_a['is_shiny'] else img_info.get('normal')
                if not img_url:
                    img_url = img_info.get('normal')
                if img_url:
                    embed.set_thumbnail(url=img_url)

            attrs_a = self._format_attributes(listing_a)
            attrs_b = self._format_attributes(listing_b)

            desc_a = f"{name_a} {attrs_a} {listing_a['details'] or ''}"
            desc_b = f"{name_b} {attrs_b} {listing_b['details'] or ''}"

            # Add Account info
            acc_a = f"{listing_a['account_name']} (FC: {listing_a['friend_code']})"
            acc_b = f"{listing_b['account_name']} (FC: {listing_b['friend_code']})"

            name_display_a = user_a.display_name if user_a else 'Unknown'
            name_display_b = user_b.display_name if user_b else 'Unknown'

            embed.add_field(name=f"Uživatel A: {name_display_a}", value=f"**Účet:** {acc_a}\n{listing_a['listing_type']}: {desc_a}", inline=False)
            embed.add_field(name=f"Uživatel B: {name_display_b}", value=f"**Účet:** {acc_b}\n{listing_b['listing_type']}: {desc_b}", inline=False)

            embed.set_footer(text="Dohodněte se na výměně zde. Až bude hotovo, stiskněte 'Obchod Dokončen'.")

            # Customize Buttons
            view = views.trade.TradeView()

            # Find and update buttons
            for child in view.children:
                if child.custom_id == "trade_copy_fc_a":
                    child.label = f"📋 FC {name_display_a}"
                elif child.custom_id == "trade_copy_fc_b":
                    child.label = f"📋 FC {name_display_b}"

            await channel.send(
                content=f"{user_a.mention if user_a else ''} {user_b.mention if user_b else ''}",
                embed=embed,
                view=view
            )

            logger.info(f"Created trade channel {channel.id} for trade {trade_id}")

        except Exception as e:
            logger.error(f"Error creating trade channel: {e}")

    async def create_listing_final(self, interaction: discord.Interaction, account_id: int, listing_type: str, pokemon_id: int, pokemon_name: str,
                                   shiny: bool, purified: bool,
                                   dynamax: bool, gigantamax: bool, background: bool, adventure_effect: bool,
                                   popis: str):
        try:
            listing_id = await database.add_listing(
                user_id=interaction.user.id,
                account_id=account_id,
                listing_type=listing_type,
                pokemon_id=pokemon_id,
                is_shiny=shiny,
                is_purified=purified,
                is_dynamax=dynamax,
                is_gigantamax=gigantamax,
                is_background=background,
                is_adventure_effect=adventure_effect,
                details=popis
            )

            attrs_map = {
                'is_shiny': shiny, 'is_purified': purified,
                'is_dynamax': dynamax, 'is_gigantamax': gigantamax,
                'is_background': background, 'is_adventure_effect': adventure_effect
            }
            attrs_str = self._format_attributes(attrs_map)
            details_str = f"| {popis}" if popis else ""
            type_str = "Nabízím" if listing_type == 'HAVE' else "Hledám"

            # Fetch account name for confirmation
            account = await database.get_account(account_id)
            acc_name = account['account_name'] if account else "Unknown"
            friend_code = account['friend_code'] if account else "Unknown"

            # Construct confirmation embed
            embed = discord.Embed(
                title=f"✅ {type_str} vytvořena! (ID: {listing_id})",
                description=f"{type_str}: {pokemon_name} {attrs_str} {details_str}",
                color=discord.Color.green()
            )
            embed.add_field(name="Účet", value=f"{acc_name}", inline=False)

            # Get Image
            img_info = POKEMON_IMAGES.get(pokemon_id)
            if img_info:
                img_url = img_info.get('shiny') if shiny else img_info.get('normal')
                if not img_url:
                    img_url = img_info.get('normal')
                if img_url:
                    embed.set_thumbnail(url=img_url)

            view = ListingConfirmationView(friend_code)

            # Determine target channel from config
            target_channel = interaction.channel
            config = None
            if interaction.guild:
                config = await database.get_guild_config(interaction.guild.id)

            if config:
                if listing_type == 'HAVE' and config['have_channel_id']:
                    ch = interaction.guild.get_channel(config['have_channel_id'])
                    if ch:
                        target_channel = ch
                elif listing_type == 'WANT' and config['want_channel_id']:
                    ch = interaction.guild.get_channel(config['want_channel_id'])
                    if ch:
                        target_channel = ch

            # Send the PUBLIC message to the channel so others can see it
            msg_loc = ""
            if target_channel:
                try:
                    await target_channel.send(embed=embed, view=view)
                    if target_channel != interaction.channel:
                        msg_loc = f" do kanálu {target_channel.mention}"
                except Exception as e:
                    logger.error(f"Failed to send to target channel {target_channel.id}: {e}")
                    # Try fallback to current channel if different
                    if target_channel != interaction.channel and interaction.channel:
                        try:
                            await interaction.channel.send(embed=embed, view=view)
                        except:
                            pass
            else:
                logger.warning(f"Could not send public message for listing {listing_id} - no channel.")

            # Notify the user via ephemeral followup that it's done
            await interaction.followup.send(f"✅ Záznam byl úspěšně zveřejněn{msg_loc}.", ephemeral=True)

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

    async def _handle_listing_creation(self, interaction: discord.Interaction, listing_type: str, pokemon_name: str, popis: str):
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

        view = ListingDraftView(
            interaction,
            listing_type,
            pokemon_id,
            pokemon_name,
            accounts,
            initial_details=popis,
            submit_callback=self.create_listing_final
        )

        embed = view._get_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="nabidka", description="Nabídni Pokémona k výměně (Offer a Pokemon)")
    @app_commands.describe(
        pokemon="Jméno Pokémona (začněte psát pro našeptávač)",
        popis="Další detaily (kostým, útoky, atd.) - volitelné"
    )
    @app_commands.autocomplete(pokemon=pokemon_autocomplete)
    async def nabidka(self, interaction: discord.Interaction, pokemon: str, popis: str = None):
        """Vytvoří novou nabídku (HAVE)."""
        await self._handle_listing_creation(interaction, 'HAVE', pokemon, popis)

    @app_commands.command(name="poptavka", description="Hledám Pokémona (Request a Pokemon)")
    @app_commands.describe(
        pokemon="Jméno Pokémona (začněte psát pro našeptávač)",
        popis="Další detaily (kostým, útoky, atd.) - volitelné"
    )
    @app_commands.autocomplete(pokemon=pokemon_autocomplete)
    async def poptavka(self, interaction: discord.Interaction, pokemon: str, popis: str = None):
        """Vytvoří novou poptávku (WANT)."""
        await self._handle_listing_creation(interaction, 'WANT', pokemon, popis)

    @app_commands.command(name="seznam", description="Zobrazit mé aktivní nabídky a poptávky")
    async def seznam(self, interaction: discord.Interaction):
        """Zobrazí seznam aktivních záznamů uživatele."""
        try:
            listings = await database.get_user_listings(interaction.user.id)
            embed_color = await get_user_team_color(interaction.user.id)

            embed = self._create_listings_embed(listings, embed_color)

            view = None
            if listings:
                embed_callback = lambda new_listings: self._create_listings_embed(new_listings, embed_color)
                view = ListingManagementView(listings, interaction.user.id, embed_callback)

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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
