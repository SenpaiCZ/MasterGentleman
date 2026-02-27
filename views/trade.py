import discord
import database
import logging
import asyncio

logger = logging.getLogger('discord')

class TradeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _get_trade_context(self, interaction: discord.Interaction):
        """Helper to get trade and listings based on channel ID."""
        trade = await database.get_trade_by_channel(interaction.channel_id)
        if not trade:
            await interaction.response.send_message("❌ Tento kanál není aktivní obchodní kanál.", ephemeral=True)
            return None, None, None

        listing_a = await database.get_listing(trade['listing_a_id'])
        listing_b = await database.get_listing(trade['listing_b_id'])

        # Check if listings still exist (might have been deleted if count reached 0 separately?)
        if not listing_a or not listing_b:
             await interaction.response.send_message("❌ Jeden ze záznamů již neexistuje.", ephemeral=True)
             return None, None, None

        # Verify user is a participant
        if interaction.user.id not in (listing_a['user_id'], listing_b['user_id']):
            await interaction.response.send_message("⛔ Nemáte oprávnění k této akci.", ephemeral=True)
            return None, None, None

        return trade, listing_a, listing_b

    @discord.ui.button(label="Obchod Dokončen (Complete)", style=discord.ButtonStyle.green, custom_id="trade_complete", row=1)
    async def complete_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        trade, listing_a, listing_b = await self._get_trade_context(interaction)
        if not trade:
            return

        # Decrement Logic
        try:
            # Listing A
            count_a = listing_a.get('count', 1)
            new_count_a = count_a - 1
            if new_count_a <= 0:
                await database.delete_listing(listing_a['id'])
            else:
                await database.update_listing_count(listing_a['id'], new_count_a)
                # If we keep it, we should set status back to ACTIVE if we want it to be matchable again?
                # "decrees by one on trade" - usually implies the remaining stock is still available.
                # But current trade logic sets status to 'PENDING' (via matched/locked state?).
                # Wait, status in DB is used. `matcher` finds 'ACTIVE'.
                # We need to set it back to ACTIVE so it can be matched again.
                await database.update_listing_status(listing_a['id'], 'ACTIVE')

            # Listing B
            count_b = listing_b.get('count', 1)
            new_count_b = count_b - 1
            if new_count_b <= 0:
                await database.delete_listing(listing_b['id'])
            else:
                await database.update_listing_count(listing_b['id'], new_count_b)
                await database.update_listing_status(listing_b['id'], 'ACTIVE')

            # Close trade
            await database.close_trade(trade['id'])

            await interaction.response.send_message("✅ Obchod byl úspěšně dokončen! Kanál bude smazán za 5 sekund. (Trade Completed)")

            await asyncio.sleep(5)
            await interaction.channel.delete()

        except Exception as e:
            logger.error(f"Error completing trade: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Nastala chyba při dokončování obchodu.", ephemeral=True)

    @discord.ui.button(label="Zrušit Obchod (Cancel)", style=discord.ButtonStyle.red, custom_id="trade_cancel", row=1)
    async def cancel_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        trade, listing_a, listing_b = await self._get_trade_context(interaction)
        if not trade:
            return

        try:
            # Revert listings to ACTIVE
            await database.update_listing_status(listing_a['id'], 'ACTIVE')
            await database.update_listing_status(listing_b['id'], 'ACTIVE')

            # Close trade
            await database.close_trade(trade['id'])

            await interaction.response.send_message("⚠️ Obchod byl zrušen. Nabídky jsou opět aktivní. Kanál bude smazán za 5 sekund. (Trade Cancelled)")

            await asyncio.sleep(5)
            await interaction.channel.delete()

        except Exception as e:
            logger.error(f"Error cancelling trade: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Nastala chyba při rušení obchodu.", ephemeral=True)

    @discord.ui.button(label="📋 FC A (Kopírovat)", style=discord.ButtonStyle.secondary, custom_id="trade_copy_fc_a", row=0)
    async def copy_fc_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Copies Friend Code for Listing A"""
        trade, listing_a, listing_b = await self._get_trade_context(interaction)
        if not trade:
            return

        fc = listing_a['friend_code']
        # For mobile users, just sending the number is best as they can long press -> copy
        await interaction.response.send_message(f"{fc}", ephemeral=True)

    @discord.ui.button(label="📋 FC B (Kopírovat)", style=discord.ButtonStyle.secondary, custom_id="trade_copy_fc_b", row=0)
    async def copy_fc_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Copies Friend Code for Listing B"""
        trade, listing_a, listing_b = await self._get_trade_context(interaction)
        if not trade:
            return

        fc = listing_b['friend_code']
        await interaction.response.send_message(f"{fc}", ephemeral=True)
