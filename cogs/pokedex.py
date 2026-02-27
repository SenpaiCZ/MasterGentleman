import discord
from discord import app_commands
from discord.ext import commands
import database
import logging

logger = logging.getLogger('discord')

class Pokedex(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _create_stat_bar(self, value, max_val=255, length=10):
        """Creates a visual progress bar for stats."""
        # Normalize to length
        filled = int((value / max_val) * length)
        filled = max(0, min(length, filled))
        empty = length - filled

        # Using blocks
        bar = "█" * filled + "░" * empty
        return f"`{bar}` {value}"

    def _get_color_by_type(self, type1):
        """Returns a discord.Color based on Pokemon type."""
        colors = {
            "Normal": 0xA8A77A,
            "Fire": 0xEE8130,
            "Water": 0x6390F0,
            "Electric": 0xF7D02C,
            "Grass": 0x7AC74C,
            "Ice": 0x96D9D6,
            "Fighting": 0xC22E28,
            "Poison": 0xA33EA1,
            "Ground": 0xE2BF65,
            "Flying": 0xA98FF3,
            "Psychic": 0xF95587,
            "Bug": 0xA6B91A,
            "Rock": 0xB6A136,
            "Ghost": 0x735797,
            "Dragon": 0x6F35FC,
            "Steel": 0xB7B7CE,
            "Fairy": 0xD685AD,
        }
        return colors.get(type1, 0xFFFFFF)

    async def pokemon_autocomplete_extended(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()
        results = await database.search_pokemon_species_extended(current, limit=25)
        choices = []
        for r in results:
            name = r['name']
            if r['form'] != 'Normal':
                name += f" ({r['form']})"
            choices.append(app_commands.Choice(name=name, value=str(r['id'])))
        return choices

    @app_commands.command(name="pokemon", description="Zobrazit detaily o Pokémonovi (Show Pokemon details)")
    @app_commands.describe(pokemon="Jméno Pokémona nebo typ (např. 'Pikachu', 'Fire')")
    @app_commands.autocomplete(pokemon=pokemon_autocomplete_extended)
    async def pokemon(self, interaction: discord.Interaction, pokemon: str):
        # Resolve Pokemon
        species = None
        if pokemon.isdigit():
            species = await database.get_pokemon_species_by_id(int(pokemon))
        else:
            # Fallback if they typed exact name without selecting
            species = await database.get_pokemon_species_by_name(pokemon)

        if not species:
            await interaction.response.send_message("❌ Pokémon nenalezen.", ephemeral=True)
            return

        # Prepare Embed
        embed_color = self._get_color_by_type(species['type1'])
        title = f"#{species['pokedex_num']} {species['name']}"
        if species['form'] != 'Normal':
            title += f" ({species['form']})"

        description = f"**Type:** {species['type1']}"
        if species['type2']:
            description += f" / {species['type2']}"

        description += "\n\n**Base Stats (MSG):**\n"
        description += f"❤️ HP: {self._create_stat_bar(species['hp'])}\n"
        description += f"⚔️ Atk: {self._create_stat_bar(species['attack'])}\n"
        description += f"🛡️ Def: {self._create_stat_bar(species['defense'])}\n"
        description += f"💥 Sp.A: {self._create_stat_bar(species['sp_atk'])}\n"
        description += f"🔰 Sp.D: {self._create_stat_bar(species['sp_def'])}\n"
        description += f"💨 Spe: {self._create_stat_bar(species['speed'])}\n"

        total = species['hp'] + species['attack'] + species['defense'] + species['sp_atk'] + species['sp_def'] + species['speed']
        description += f"\n**Total:** {total}"

        embed = discord.Embed(title=title, description=description, color=embed_color)

        if species['image_url']:
            embed.set_thumbnail(url=species['image_url'])

        # Features
        features = []
        if species['can_dynamax']: features.append("Dynamax")
        if species['can_gigantamax']: features.append("Gigantamax")
        if species['can_mega']: features.append("Mega Evolution")

        if features:
            embed.add_field(name="Capabilities in GO", value=", ".join(features), inline=False)

        # Links
        links = f"[Serebii](https://www.serebii.net/pokemon/{species['name'].lower()}) | "
        links += f"[Bulbapedia](https://bulbapedia.bulbagarden.net/wiki/{species['name'].replace(' ', '_')}_(Pok%C3%A9mon)) | "
        links += f"[GO Hub](https://db.pokemongohub.net/pokemon/{species['pokedex_num']})"
        embed.add_field(name="More Info", value=links, inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Pokedex(bot))
