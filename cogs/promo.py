import discord
from discord.ext import commands, tasks
import database
import services.scraper as scraper
import logging

logger = logging.getLogger('discord')

class Promo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.promo_check_task.start()

    def cog_unload(self):
        self.promo_check_task.cancel()

    @tasks.loop(minutes=60)
    async def promo_check_task(self):
        """Background task to check for new promo codes."""
        logger.info("Starting periodic promo code check...")
        try:
            new_codes = await scraper.scrape_promo_codes()
            if not new_codes:
                return

            for item in new_codes:
                code = item['code']
                description = item['description']
                image_url = item.get('image_url')

                # Check if we've seen this code
                if not await database.is_promo_code_seen(code):
                    logger.info(f"New promo code found: {code}")
                    # Add to database
                    await database.add_seen_promo_code(code, description)
                    # Notify guilds
                    await self.notify_new_code(code, description, image_url)

        except Exception as e:
            logger.error(f"Error in promo_check_task: {e}")

    async def notify_new_code(self, code, description, image_url=None):
        """Sends a notification to all configured guilds."""
        embed = discord.Embed(
            title="🎫 Nový Promo Kód!",
            description=f"Byl nalezen nový promo kód pro Pokémon GO.",
            color=0x2ECC71 # Green color
        )
        embed.add_field(name="🎁 Odměna", value=description, inline=False)
        embed.add_field(name="⌨️ Kód k uplatnění", value=f"```\n{code}\n```", inline=False)
        
        redemption_url = f"https://store.pokemongo.com/offer-redemption?passcode={code}"
        embed.add_field(name="🔗 Odkaz pro aktivaci", value=f"[Klikněte zde pro uplatnění]({redemption_url})", inline=False)
        
        if image_url:
            embed.set_thumbnail(url=image_url)
        
        embed.set_footer(text="MasterGentleman Promo Monitor • Zdroj: LeekDuck")
        embed.timestamp = discord.utils.utcnow()

        for guild in self.bot.guilds:
            config = await database.get_guild_config(guild.id)
            if config and config.get('promo_channel_id'):
                channel = guild.get_channel(config['promo_channel_id'])
                if channel:
                    try:
                        await channel.send(embed=embed)
                        logger.info(f"Notified guild {guild.id} about code {code}")
                    except Exception as e:
                        logger.error(f"Failed to send promo alert to guild {guild.id}: {e}")

    @promo_check_task.before_loop
    async def before_promo_check(self):
        await self.bot.wait_until_ready()

    @commands.command(name="checkpromo", hidden=True)
    @commands.is_owner()
    async def manual_promo_check(self, ctx):
        """Manually trigger a promo code check."""
        await ctx.send("🔍 Kontroluji promo kódy...")
        await self.promo_check_task()
        await ctx.send("✅ Kontrola dokončena.")

async def setup(bot):
    await bot.add_cog(Promo(bot))
