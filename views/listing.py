import discord
from discord import ui
import logging
from data.pokemon import POKEMON_IMAGES

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


class ListingDraftView(ui.View):
    def __init__(self, interaction, listing_type, pokemon_id, pokemon_name, accounts, initial_details=None, submit_callback=None):
        super().__init__(timeout=180)
        self.original_interaction = interaction
        self.listing_type = listing_type
        self.pokemon_id = pokemon_id
        self.pokemon_name = pokemon_name
        self.accounts = accounts
        self.submit_callback = submit_callback

        # State
        self.is_shiny = False
        self.is_purified = False
        self.details = initial_details

        # Default to main account or first account
        main_acc = next((acc for acc in accounts if acc['is_main']), accounts[0])
        self.selected_account_id = main_acc['id']
        self.selected_account_name = main_acc['account_name']
        self.selected_account_fc = main_acc['friend_code']

        # UI Setup
        self._update_components()

    def _update_components(self):
        self.clear_items()

        # Row 0: Toggles
        btn_shiny = ui.Button(
            label="Shiny",
            emoji="✨",
            style=discord.ButtonStyle.success if self.is_shiny else discord.ButtonStyle.secondary,
            custom_id="toggle_shiny",
            row=0
        )
        btn_shiny.callback = self.toggle_shiny
        self.add_item(btn_shiny)

        btn_purified = ui.Button(
            label="Purified",
            emoji="🕊️",
            style=discord.ButtonStyle.primary if self.is_purified else discord.ButtonStyle.secondary,
            custom_id="toggle_purified",
            row=0
        )
        btn_purified.callback = self.toggle_purified
        self.add_item(btn_purified)

        btn_details = ui.Button(
            label="Popis",
            emoji="📝",
            style=discord.ButtonStyle.secondary,
            custom_id="edit_details",
            row=0
        )
        btn_details.callback = self.open_details_modal
        self.add_item(btn_details)

        # Row 1: Account Select (if multiple accounts)
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
                row=1
            )
            select_account.callback = self.select_account
            self.add_item(select_account)

        # Row 2: Actions
        btn_publish = ui.Button(
            label="Zveřejnit",
            emoji="✅",
            style=discord.ButtonStyle.green,
            custom_id="publish_listing",
            row=2
        )
        btn_publish.callback = self.publish
        self.add_item(btn_publish)

        btn_cancel = ui.Button(
            label="Zrušit",
            emoji="❌",
            style=discord.ButtonStyle.red,
            custom_id="cancel_listing",
            row=2
        )
        btn_cancel.callback = self.cancel
        self.add_item(btn_cancel)

    def _get_embed(self):
        title = "Návrh Nabídky" if self.listing_type == 'HAVE' else "Návrh Poptávky"
        color = discord.Color.blue() if self.listing_type == 'HAVE' else discord.Color.orange()

        desc = f"**Pokémon:** {self.pokemon_name}\n"

        # Status line
        status_parts = []
        if self.is_shiny: status_parts.append("✨ **Shiny**")
        if self.is_purified: status_parts.append("🕊️ **Purified**")
        if status_parts:
            desc += f"**Stav:** {' | '.join(status_parts)}\n"

        # Details
        if self.details:
            desc += f"**Popis:** {self.details}\n"

        # Account
        desc += f"\n👤 **Účet:** {self.selected_account_name} (`{self.selected_account_fc}`)"

        embed = discord.Embed(title=title, description=desc, color=color)

        # Get Image
        img_info = POKEMON_IMAGES.get(self.pokemon_id)
        if img_info:
            img_url = img_info.get('shiny') if self.is_shiny else img_info.get('normal')
            if not img_url:
                img_url = img_info.get('normal')

            if img_url:
                embed.set_thumbnail(url=img_url)

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

    async def open_details_modal(self, interaction: discord.Interaction):
        # Callback for the modal to update the view
        async def modal_callback(modal_interaction, new_details):
            self.details = new_details
            await self.update_view(modal_interaction)

        await interaction.response.send_modal(ListingDescriptionModal(self.details, modal_callback))

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
                self.pokemon_id,
                self.pokemon_name,
                self.is_shiny,
                self.is_purified,
                self.details
            )

    async def cancel(self, interaction: discord.Interaction):
        embed = discord.Embed(title="❌ Zrušeno", description="Vytváření záznamu bylo zrušeno.", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=None)
