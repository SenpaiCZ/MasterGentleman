import discord
from discord.ext import commands
from discord import app_commands
import database
import logging

logger = logging.getLogger('discord')

TEAMS = {
    "Mystic": discord.Color.blue(),
    "Valor": discord.Color.red(),
    "Instinct": discord.Color.gold()
}

class Lookup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="hledam_trenera", description="Vyhledat trenéra podle herního jména (Search Trainer)")
    @app_commands.describe(ign="Herní jméno trenéra (In-Game Name)")
    async def hledam_trenera(self, interaction: discord.Interaction, ign: str):
        """Vyhledá trenéra a zobrazí jeho profil."""
        # Defer immediately since DB lookup might take a moment
        await interaction.response.defer(ephemeral=False) # Public response as requested? Or only registered?
        # User requested: "only for registred users".
        # But should the response be ephemeral? "show profile".
        # If I want to show someone else's profile, usually I want to see it.
        # Let's keep it public so others can see it too? Or ephemeral to reduce spam?
        # Let's make it ephemeral for now to be safe, or public if they want to share.
        # Actually, standard lookup commands are often public. But let's stick to ephemeral if user didn't specify,
        # but wait, user said "show profile".
        # Let's make it visible to user only (ephemeral) to avoid spamming the channel with profiles.

        # Check if user is registered (privacy/security measure requested)
        # We need to check if the *caller* is registered.
        accounts = await database.get_user_accounts(interaction.user.id)
        if not accounts:
            await interaction.followup.send("❌ Pro použití tohoto příkazu musíte být registrováni (`/registrace`).", ephemeral=True)
            return

        # Perform search
        results = await database.search_user_accounts(ign)

        if not results:
            await interaction.followup.send(f"❌ Trenér s jménem obsahujícím **'{ign}'** nebyl nalezen.", ephemeral=True)
            return

        # Filter logic
        # 1. Exact match (case insensitive)
        exact_match = next((u for u in results if u['account_name'].lower() == ign.lower()), None)

        if exact_match:
            await self._show_profile(interaction, exact_match)
        elif len(results) == 1:
             await self._show_profile(interaction, results[0])
        else:
            # Multiple partial matches
            # Limit to 10
            options = []
            for u in results[:10]:
                options.append(f"• **{u['account_name']}** ({u['team']})")

            desc = "\n".join(options)
            if len(results) > 10:
                desc += f"\n... a {len(results)-10} dalších."

            embed = discord.Embed(
                title="🔍 Nalezeno více trenérů",
                description=f"Prosím, upřesněte hledání:\n\n{desc}",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def _show_profile(self, interaction: discord.Interaction, user_data):
        team_name = user_data.get('team', 'Unknown')
        team_color = TEAMS.get(team_name, discord.Color.default())

        # Determine emoji for team
        team_emoji = ""
        if team_name == "Mystic": team_emoji = "💙"
        elif team_name == "Valor": team_emoji = "❤️"
        elif team_name == "Instinct": team_emoji = "💛"

        embed = discord.Embed(
            title=f"👤 Profil Trenéra: {user_data['account_name']}",
            color=team_color
        )

        embed.add_field(name="Tým", value=f"{team_emoji} {team_name}", inline=True)
        embed.add_field(name="Region", value=f"📍 {user_data['region']}", inline=True)
        embed.add_field(name="Friend Code", value=f"🆔 `{user_data['friend_code']}`", inline=False)

        if user_data.get('want_more_friends'):
            embed.add_field(name="🤝 Přátelé", value="✅ **Hledá nové přátele!**", inline=False)

        # Try to fetch discord user to show avatar
        try:
            guild = interaction.guild
            if guild:
                member = guild.get_member(user_data['user_id'])
                if not member:
                     member = await guild.fetch_member(user_data['user_id'])

                if member:
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"Discord: {member.display_name}")
        except discord.HTTPException:
            pass

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="hledam_pratele", description="Zobrazit trenéry, kteří hledají nové přátele (Find Friends)")
    async def hledam_pratele(self, interaction: discord.Interaction):
        """Zobrazí seznam trenérů, kteří mají aktivní příznak 'Chci více přátel'."""
        await interaction.response.defer(ephemeral=True)

        # Check registration
        accounts = await database.get_user_accounts(interaction.user.id)
        if not accounts:
            await interaction.followup.send("❌ Pro použití tohoto příkazu musíte být registrováni (`/registrace`).", ephemeral=True)
            return

        users = await database.get_users_wanting_friends(limit=25)

        if not users:
            await interaction.followup.send("❌ Žádní trenéři momentálně nehledají nové přátele.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🤝 Trenéři hledající přátele",
            description="Tito hráči mají zájem o nové Friend Requesty:",
            color=discord.Color.green()
        )

        lines = []
        for u in users:
            team_emoji = "⚪"
            if u['team'] == "Mystic": team_emoji = "💙"
            elif u['team'] == "Valor": team_emoji = "❤️"
            elif u['team'] == "Instinct": team_emoji = "💛"

            line = f"{team_emoji} **{u['account_name']}** - `{u['friend_code']}`"
            lines.append(line)

        embed.add_field(name="Seznam", value="\n".join(lines), inline=False)
        embed.set_footer(text="Pro přidání na tento seznam použijte /chci_vice_pratel")

        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Lookup(bot))
