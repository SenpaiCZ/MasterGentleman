import discord
import database
import logging

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

        # Verify user is a participant
        if interaction.user.id not in (listing_a['user_id'], listing_b['user_id']):
            await interaction.response.send_message("⛔ Nemáte oprávnění k této akci.", ephemeral=True)
            return None, None, None

        return trade, listing_a, listing_b

    @discord.ui.button(label="Obchod Dokončen (Complete)", style=discord.ButtonStyle.green, custom_id="trade_complete")
    async def complete_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        trade, listing_a, listing_b = await self._get_trade_context(interaction)
        if not trade:
            return

        # Double check intent
        # Ideally, we should require confirmation from both? For MVP, one is enough.

        try:
            # Delete listings
            await database.delete_listing(listing_a['id'])
            await database.delete_listing(listing_b['id'])

            # Close trade
            await database.close_trade(trade['id'])

            await interaction.response.send_message("✅ Obchod byl úspěšně dokončen! Kanál bude smazán za 5 sekund. (Trade Completed)")

            # Delete channel after delay
            # We can use delete(delay=5) on channel, but interaction doesn't expose that directly on response.
            # We can use asyncio.sleep
            # Note: Using create_task to avoid blocking
            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete()

        except Exception as e:
            logger.error(f"Error completing trade: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Nastala chyba při dokončování obchodu.", ephemeral=True)

    @discord.ui.button(label="Zrušit Obchod (Cancel)", style=discord.ButtonStyle.red, custom_id="trade_cancel")
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

            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete()

        except Exception as e:
            logger.error(f"Error cancelling trade: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Nastala chyba při rušení obchodu.", ephemeral=True)
