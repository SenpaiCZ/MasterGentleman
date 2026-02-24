import database
import logging

logger = logging.getLogger('discord')

async def find_match(new_listing_id):
    """
    Attempts to find a match for the newly created listing.
    If a match is found:
    1. Locks both listings (sets status to PENDING).
    2. Creates a Trade record (status OPEN, channel_id NULL).
    Returns: (trade_id, matched_listing_data) or (None, None).
    """
    try:
        new_listing = await database.get_listing(new_listing_id)
        if not new_listing:
            return None, None

        target_type = 'WANT' if new_listing['listing_type'] == 'HAVE' else 'HAVE'

        candidates = await database.find_candidates(
            listing_type=target_type,
            pokemon_id=new_listing['pokemon_id'],
            is_shiny=new_listing['is_shiny'],
            is_purified=new_listing['is_purified'],
            exclude_user_id=new_listing['user_id']
        )

        match = None
        for candidate in candidates:
            # Check history to avoid re-matching failed pairs
            history = await database.check_trade_history(new_listing['id'], candidate['id'])
            if not history:
                match = candidate
                break

        if match:
            # We found a match!
            logger.info(f"Match found for listing {new_listing_id} -> {match['id']}")

            # Set both to PENDING
            await database.update_listing_status(new_listing['id'], 'PENDING')
            await database.update_listing_status(match['id'], 'PENDING')

            # Create trade record
            trade_id = await database.create_trade(new_listing['id'], match['id'], channel_id=None)

            return trade_id, match

    except Exception as e:
        logger.error(f"Error in find_match: {e}")
        return None, None

    return None, None
