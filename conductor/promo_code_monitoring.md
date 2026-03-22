# Implementation Plan: Promo Code Monitoring

Add a background task to monitor Pokemon GO promo codes from LeekDuck and notify configured channels.

## Objective
- Periodically check `https://leekduck.com/promo-codes/` for new codes.
- Notify users in a configured Discord channel when a new code is found.
- Provide a direct link to the redemption store: `https://store.pokemongo.com/offer-redemption?passcode=<code>`.

## Key Files & Context
- `database.py`: Store guild configuration (`promo_channel_id`) and track "seen" codes.
- `services/scraper.py`: Logic for scraping LeekDuck.
- `cogs/config.py`: Commands to set the notification channel.
- `cogs/promo.py` (New): Background task to run the monitor.

## Implementation Steps

### 1. Database Updates (`database.py`)
- Add `promo_channel_id` to `guild_config` table.
- Create a new table `promo_codes` to store discovered codes:
  ```sql
  CREATE TABLE IF NOT EXISTS promo_codes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT UNIQUE NOT NULL,
      description TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
  ```
- Update `set_guild_config` to allow `promo_channel_id`.
- Add helper functions:
  - `add_seen_promo_code(code, description)`
  - `is_promo_code_seen(code)`

### 2. Scraping Logic (`services/scraper.py`)
- Add `scrape_promo_codes()` function:
  - Fetch `https://leekduck.com/promo-codes/`.
  - Parse the codes and their descriptions.
  - Filter for "Active" codes if possible.

### 3. Configuration Commands (`cogs/config.py`)
- Add `/setup promo_channel` command.
- Update `/setup stav` (status) to show the promo channel.

### 4. Background Task Cog (`cogs/promo.py`)
- Create a new Cog with a `tasks.loop`.
- Every X minutes (e.g., 60):
  1. Call `scrape_promo_codes()`.
  2. For each new code:
     - Check if it exists in the `promo_codes` table.
     - If new, add it to the database.
     - Send a notification to all guilds that have a `promo_channel_id` configured.
- Notification format:
  - Embed with code, description, and the direct redemption link.

### 5. Integration
- Register `cogs.promo` in `main.py` (or ensure it's loaded if using automatic loading).

## Verification & Testing
- **Unit Test:** Test `scrape_promo_codes()` with a mock/sample HTML response.
- **Database Test:** Ensure `promo_codes` table handles duplicates correctly.
- **Integration Test:** Trigger the task manually or with a short interval to verify Discord notifications.
