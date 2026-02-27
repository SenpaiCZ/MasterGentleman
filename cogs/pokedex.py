import discord
from discord import app_commands
from discord.ext import commands
import database
import logging
import json

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

        description += "\n\n**Base Stats (Pokemon GO):**\n"

        # Max stats in GO are roughly: Atk ~500, Def ~500, HP ~500. Using 300 for nicer bars for average mons.
        # Blissey HP is huge so we might cap it or just let it fill.
        # Let's use 300 as visual max for bars, but clamp.

        description += f"⚔️ **Attack:** {self._create_stat_bar(species['attack'], 400)}\n"
        description += f"🛡️ **Defense:** {self._create_stat_bar(species['defense'], 400)}\n"
        description += f"❤️ **Stamina:** {self._create_stat_bar(species['hp'], 400)}\n"

        # Check for max_cp if available (migrated schema might not have it populated yet for old rows)
        if 'max_cp' in species and species['max_cp'] > 0:
            description += f"\n💪 **Max CP (Lvl 50):** {species['max_cp']}"

        # Add Buddy Distance if available
        if 'buddy_distance' in species and species['buddy_distance'] > 0:
            description += f"\n🚶 **Buddy Distance:** {species['buddy_distance']} km"

        embed = discord.Embed(title=title, description=description, color=embed_color)

        if species['image_url']:
            embed.set_thumbnail(url=species['image_url'])

        # Best Moveset
        if 'best_moveset' in species and species['best_moveset']:
            try:
                moveset = json.loads(species['best_moveset'])
                if moveset:
                    moveset_text = f"⚔️ {moveset.get('fast_move', '?')} + {moveset.get('charged_move', '?')}\n"
                    moveset_text += f"**DPS:** {moveset.get('dps', '?')} | **TDO:** {moveset.get('tdo', '?')}"
                    if moveset.get('weather'):
                        moveset_text += f" | **Weather:** {moveset.get('weather')}"
                    embed.add_field(name="Best Moveset", value=moveset_text, inline=False)
            except json.JSONDecodeError:
                pass

        # Tier Ranking
        if 'tier_data' in species and species['tier_data']:
            try:
                rankings = json.loads(species['tier_data'])
                if rankings:
                    tier_text = ""
                    for rank in rankings:
                        category = rank['category']
                        tier = rank['tier']
                        ranking_num = rank['rank']

                        line = f"**{category}:** {tier}"
                        if ranking_num:
                            line += f" ({ranking_num})"
                        tier_text += line + "\n"

                    if tier_text:
                        embed.add_field(name="Tier Ranking", value=tier_text, inline=False)
            except json.JSONDecodeError:
                pass

        # Features
        features = []
        if species['can_dynamax']: features.append("Dynamax")
        # Check for other forms (Mega, Gigantamax, Shadow)
        variants = await database.get_pokemon_variants(species['pokedex_num'])
        for v in variants:
            form = v['form']
            if "Mega" in form and "Mega Evolution" not in features:
                features.append("Mega Evolution")
            if "Gigantamax" in form and "Gigantamax" not in features:
                features.append("Gigantamax")
            if "Shadow" in form and "Shadow" not in features:
                features.append("Shadow")

        if features:
            embed.add_field(name="Capabilities in GO", value=", ".join(features), inline=False)

        # Links - Focused on GO
        links = f"[GO Hub Database](https://db.pokemongohub.net/pokemon/{species['pokedex_num']})"
        embed.add_field(name="More Info", value=links, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Pokedex(bot))
