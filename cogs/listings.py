import discord
from discord.ext import commands
from discord import app_commands, ui
import database
import services.matcher as matcher
import views.trade
from views.listing import ListingDraftView, ListingManagementView
import logging
# from data.pokemon import POKEMON_NAMES, POKEMON_IDS, POKEMON_IMAGES # REMOVED: Using DB now
import functools

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

class Listings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _format_attributes(self, l):
        # l can be a dict.
        attrs = []
        if l.get('is_shiny'): attrs.append("✨")
        if l.get('is_purified'): attrs.append("🕊️")
        if l.get('is_dynamax'): attrs.append("Dyna")
        if l.get('is_gigantamax'): attrs.append("Giga")
        if l.get('is_background'): attrs.append("🌍")
        if l.get('is_adventure_effect'): attrs.append("🪄")
        if l.get('is_mirror'): attrs.append("🪞")
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
            # listing now contains joined fields from pokemon_species
            l_type = l['listing_type']
            acc_name = l['account_name']

            # Use name from DB
            p_name = l.get('pokemon_name', 'Unknown')
            # Append form if not Normal?
            if l.get('pokemon_form') and l.get('pokemon_form') != 'Normal':
                p_name += f" ({l['pokemon_form']})"

            attrs = self._format_attributes(l)
            details = f"({l['details']})" if l['details'] else ""

            # Truncate if too long (Discord limits)
            line = f"[{acc_name}] | {p_name} {attrs} {details}\n"

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

    def _create_single_listing_embed(self, listing):
        """Creates an embed for a single listing (for public posting)."""
        # listing dict must contain joined pokemon details or be constructed manually

        pokemon_name = listing.get('pokemon_name', 'Unknown')
        if listing.get('pokemon_form') and listing.get('pokemon_form') != 'Normal':
            pokemon_name += f" ({listing['pokemon_form']})"

        attrs_str = self._format_attributes(listing)
        details_str = f"| {listing['details']}" if listing['details'] else ""

        type_str = "Nabídka" if listing['listing_type'] == 'HAVE' else "Poptávka"
        acc_name = listing.get('account_name', 'Unknown')

        embed = discord.Embed(
            title=f"✅ {type_str} vytvořena!",
            description=f"{type_str}: {pokemon_name} {attrs_str} {details_str}",
            color=discord.Color.green()
        )
        embed.add_field(name="Účet", value=f"{acc_name}", inline=False)

        # Get Image from DB or constructed object
        img_url = listing.get('image_url')
        # If shiny, we might need to adjust URL if we were using external logic,
        # but for now we store generic URL in species.
        # The previous system used POKEMON_IMAGES dictionary with 'shiny' key.
        # pokemondb.net images are usually normal.
        # If we want shiny images, we might need a different source or the old dictionary if we kept it.
        # But we deleted data/pokemon.py usage.
        # Let's use the image_url from DB (species).

        # NOTE: pokemondb images are "icon" sprites usually.
        # If we want shiny, we might need to rely on the old method OR just show normal.
        # For now, show normal (or whatever is in DB).
        if img_url:
            embed.set_thumbnail(url=img_url)

        return embed

    async def pokemon_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()

        results = await database.search_pokemon_species(current, limit=25)
        choices = []
        for r in results:
            name = r['name']
            if r['form'] != 'Normal':
                name += f" ({r['form']})"

            # Value should probably be the name+form to be parsed later, OR the ID if we can pass it?
            # app_commands.Choice value must be str or int/float.
            # If we pass ID as value, the command handler receives the ID.
            # But the user sees the name.
            # Let's pass the ID as string.

            # actually, if we pass ID, the "pokemon" argument in command function will receive that string ID.
            # We need to handle that.

            choices.append(app_commands.Choice(name=name, value=str(r['id'])))

        return choices

    async def _create_trade_channel(self, guild: discord.Guild, trade_id: int, listing_a_id: int, listing_b: dict):
        """Creates a private trade channel and notifies users."""
        try:
            listing_a = await database.get_listing(listing_a_id)
            # listing_b is already dict

            user_a = guild.get_member(listing_a['user_id'])
            user_b = guild.get_member(listing_b['user_id'])

            if not user_a or not user_b:
                logger.warning(f"Could not find members for trade {trade_id}")

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }

            if user_a: overwrites[user_a] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            if user_b: overwrites[user_b] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            name_a = listing_a.get('pokemon_name', 'Unknown')
            name_b = listing_b.get('pokemon_name', 'Unknown')

            # Sanitize
            safe_name_a = name_a.replace(" ", "-").lower()
            safe_name_b = name_b.replace(" ", "-").lower()

            channel_name = f"trade-{safe_name_a}-{safe_name_b}"

            category = None
            config = await database.get_guild_config(guild.id)
            if config and config['trade_category_id']:
                category = guild.get_channel(config['trade_category_id'])

            channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=category, reason="Trade Match")
            await database.update_trade_channel(trade_id, channel.id)

            embed_color = await get_user_team_color(listing_a['user_id'])
            embed = discord.Embed(title="🤝 Shoda Obchodu! (Trade Match!)", description="Byla nalezena shoda pro vaši nabídku/poptávku.", color=embed_color)

            # Image (A)
            if listing_a.get('image_url'):
                embed.set_thumbnail(url=listing_a['image_url'])

            attrs_a = self._format_attributes(listing_a)
            attrs_b = self._format_attributes(listing_b)

            desc_a = f"{name_a} {attrs_a} {listing_a['details'] or ''}"
            desc_b = f"{name_b} {attrs_b} {listing_b['details'] or ''}"

            acc_a = f"{listing_a['account_name']} (FC: {listing_a['friend_code']})"
            acc_b = f"{listing_b['account_name']} (FC: {listing_b['friend_code']})"

            name_display_a = user_a.display_name if user_a else 'Unknown'
            name_display_b = user_b.display_name if user_b else 'Unknown'

            embed.add_field(name=f"Uživatel A: {name_display_a}", value=f"**Účet:** {acc_a}\n{listing_a['listing_type']}: {desc_a}", inline=False)
            embed.add_field(name=f"Uživatel B: {name_display_b}", value=f"**Účet:** {acc_b}\n{listing_b['listing_type']}: {desc_b}", inline=False)

            embed.set_footer(text="Dohodněte se na výměně zde. Až bude hotovo, stiskněte 'Obchod Dokončen'.")

            view = views.trade.TradeView()
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

        except Exception as e:
            logger.error(f"Error creating trade channel: {e}")

    async def create_listing_final(self, interaction: discord.Interaction, account_id: int, listing_type: str, pokemon_id: int, pokemon_name: str,
                                   shiny: bool, purified: bool,
                                   dynamax: bool, gigantamax: bool, background: bool, adventure_effect: bool,
                                   is_mirror: bool,
                                   popis: str,
                                   old_listing_id: int = None):
        # NOTE: 'pokemon_id' arg here is now 'species_id' from database
        species_id = pokemon_id

        try:
            listing_id = await database.add_listing(
                user_id=interaction.user.id,
                account_id=account_id,
                listing_type=listing_type,
                species_id=species_id, # CHANGED
                is_shiny=shiny,
                is_purified=purified,
                is_dynamax=dynamax,
                is_gigantamax=gigantamax,
                is_background=background,
                is_adventure_effect=adventure_effect,
                is_mirror=is_mirror,
                details=popis,
                guild_id=interaction.guild_id if interaction.guild else None
            )

            type_str = "Nabídka" if listing_type == 'HAVE' else "Poptávka"
            account = await database.get_account(account_id)

            # Fetch species details for embed
            # We can't use get_listing immediately if we haven't committed?
            # add_listing commits.

            # But we can just construct the dict if we have the name, or fetch species.
            # Use database.get_listing to be sure to get joined data.
            full_listing = await database.get_listing(listing_id)

            embed = self._create_single_listing_embed(full_listing)

            target_channel = interaction.channel
            config = None
            if interaction.guild:
                config = await database.get_guild_config(interaction.guild.id)

            if config:
                if listing_type == 'HAVE' and config['have_channel_id']:
                    ch = interaction.guild.get_channel(config['have_channel_id'])
                    if ch: target_channel = ch
                elif listing_type == 'WANT' and config['want_channel_id']:
                    ch = interaction.guild.get_channel(config['want_channel_id'])
                    if ch: target_channel = ch

            msg_loc = ""
            sent_message = None
            if target_channel:
                try:
                    sent_message = await target_channel.send(content=interaction.user.mention, embed=embed)
                    if target_channel != interaction.channel:
                        msg_loc = f" do kanálu {target_channel.mention}"
                except Exception as e:
                    logger.error(f"Failed to send public msg: {e}")
                    if target_channel != interaction.channel and interaction.channel:
                         try:
                            sent_message = await interaction.channel.send(content=interaction.user.mention, embed=embed)
                         except: pass

            if sent_message:
                await database.update_listing_message(listing_id, sent_message.id, sent_message.channel.id)

            if old_listing_id:
                old_l = await database.get_listing(old_listing_id)
                if old_l:
                    if old_l['channel_id'] and old_l['message_id']:
                        try:
                            ch = self.bot.get_channel(old_l['channel_id'])
                            if not ch: ch = await self.bot.fetch_channel(old_l['channel_id'])
                            if ch:
                                msg = await ch.fetch_message(old_l['message_id'])
                                await msg.delete()
                        except: pass
                    await database.delete_listing(old_listing_id)

            if not interaction.response.is_done():
                 await interaction.response.send_message(f"✅ Záznam byl úspěšně zveřejněn{msg_loc}.", ephemeral=True)
            else:
                 await interaction.followup.send(f"✅ Záznam byl úspěšně zveřejněn{msg_loc}.", ephemeral=True)

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

    async def _handle_listing_creation(self, interaction: discord.Interaction, listing_type: str, pokemon: str, popis: str):
        # pokemon is now expected to be the Species ID (as string) from autocomplete
        # OR a raw name if user typed something else.

        species_id = None
        pokemon_name = ""

        if pokemon.isdigit():
            species_id = int(pokemon)
            # Fetch name
            # We don't have get_species_by_id yet exposed in this Cog, but we can query or trust it exists
            # Ideally verify.
            # Let's add get_pokemon_species_by_id to database.py?
            # Or just use raw sql here? Better to be safe.
            # Assuming if it's digit, it's from autocomplete.

            # We can use database.get_db() context to verify
            # Or just let the ListingDraftView handle visual confirmation.

            # We need the name for the View title though.
            # ListingDraftView constructor expects pokemon_name.
            pass
        else:
            # Try to resolve by name
            row = await database.get_pokemon_species_by_name(pokemon)
            if row:
                species_id = row['id']
                pokemon_name = row['name']
                if row['form'] != 'Normal':
                    pokemon_name += f" ({row['form']})"
            else:
                await interaction.response.send_message(f"❌ Neznámý Pokémon '{pokemon}'. Prosím vyberte ze seznamu.", ephemeral=True)
                return

        # If we have species_id but not name (from autocomplete ID)
        if species_id and not pokemon_name:
             # We need to fetch the name.
             async with await database.get_db() as db:
                 async with db.execute("SELECT name, form FROM pokemon_species WHERE id = ?", (species_id,)) as cursor:
                     row = await cursor.fetchone()
                     if row:
                         pokemon_name = row['name']
                         if row['form'] != 'Normal':
                             pokemon_name += f" ({row['form']})"
                     else:
                         await interaction.response.send_message("❌ Chyba: Pokémon nenalezen v DB.", ephemeral=True)
                         return

        accounts = await database.get_user_accounts(interaction.user.id)
        if not accounts:
            await interaction.response.send_message("❌ Nemáte registrovaný žádný účet. Použijte `/registrace`.", ephemeral=True)
            return

        view = ListingDraftView(
            interaction,
            listing_type,
            species_id, # passing species_id as pokemon_id
            pokemon_name,
            accounts,
            initial_details=popis,
            submit_callback=self.create_listing_final
        )

        # Load capabilities from DB to disable/enable buttons in View?
        # ListingDraftView currently defaults all enabled.
        # Future improvement: pass capabilities to View.

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

    # --- My Listings Management ---
    moje_group = app_commands.Group(name="moje", description="Správa mých záznamů (Manage my listings)")

    @moje_group.command(name="nabidky", description="Spravovat mé nabídky (Manage My Offers)")
    async def moje_nabidky(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._show_management_view(interaction, 'HAVE')

    @moje_group.command(name="poptavky", description="Spravovat mé poptávky (Manage My Requests)")
    async def moje_poptavky(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._show_management_view(interaction, 'WANT')

    async def _show_management_view(self, interaction: discord.Interaction, listing_type: str):
        all_listings = await database.get_user_listings(interaction.user.id)
        listings = [l for l in all_listings if l['listing_type'] == listing_type]

        if not listings:
            await interaction.followup.send(f"Nemáte žádné aktivní záznamy typu {listing_type}.", ephemeral=True)
            return

        callbacks = {
            'delete': self._delete_listing_callback,
            'edit_details': self._edit_details_callback,
            'edit_all': self._edit_all_callback
        }

        view = ListingManagementView(listings, callbacks)
        embed = self._create_listings_embed(listings, await get_user_team_color(interaction.user.id))
        title_prefix = "Moje Nabídky" if listing_type == 'HAVE' else "Moje Poptávky"
        embed.title = f"{title_prefix} (My Listings)"

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _delete_listing_callback(self, interaction: discord.Interaction, listing_id: int, view: ListingManagementView):
        listing = await database.get_listing(listing_id)
        if not listing:
            await interaction.response.send_message("Záznam již neexistuje.", ephemeral=True)
            return

        if listing['channel_id'] and listing['message_id']:
            try:
                channel = self.bot.get_channel(listing['channel_id'])
                if not channel: channel = await self.bot.fetch_channel(listing['channel_id'])
                if channel:
                    msg = await channel.fetch_message(listing['message_id'])
                    await msg.delete()
            except: pass

        await database.delete_listing(listing_id)

        # We need to remove it from view.listings
        view.listings = [l for l in view.listings if l['id'] != listing_id]

        if not view.listings:
            await interaction.response.edit_message(content="✅ Záznam smazán. Seznam je prázdný.", embed=None, view=None)
            return

        new_view = ListingManagementView(view.listings, view.callbacks)
        embed = self._create_listings_embed(view.listings, await get_user_team_color(interaction.user.id))

        await interaction.response.edit_message(content="✅ Záznam smazán.", embed=embed, view=new_view)

    async def _edit_details_callback(self, interaction: discord.Interaction, listing_id: int, new_details: str, view: ListingManagementView):
        await database.update_listing_details(listing_id, new_details)

        listing = await database.get_listing(listing_id)
        if listing['channel_id'] and listing['message_id']:
            try:
                channel = self.bot.get_channel(listing['channel_id'])
                if not channel: channel = await self.bot.fetch_channel(listing['channel_id'])
                if channel:
                    msg = await channel.fetch_message(listing['message_id'])
                    embed = self._create_single_listing_embed(listing)
                    await msg.edit(embed=embed)
            except: pass

        # Refresh
        all_listings = await database.get_user_listings(interaction.user.id)
        current_type = listing['listing_type']
        listings = [l for l in all_listings if l['listing_type'] == current_type]

        new_view = ListingManagementView(listings, view.callbacks)
        embed_list = self._create_listings_embed(listings, await get_user_team_color(interaction.user.id))

        await interaction.response.edit_message(content="✅ Popis upraven.", embed=embed_list, view=new_view)

    async def _edit_all_callback(self, interaction: discord.Interaction, listing_id: int, view: ListingManagementView):
        listing = await database.get_listing(listing_id)
        if not listing:
             await interaction.response.send_message("Záznam neexistuje.", ephemeral=True)
             return

        # listing dict has pokemon_name from JOIN
        pokemon_name = listing.get('pokemon_name', "Unknown")
        if listing.get('pokemon_form') and listing.get('pokemon_form') != 'Normal':
            pokemon_name += f" ({listing['pokemon_form']})"

        accounts = await database.get_user_accounts(interaction.user.id)

        submit_cb = functools.partial(self.create_listing_final, old_listing_id=listing_id)

        draft_view = ListingDraftView(
            interaction,
            listing['listing_type'],
            listing['species_id'], # listing now has species_id column
            pokemon_name,
            accounts,
            initial_details=listing['details'],
            submit_callback=submit_cb
        )

        draft_view.is_shiny = bool(listing['is_shiny'])
        draft_view.is_purified = bool(listing['is_purified'])
        draft_view.is_dynamax = bool(listing['is_dynamax'])
        draft_view.is_gigantamax = bool(listing['is_gigantamax'])
        draft_view.is_background = bool(listing['is_background'])
        draft_view.is_adventure_effect = bool(listing['is_adventure_effect'])
        draft_view.is_mirror = bool(listing['is_mirror'])

        for acc in accounts:
            if acc['id'] == listing['account_id']:
                draft_view.selected_account_id = acc['id']
                draft_view.selected_account_name = acc['account_name']
                draft_view.selected_account_fc = acc['friend_code']
                break

        draft_view._update_components()
        embed = draft_view._get_embed()

        await interaction.response.edit_message(content=None, embed=embed, view=draft_view)

async def setup(bot):
    await bot.add_cog(Listings(bot))
