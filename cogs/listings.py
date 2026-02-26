import discord
from discord.ext import commands
from discord import app_commands, ui
import database
import services.matcher as matcher
import views.trade
from views.listing import ListingDraftView, ListingManagementView
import logging
from data.pokemon import POKEMON_NAMES, POKEMON_IDS, POKEMON_IMAGES
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
        # l can be a dict or Row.
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
            l_id = l['id']
            l_type = l['listing_type']
            p_id = l['pokemon_id']
            acc_name = l['account_name']

            p_name = POKEMON_IDS.get(p_id, f"Unknown #{p_id}")

            attrs = self._format_attributes(l)
            details = f"({l['details']})" if l['details'] else ""

            # Truncate if too long (Discord limits)
            # User requested ID removal from view
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
        pokemon_id = listing['pokemon_id']
        pokemon_name = POKEMON_IDS.get(pokemon_id, f"#{pokemon_id}")

        attrs_str = self._format_attributes(listing)
        details_str = f"| {listing['details']}" if listing['details'] else ""

        type_str = "Nabídka" if listing['listing_type'] == 'HAVE' else "Poptávka"
        acc_name = listing['account_name']

        embed = discord.Embed(
            title=f"✅ {type_str} vytvořena!",
            description=f"{type_str}: {pokemon_name} {attrs_str} {details_str}",
            color=discord.Color.green()
        )
        embed.add_field(name="Účet", value=f"{acc_name}", inline=False)

        # Get Image
        img_info = POKEMON_IMAGES.get(pokemon_id)
        if img_info:
            img_url = img_info.get('shiny') if listing['is_shiny'] else img_info.get('normal')
            if not img_url:
                img_url = img_info.get('normal')
            if img_url:
                embed.set_thumbnail(url=img_url)

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

            # Use Category if configured
            category = None
            config = await database.get_guild_config(guild.id)
            if config and config['trade_category_id']:
                category = guild.get_channel(config['trade_category_id'])

            channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=category, reason="Trade Match")

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
                                   is_mirror: bool,
                                   popis: str,
                                   old_listing_id: int = None):
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
                is_mirror=is_mirror,
                details=popis,
                guild_id=interaction.guild_id if interaction.guild else None
            )

            # Updated terminology
            type_str = "Nabídka" if listing_type == 'HAVE' else "Poptávka"

            # Fetch account name for confirmation
            account = await database.get_account(account_id)

            # Construct dictionary to use helper
            listing_data = {
                'listing_type': listing_type,
                'pokemon_id': pokemon_id,
                'is_shiny': shiny, 'is_purified': purified,
                'is_dynamax': dynamax, 'is_gigantamax': gigantamax,
                'is_background': background, 'is_adventure_effect': adventure_effect,
                'is_mirror': is_mirror,
                'details': popis,
                'account_name': account['account_name'] if account else "Unknown"
            }

            embed = self._create_single_listing_embed(listing_data)

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
            sent_message = None
            if target_channel:
                try:
                    # Added user mention to content
                    sent_message = await target_channel.send(content=interaction.user.mention, embed=embed)
                    if target_channel != interaction.channel:
                        msg_loc = f" do kanálu {target_channel.mention}"
                except Exception as e:
                    logger.error(f"Failed to send to target channel {target_channel.id}: {e}")
                    # Try fallback to current channel if different
                    if target_channel != interaction.channel and interaction.channel:
                        try:
                            sent_message = await interaction.channel.send(content=interaction.user.mention, embed=embed)
                        except:
                            pass
            else:
                logger.warning(f"Could not send public message for listing {listing_id} - no channel.")

            if sent_message:
                await database.update_listing_message(listing_id, sent_message.id, sent_message.channel.id)

            # Delete OLD listing if replacing
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
                        except Exception as e:
                            logger.warning(f"Failed to delete old message during replacement: {e}")
                    await database.delete_listing(old_listing_id)
                    logger.info(f"Deleted old listing {old_listing_id} replaced by {listing_id}")

            # Notify the user via ephemeral followup that it's done
            if not interaction.response.is_done():
                 await interaction.response.send_message(f"✅ Záznam byl úspěšně zveřejněn{msg_loc}.", ephemeral=True)
            else:
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

    # --- My Listings Management ---
    moje_group = app_commands.Group(name="moje", description="Správa mých záznamů (Manage my listings)")

    @moje_group.command(name="nabidky", description="Spravovat mé nabídky (Manage My Offers)")
    async def moje_nabidky(self, interaction: discord.Interaction):
        await self._show_management_view(interaction, 'HAVE')

    @moje_group.command(name="poptavky", description="Spravovat mé poptávky (Manage My Requests)")
    async def moje_poptavky(self, interaction: discord.Interaction):
        await self._show_management_view(interaction, 'WANT')

    async def _show_management_view(self, interaction: discord.Interaction, listing_type: str):
        # Fetch listings
        all_listings = await database.get_user_listings(interaction.user.id)
        listings = [l for l in all_listings if l['listing_type'] == listing_type]

        if not listings:
            await interaction.response.send_message(f"Nemáte žádné aktivní záznamy typu {listing_type}.", ephemeral=True)
            return

        callbacks = {
            'delete': self._delete_listing_callback,
            'edit_details': self._edit_details_callback,
            'edit_all': self._edit_all_callback
        }

        view = ListingManagementView(listings, callbacks)
        embed = self._create_listings_embed(listings, await get_user_team_color(interaction.user.id))

        # Determine title prefix based on type
        title_prefix = "Moje Nabídky" if listing_type == 'HAVE' else "Moje Poptávky"
        embed.title = f"{title_prefix} (My Listings)"

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _delete_listing_callback(self, interaction: discord.Interaction, listing_id: int, view: ListingManagementView):
        listing = await database.get_listing(listing_id)
        if not listing:
            await interaction.response.send_message("Záznam již neexistuje.", ephemeral=True)
            return

        # Delete message
        if listing['channel_id'] and listing['message_id']:
            try:
                channel = self.bot.get_channel(listing['channel_id'])
                if not channel:
                    channel = await self.bot.fetch_channel(listing['channel_id'])
                if channel:
                    msg = await channel.fetch_message(listing['message_id'])
                    await msg.delete()
            except Exception as e:
                logger.warning(f"Failed to delete listing message for {listing_id}: {e}")

        await database.delete_listing(listing_id)

        # Refresh View
        # Update view.listings
        view.listings = [l for l in view.listings if l['id'] != listing_id]

        # If no listings left, disable
        if not view.listings:
            await interaction.response.edit_message(content="✅ Záznam smazán. Seznam je prázdný.", embed=None, view=None)
            return

        # Create new View to refresh Select Menu
        new_view = ListingManagementView(view.listings, view.callbacks)
        embed = self._create_listings_embed(view.listings, await get_user_team_color(interaction.user.id))

        await interaction.response.edit_message(content="✅ Záznam smazán.", embed=embed, view=new_view)

    async def _edit_details_callback(self, interaction: discord.Interaction, listing_id: int, new_details: str, view: ListingManagementView):
        await database.update_listing_details(listing_id, new_details)

        # Update message
        listing = await database.get_listing(listing_id) # Reload
        if listing['channel_id'] and listing['message_id']:
            try:
                channel = self.bot.get_channel(listing['channel_id'])
                if not channel:
                    channel = await self.bot.fetch_channel(listing['channel_id'])
                if channel:
                    msg = await channel.fetch_message(listing['message_id'])
                    # Re-create embed
                    embed = self._create_single_listing_embed(listing)
                    await msg.edit(embed=embed)
            except Exception as e:
                logger.warning(f"Failed to edit message for {listing_id}: {e}")

        # Refresh List View
        # We need to update the specific listing in the local list so the embed updates
        # But `listings` contains Rows which are immutable.
        # So we fetch again.
        all_listings = await database.get_user_listings(interaction.user.id)
        current_type = listing['listing_type']
        listings = [l for l in all_listings if l['listing_type'] == current_type]

        new_view = ListingManagementView(listings, view.callbacks)
        embed_list = self._create_listings_embed(listings, await get_user_team_color(interaction.user.id))

        await interaction.response.edit_message(content="✅ Popis upraven.", embed=embed_list, view=new_view)

    async def _edit_all_callback(self, interaction: discord.Interaction, listing_id: int, view: ListingManagementView):
        # 1. Get Listing
        listing = await database.get_listing(listing_id)
        if not listing:
             await interaction.response.send_message("Záznam neexistuje.", ephemeral=True)
             return

        # 2. Launch Wizard (ListingDraftView)
        # We do NOT delete the listing yet. We wait for publish.

        pokemon_name = POKEMON_IDS.get(listing['pokemon_id'], "Unknown")
        accounts = await database.get_user_accounts(interaction.user.id)

        # Prepare callback with old_listing_id
        submit_cb = functools.partial(self.create_listing_final, old_listing_id=listing_id)

        draft_view = ListingDraftView(
            interaction,
            listing['listing_type'],
            listing['pokemon_id'],
            pokemon_name,
            accounts,
            initial_details=listing['details'],
            submit_callback=submit_cb
        )

        # Pre-fill draft view attributes
        draft_view.is_shiny = bool(listing['is_shiny'])
        draft_view.is_purified = bool(listing['is_purified'])
        draft_view.is_dynamax = bool(listing['is_dynamax'])
        draft_view.is_gigantamax = bool(listing['is_gigantamax'])
        draft_view.is_background = bool(listing['is_background'])
        draft_view.is_adventure_effect = bool(listing['is_adventure_effect'])
        draft_view.is_mirror = bool(listing['is_mirror'])

        # Select correct account
        for acc in accounts:
            if acc['id'] == listing['account_id']:
                draft_view.selected_account_id = acc['id']
                draft_view.selected_account_name = acc['account_name']
                draft_view.selected_account_fc = acc['friend_code']
                break

        draft_view._update_components() # Refresh buttons state

        embed = draft_view._get_embed()

        # Replace the management view with the wizard
        await interaction.response.edit_message(content=None, embed=embed, view=draft_view)

async def setup(bot):
    await bot.add_cog(Listings(bot))
