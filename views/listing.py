import discord
from discord import ui
import logging
import database
from data.pokemon import POKEMON_IMAGES, POKEMON_IDS

logger = logging.getLogger('discord')

class ListingDescriptionModal(ui.Modal, title="Detaily nabídky/poptávky"):
    details = ui.TextInput(
        label="Popis",
        placeholder="Např. kostým, CP, útoky, location card...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=200
    )

    def __init__(self, current_details, callback):
        super().__init__()
        if current_details:
            self.details.default = current_details
        self.callback = callback

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.details.value)

class ListingCountModal(ui.Modal, title="Počet (Quantity)"):
    count = ui.TextInput(
        label="Počet kusů",
        placeholder="Zadejte číslo (1-100)",
        min_length=1,
        max_length=3,
        required=True
    )

    def __init__(self, current_count, callback):
        super().__init__()
        self.count.default = str(current_count)
        self.callback = callback

    async def on_submit(self, interaction: discord.Interaction):
        if not self.count.value.isdigit():
             await interaction.response.send_message("❌ Zadejte prosím platné číslo.", ephemeral=True)
             return

        val = int(self.count.value)
        if val < 1 or val > 100:
             await interaction.response.send_message("❌ Počet musí být mezi 1 a 100.", ephemeral=True)
             return

        await self.callback(interaction, val)


class ListingDraftView(ui.View):
    def __init__(self, interaction, listing_type, species_id, pokedex_num, pokemon_name, image_url, shiny_image_url, accounts, can_dynamax=False, initial_details=None, submit_callback=None):
        super().__init__(timeout=180)
        self.original_interaction = interaction
        self.listing_type = listing_type
        self.species_id = species_id
        self.pokedex_num = pokedex_num
        self.pokemon_name = pokemon_name
        self.image_url = image_url
        self.shiny_image_url = shiny_image_url
        self.accounts = accounts
        self.can_dynamax = can_dynamax
        self.submit_callback = submit_callback

        # State
        self.is_shiny = False
        self.is_purified = False
        self.is_dynamax = False
        # self.is_gigantamax = False  # Removed
        self.is_background = False
        self.is_adventure_effect = False
        self.is_mirror = False
        self.details = initial_details
        self.count = 1

        # Adventure Effect Eligibility
        # Allowed: Origin Dialga, Origin Palkia, Black Kyurem, White Kyurem,
        # Dusk Mane Necrozma, Dawn Wings Necrozma, Crowned Shield Zamazenta,
        # Crowned Sword Zacian, Eternatus

        # We need to check exact form matches.
        # pokemon_name passed here usually contains form if not Normal (e.g. "Dialga (Origin Forme)")
        # Ideally we should check based on pokedex_num and form or exact name.
        # But here we assume pokemon_name is constructed as "Name (Form)" if form != Normal.

        # Let's normalize for check.
        # The list provided:
        # Origin Dialga -> Dialga (Origin Forme)
        # Origin Palkia -> Palkia (Origin Forme)
        # Black Kyurem -> Kyurem (Black Kyurem) ? Need to verify exact form strings from DB.
        # But roughly we can check partials if unique enough.

        name_check = pokemon_name.lower()

        self.can_adventure_effect = False

        # List of allowed identifiers (checking against lower case name+form)
        allowed_adv = [
            "dialga (origin",
            "palkia (origin",
            "kyurem (black",
            "kyurem (white",
            "necrozma (dusk mane",
            "necrozma (dawn wings",
            "zamazenta (crowned shield",
            "zacian (crowned sword",
            "eternatus"
        ]

        for allowed in allowed_adv:
            if allowed in name_check:
                self.can_adventure_effect = True
                break

        # Default to main account or first account
        main_acc = next((acc for acc in accounts if acc['is_main']), accounts[0])
        self.selected_account_id = main_acc['id']
        self.selected_account_name = main_acc['account_name']
        self.selected_account_fc = main_acc['friend_code']

        # UI Setup
        self._update_components()

    def _create_button(self, label, emoji, is_active, custom_id, callback, row):
        style = discord.ButtonStyle.primary if is_active else discord.ButtonStyle.secondary
        # Shiny uses success green
        if label == "Shiny" and is_active:
            style = discord.ButtonStyle.success

        btn = ui.Button(label=label, emoji=emoji, style=style, custom_id=custom_id, row=row)
        btn.callback = callback
        return btn

    def _update_components(self):
        self.clear_items()

        # Row 0: Basic Attributes
        self.add_item(self._create_button("Shiny", "✨", self.is_shiny, "toggle_shiny", self.toggle_shiny, 0))
        self.add_item(self._create_button("Purified", "🕊️", self.is_purified, "toggle_purified", self.toggle_purified, 0))
        if self.can_dynamax:
            self.add_item(self._create_button("Dyna", None, self.is_dynamax, "toggle_dynamax", self.toggle_dynamax, 0))
        # Removed Giga button
        self.add_item(self._create_button("BG", "🌍", self.is_background, "toggle_bg", self.toggle_bg, 0))

        # Row 1: Advanced Attributes & Details
        if self.can_adventure_effect:
            self.add_item(self._create_button("Adventure Effect", "🪄", self.is_adventure_effect, "toggle_adv", self.toggle_adv, 1))

        self.add_item(self._create_button("Mirror", "🪞", self.is_mirror, "toggle_mirror", self.toggle_mirror, 1))

        btn_details = ui.Button(
            label="Popis",
            emoji="📝",
            style=discord.ButtonStyle.secondary,
            custom_id="edit_details",
            row=1
        )
        btn_details.callback = self.open_details_modal
        self.add_item(btn_details)

        # Count Button
        btn_count = ui.Button(
            label=f"Počet: {self.count}",
            emoji="#️⃣",
            style=discord.ButtonStyle.secondary,
            custom_id="edit_count",
            row=1
        )
        btn_count.callback = self.open_count_modal
        self.add_item(btn_count)

        # Row 2: Account Select (if multiple accounts)
        row_offset = 2
        if len(self.accounts) > 1:
            options = []
            for acc in self.accounts:
                label = f"{acc['account_name']} ({acc['friend_code']})"
                if acc['is_main']:
                    label = "⭐ " + label
                options.append(discord.SelectOption(
                    label=label,
                    value=str(acc['id']),
                    default=(acc['id'] == self.selected_account_id)
                ))

            select_account = ui.Select(
                placeholder="👤 Vybrat účet",
                min_values=1,
                max_values=1,
                options=options,
                row=row_offset
            )
            select_account.callback = self.select_account
            self.add_item(select_account)
            row_offset += 1

        # Final Row: Actions
        btn_publish = ui.Button(
            label="Zveřejnit",
            emoji="✅",
            style=discord.ButtonStyle.green,
            custom_id="publish_listing",
            row=row_offset
        )
        btn_publish.callback = self.publish
        self.add_item(btn_publish)

        btn_cancel = ui.Button(
            label="Zrušit",
            emoji="❌",
            style=discord.ButtonStyle.red,
            custom_id="cancel_listing",
            row=row_offset
        )
        btn_cancel.callback = self.cancel
        self.add_item(btn_cancel)

    def _get_embed(self):
        title = "Návrh Nabídky" if self.listing_type == 'HAVE' else "Návrh Poptávky"
        color = discord.Color.blue() if self.listing_type == 'HAVE' else discord.Color.orange()

        count_str = f" (x{self.count})" if self.count > 1 else ""
        desc = f"**Pokémon:** {self.pokemon_name}{count_str}\n"

        # Status line
        status_parts = []
        if self.is_shiny: status_parts.append("✨ **Shiny**")
        if self.is_purified: status_parts.append("🕊️ **Purified**")
        if self.is_dynamax: status_parts.append("**Dyna**")
        # Removed Giga status
        if self.is_background: status_parts.append("🌍 **BG**")
        if self.is_adventure_effect: status_parts.append("🪄 **Adventure Effect**")
        if self.is_mirror: status_parts.append("🪞 **Mirror**")

        if status_parts:
            desc += f"**Stav:** {' | '.join(status_parts)}\n"

        # Details
        if self.details:
            desc += f"**Popis:** {self.details}\n"

        # Account
        desc += f"\n👤 **Účet:** {self.selected_account_name} (`{self.selected_account_fc}`)"

        embed = discord.Embed(title=title, description=desc, color=color)

        # Get Image Logic
        # Priority: DB Shiny URL (if shiny) > DB Normal URL > JSON Shiny (if shiny) > JSON Normal

        final_image_url = None

        if self.is_shiny and self.shiny_image_url:
            final_image_url = self.shiny_image_url
        elif self.image_url:
            # If standard, or shiny but no specific shiny URL
            final_image_url = self.image_url

        # Fallback to JSON if DB URLs are missing
        if not final_image_url:
            img_info = POKEMON_IMAGES.get(self.pokedex_num)
            if img_info:
                if self.is_shiny:
                    final_image_url = img_info.get('shiny') or img_info.get('normal')
                else:
                    final_image_url = img_info.get('normal')

        if final_image_url:
            embed.set_thumbnail(url=final_image_url)

        embed.set_footer(text="Upravte detaily pomocí tlačítek a potvrďte zveřejnění.")
        return embed

    async def update_view(self, interaction: discord.Interaction):
        self._update_components()
        embed = self._get_embed()
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Fallback if needed, but usually edit_message works
            await interaction.edit_original_response(embed=embed, view=self)

    async def toggle_shiny(self, interaction: discord.Interaction):
        self.is_shiny = not self.is_shiny
        await self.update_view(interaction)

    async def toggle_purified(self, interaction: discord.Interaction):
        self.is_purified = not self.is_purified
        await self.update_view(interaction)

    async def toggle_dynamax(self, interaction: discord.Interaction):
        self.is_dynamax = not self.is_dynamax
        await self.update_view(interaction)

    # Removed toggle_gigantamax

    async def toggle_bg(self, interaction: discord.Interaction):
        self.is_background = not self.is_background
        await self.update_view(interaction)

    async def toggle_adv(self, interaction: discord.Interaction):
        self.is_adventure_effect = not self.is_adventure_effect
        await self.update_view(interaction)

    async def toggle_mirror(self, interaction: discord.Interaction):
        self.is_mirror = not self.is_mirror
        await self.update_view(interaction)

    async def open_details_modal(self, interaction: discord.Interaction):
        # Callback for the modal to update the view
        async def modal_callback(modal_interaction, new_details):
            self.details = new_details
            await self.update_view(modal_interaction)

        await interaction.response.send_modal(ListingDescriptionModal(self.details, modal_callback))

    async def open_count_modal(self, interaction: discord.Interaction):
        async def modal_callback(modal_interaction, new_count):
            self.count = new_count
            await self.update_view(modal_interaction)

        await interaction.response.send_modal(ListingCountModal(self.count, modal_callback))

    async def select_account(self, interaction: discord.Interaction):
        # The select interaction returns a list of values
        select = [item for item in self.children if isinstance(item, ui.Select)][0]
        selected_val = int(select.values[0])

        # Update selected account
        for acc in self.accounts:
            if acc['id'] == selected_val:
                self.selected_account_id = acc['id']
                self.selected_account_name = acc['account_name']
                self.selected_account_fc = acc['friend_code']
                break

        await self.update_view(interaction)

    async def publish(self, interaction: discord.Interaction):
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        # Call the external callback
        if self.submit_callback:
            await self.submit_callback(
                interaction,
                self.selected_account_id,
                self.listing_type,
                self.species_id,
                self.pokemon_name,
                self.is_shiny,
                self.is_purified,
                self.is_dynamax,
                False, # is_gigantamax forced to False
                self.is_background,
                self.is_adventure_effect,
                self.is_mirror,
                self.details,
                self.count
            )

    async def cancel(self, interaction: discord.Interaction):
        embed = discord.Embed(title="❌ Zrušeno", description="Vytváření záznamu bylo zrušeno.", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=None)


class ListingManagementView(ui.View):
    def __init__(self, listings, callbacks):
        # callbacks: dict with 'delete', 'edit_details', 'edit_all'
        super().__init__(timeout=180)
        self.listings = [dict(l) for l in listings]
        self.callbacks = callbacks
        self.selected_listing_id = None

        options = []
        # Limit to 25
        for l in self.listings[:25]:
            p_name = POKEMON_IDS.get(l['pokemon_id'], f"#{l['pokemon_id']}")
            is_have = l['listing_type'] == 'HAVE'
            emoji = "📥" if is_have else "📤"

            desc_parts = []
            if l['is_shiny']: desc_parts.append("✨")
            if l.get('is_mirror'): desc_parts.append("🪞")
            if l.get('count', 1) > 1: desc_parts.append(f"(x{l['count']})")
            if l['account_name'] and l['account_name'] != "Main": desc_parts.append(f"👤 {l['account_name']}")

            desc = " ".join(desc_parts)
            if not desc: desc = "Standard"

            # No ID in label
            label = f"{emoji} {p_name}"

            options.append(discord.SelectOption(
                label=label[:100],
                value=str(l['id']),
                description=desc[:100]
            ))

        if not options:
            options.append(discord.SelectOption(label="Žádné záznamy", value="none"))

        self.select_menu = ui.Select(
            placeholder="Vyberte záznam...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=(len(listings) == 0)
        )
        self.select_menu.callback = self.on_select
        self.add_item(self.select_menu)

        # Buttons
        self.btn_edit_details = ui.Button(label="Upravit popis", emoji="📝", style=discord.ButtonStyle.secondary, disabled=True, row=1)
        self.btn_edit_details.callback = self.on_edit_details
        self.add_item(self.btn_edit_details)

        self.btn_edit_all = ui.Button(label="Upravit vše", emoji="✏️", style=discord.ButtonStyle.secondary, disabled=True, row=1)
        self.btn_edit_all.callback = self.on_edit_all
        self.add_item(self.btn_edit_all)

        self.btn_delete = ui.Button(label="Smazat", emoji="🗑️", style=discord.ButtonStyle.red, disabled=True, row=1)
        self.btn_delete.callback = self.on_delete
        self.add_item(self.btn_delete)

    async def on_select(self, interaction: discord.Interaction):
        if self.select_menu.values[0] == "none":
            return

        self.selected_listing_id = int(self.select_menu.values[0])
        self.btn_edit_details.disabled = False
        self.btn_edit_all.disabled = False
        self.btn_delete.disabled = False
        await interaction.response.edit_message(view=self)

    async def on_delete(self, interaction: discord.Interaction):
        if self.selected_listing_id and self.callbacks.get('delete'):
            await self.callbacks['delete'](interaction, self.selected_listing_id, self)

    async def on_edit_details(self, interaction: discord.Interaction):
        if self.selected_listing_id and self.callbacks.get('edit_details'):
            # Find current details
            listing = next((l for l in self.listings if l['id'] == self.selected_listing_id), None)
            current_details = listing['details'] if listing else ""

            async def modal_callback(modal_interaction, new_details):
                await self.callbacks['edit_details'](modal_interaction, self.selected_listing_id, new_details, self)

            await interaction.response.send_modal(ListingDescriptionModal(current_details, modal_callback))

    async def on_edit_all(self, interaction: discord.Interaction):
        if self.selected_listing_id and self.callbacks.get('edit_all'):
            await self.callbacks['edit_all'](interaction, self.selected_listing_id, self)
