# MasterGentleman - Pokémon GO Trade Helper Bot

A Discord bot designed to facilitate Pokémon GO trades within your community. It helps users list their offers and requests, find potential trade partners, and coordinate meetups.

## Co umím a jak ti pomůžu?

*   **Snadné výměny Pokémonů**: Hledáš konkrétního Pokémona nebo nabízíš přebytky? Zadej to ke mě a já ti najdu ideálního parťáka na výměnu. Podporuji i Shiny, Purified, Dynamax a další!
*   **Automatické párování**: Nemusíš procházet stovky zpráv. Jakmile se objeví někdo, kdo hledá to, co máš, nebo nabízí to, co chceš, dám ti vědět.
*   **Stylové vizitky pro sdílení**: Jedním příkazem ti vytvořím krásný obrázek s tvou nabídkou či poptávkou, který můžeš sdílet na sociálních sítích nebo v jiných skupinách.
*   **Přehled o eventech**: Už žádné zmeškané Raid Hour nebo Community Day! Pravidelně informuji o všem, co se ve světě Pokémon GO chystá.
*   **Rychlé sdílení Trainer Code**: Ostatní trenéři si tvůj kód snadno zobrazí nebo načtou QR kód, takže přidávání přátel je hračka.

## Features

*   **Trade Listings**: Users can easily list Pokémon they have (HAVE) or want (WANT).
*   **Matching System**: Automatically finds potential trade partners based on listings.
*   **Event Updates**: Notifies the community about upcoming Pokémon GO events.
*   **Image Generation**: Generates visual trade cards for sharing.
*   **Localized Interface**: User-facing commands and responses are in Czech.

## Prerequisites

*   **Hardware**: Raspberry Pi 5 (or any Linux machine running a Debian-based OS like Raspberry Pi OS, Ubuntu, etc.).
*   **Operating System**: Raspberry Pi OS (Bookworm or newer recommended).
*   **Software**: Python 3.10+, Git.
*   **Discord Bot Token**: You need to create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).

## Installation

These instructions are tailored for Raspberry Pi OS (Debian-based).

### 1. Update System & Install Dependencies

First, ensure your system is up to date and install necessary packages, including the required fonts for image generation.

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip git fonts-dejavu
```

### 2. Clone the Repository

Clone the bot's source code to your Raspberry Pi.

```bash
git clone https://github.com/yourusername/MasterGentleman.git
cd MasterGentleman
```

### 3. Set Up Virtual Environment

It is highly recommended to use a Python virtual environment to manage dependencies and avoid conflicts with system packages (especially on newer Raspberry Pi OS versions).

```bash
# Create a virtual environment named 'venv'
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

*Note: You will need to activate the virtual environment every time you work on the project or run the bot manually.*

### 4. Install Python Dependencies

With the virtual environment active, install the required Python libraries.

```bash
pip install -r requirements.txt
```

### 5. Configuration

1.  Create a `.env` file based on the example provided.

    ```bash
    cp .env.example .env
    ```

2.  Open the `.env` file using a text editor (like `nano`).

    ```bash
    nano .env
    ```

3.  Paste your Discord Bot Token into the file:

    ```env
    DISCORD_TOKEN=your_actual_discord_bot_token_here
    ```

4.  Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

## Running the Bot

### Manual Execution

To run the bot manually (for testing or debugging), ensure your virtual environment is active and run:

```bash
python main.py
```

To stop the bot, press `Ctrl+C`.

### Automatic Start on Boot (Systemd Service) - Optional

To have the bot start automatically when the Raspberry Pi boots up, you can set up a `systemd` service.

1.  Create a new service file:

    ```bash
    sudo nano /etc/systemd/system/tradebot.service
    ```

2.  Paste the following configuration into the file. **Make sure to replace `/home/pi/MasterGentleman` with the actual path to your bot directory and `pi` with your username if different.**

    ```ini
    [Unit]
    Description=MasterGentleman Discord Bot
    After=network.target

    [Service]
    # Replace 'pi' with your username
    User=pi
    Group=pi

    # Replace with the path to your project directory
    WorkingDirectory=/home/pi/MasterGentleman

    # Replace with the path to your python executable in the venv
    ExecStart=/home/pi/MasterGentleman/venv/bin/python main.py

    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    ```

3.  Reload the systemd daemon to recognize the new service:

    ```bash
    sudo systemctl daemon-reload
    ```

4.  Enable the service to start on boot:

    ```bash
    sudo systemctl enable tradebot.service
    ```

5.  Start the service immediately:

    ```bash
    sudo systemctl start tradebot.service
    ```

6.  Check the status to ensure it's running correctly:

    ```bash
    sudo systemctl status tradebot.service
    ```

## Usage

Once the bot is running and invited to your server, you can use the following slash commands:

*   `/nabidka`: Add a Pokémon you are offering (HAVE).
*   `/poptavka`: Add a Pokémon you are looking for (WANT).
*   `/seznam`: List your current active listings.
*   `/tisk`: Generate an image summary of your offers or requests.
*   `/registrace`: Register your Trainer Code, Team, and Region.
*   `/smazat`: Delete a listing.
*   `/nastaveni_udalosti`: Configure event notifications (Admin only).

## Troubleshooting

*   **Database**: The bot uses a local SQLite database (`trade_bot.db`). This file is created automatically on the first run.
*   **Fonts**: If generated images have missing text or weird symbols, ensure `fonts-dejavu` is installed (`sudo apt install fonts-dejavu`).
*   **Logs**: Check the console output (if running manually) or system logs (`journalctl -u tradebot.service -f`) for errors.
