import aiohttp
import asyncio
import os
import math
import logging
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
# from data.pokemon import POKEMON_IMAGES, POKEMON_IDS # REMOVED: Using DB data
import qrcode
import database # To fetch URLs if needed or rely on passed data

logger = logging.getLogger('discord')

SPRITE_DIR = "data/sprites"
MAX_ITEMS = 100

class ImageGenerator:
    def __init__(self):
        self.sprite_dir = SPRITE_DIR
        if not os.path.exists(self.sprite_dir):
            os.makedirs(self.sprite_dir)

    async def _download_image(self, session, url, filepath):
        try:
            # logger.info(f"Downloading image from {url} to {filepath}")
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    # Write in executor to avoid blocking disk IO on main thread
                    await asyncio.to_thread(self._write_file, filepath, data)
                    return True
                else:
                    logger.warning(f"Failed to download image from {url}: Status {resp.status}")
        except Exception as e:
            logger.error(f"Error downloading image {url}: {e}")
        return False

    def _write_file(self, filepath, data):
        with open(filepath, 'wb') as f:
            f.write(data)

    async def prepare_sprites(self, listings):
        """Downloads missing sprites asynchronously."""
        tasks = []
        needed = set()

        for item in listings:
            # Prefer explicit pokedex_num if available (aliases sometimes confusing)
            pid = item.get('pokedex_num') or item.get('pokemon_id')

            # If pid matches species_id but we want dex num, this check is hard without context.
            # But get_account_listings returns p.pokedex_num as pokemon_id.

            if pid is None:
                logger.warning(f"Item missing pokemon_id/pokedex_num: {item}")
                continue

            pform = item.get('pokemon_form', 'Normal')
            is_shiny = item['is_shiny']

            # Construct filename: {id}_{form}_{shiny}.png
            # Sanitize form name
            safe_form = pform.replace(" ", "_").lower()

            # Add v1 prefix to bust cache if old files were wrong
            filename = f"v1_{pid}_{safe_form}_{'shiny' if is_shiny else 'normal'}.png"
            filepath = os.path.join(self.sprite_dir, filename)

            if (pid, pform, is_shiny) in needed:
                continue
            needed.add((pid, pform, is_shiny))

            if not os.path.exists(filepath):
                # Get URL from item (it comes from DB join)
                url = item.get('image_url')
                if url:
                    tasks.append((url, filepath))
                else:
                    logger.warning(f"No image_url for Pokemon ID {pid} ({pform})")

        if tasks:
            async with aiohttp.ClientSession() as session:
                download_tasks = [self._download_image(session, url, path) for url, path in tasks]
                await asyncio.gather(*download_tasks)

    def _get_sprite_sync(self, pokemon_id, pokemon_form, is_shiny):
        """Sync function to load image from disk."""
        safe_form = pokemon_form.replace(" ", "_").lower()
        # Ensure we use the v1 prefix
        filename = f"v1_{pokemon_id}_{safe_form}_{'shiny' if is_shiny else 'normal'}.png"
        filepath = os.path.join(self.sprite_dir, filename)

        if os.path.exists(filepath):
            try:
                img = Image.open(filepath).convert("RGBA")
                return img
            except Exception as e:
                logger.error(f"Error opening image {filepath}: {e}")
        return None

    def _draw_star(self, draw, xy, size, fill):
        """Draws a 5-pointed star."""
        x, y = xy
        points = []
        for i in range(10):
            angle = i * 36 * 3.14159 / 180
            r = size if i % 2 == 0 else size / 2
            points.append((x + r * math.sin(angle), y - r * math.cos(angle)))
        draw.polygon(points, fill=fill)

    def _draw_badge(self, draw, text, center_xy, bg_color, text_color, font):
        """Draws a small pill/badge with text."""
        x, y = center_xy

        # Calculate text size
        bbox = draw.textbbox((0,0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # Badge size (padding)
        pad_x = 4
        pad_y = 2
        w = tw + pad_x * 2
        h = th + pad_y * 2

        x0, y0 = x - w/2, y - h/2
        x1, y1 = x + w/2, y + h/2

        draw.rectangle([x0, y0, x1, y1], fill=bg_color)

        # Center text
        tx = x - tw/2
        ty = y - th/2 - 1 # visual adjustment
        draw.text((tx, ty), text, font=font, fill=text_color)

    def _generate_card_sync(self, listings, title, user_name, team_color_rgb, friend_code):
        """Sync implementation of image generation."""
        num_items = len(listings)
        cols = math.ceil(math.sqrt(num_items))
        if cols < 3: cols = 3
        if cols > 6: cols = 6

        rows = math.ceil(num_items / cols)

        # Dimensions
        CELL_W, CELL_H = 120, 150
        MARGIN = 20
        HEADER_H = 60 # Increased height for QR code

        # QR in Header
        QR_SIZE = 50 # Smaller QR for header

        TITLE_H = 20
        FOOTER_H = 30

        # Title Section Height (Title + Padding)
        TOP_SECTION_H = HEADER_H + 10 + TITLE_H + 10

        IMG_W = cols * CELL_W + 2 * MARGIN
        IMG_H = TOP_SECTION_H + rows * CELL_H + MARGIN + FOOTER_H

        bg_color = (54, 57, 63)
        img = Image.new('RGBA', (IMG_W, IMG_H), bg_color)
        draw = ImageDraw.Draw(img)

        # --- Fonts ---
        try:
            # Reduced font sizes as requested
            font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 16) # Slightly larger title
            font_user = ImageFont.truetype("DejaVuSans-Bold.ttf", 18) # Larger user name
            font_fc = ImageFont.truetype("DejaVuSans-Bold.ttf", 12)   # Font for FC next to QR
            font_text = ImageFont.truetype("DejaVuSans.ttf", 14)
            font_small = ImageFont.truetype("DejaVuSans.ttf", 10)
            font_badge = ImageFont.truetype("DejaVuSans-Bold.ttf", 10)
            font_footer = ImageFont.truetype("DejaVuSans.ttf", 12)
        except OSError:
            font_title = ImageFont.load_default()
            font_user = ImageFont.load_default()
            font_fc = ImageFont.load_default()
            font_text = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_badge = ImageFont.load_default()
            font_footer = ImageFont.load_default()

        # --- Header ---
        # Team Colored Strip
        draw.rectangle([(0, 0), (IMG_W, HEADER_H)], fill=team_color_rgb)

        # User Name inside Header (Left Aligned)
        draw.text((MARGIN, HEADER_H / 2), user_name, font=font_user, fill=(255, 255, 255), anchor="lm")

        # --- QR Code & FC in Header ---
        if friend_code:
            try:
                qr = qrcode.make(friend_code)
                qr = qr.resize((QR_SIZE, QR_SIZE), Image.Resampling.LANCZOS)

                # Position: Right side with margin
                qr_x = IMG_W - MARGIN - QR_SIZE
                qr_y = (HEADER_H - QR_SIZE) // 2

                img.paste(qr, (qr_x, qr_y))

                # FC Text: Left of QR
                fc_text = f"FC: {friend_code}"

                # Align right side of text to left side of QR (with 10px padding)
                fc_x = qr_x - 10
                fc_y = HEADER_H / 2

                draw.text((fc_x, fc_y), fc_text, font=font_fc, fill=(255, 255, 255), anchor="rm")

            except Exception as e:
                logger.error(f"Error generating QR code: {e}")

        # --- Title Section ---
        current_y = HEADER_H + 10
        draw.text((IMG_W // 2, current_y), title, font=font_title, fill=(255, 255, 255), anchor="mt")

        # --- Grid ---
        grid_start_y = TOP_SECTION_H

        for i, item in enumerate(listings):
            col = i % cols
            row = i // cols

            x = MARGIN + col * CELL_W
            y = grid_start_y + row * CELL_H

            draw.rectangle([(x + 2, y + 2), (x + CELL_W - 2, y + CELL_H - 2)], fill=(47, 49, 54), outline=None)

            # Prefer explicit pokedex_num if available
            pokemon_id = item.get('pokedex_num') or item.get('pokemon_id')
            pokemon_form = item.get('pokemon_form', 'Normal')
            is_shiny = item['is_shiny']
            is_purified = item['is_purified']
            is_dynamax = item.get('is_dynamax', False)
            is_gigantamax = item.get('is_gigantamax', False)
            is_background = item.get('is_background', False)
            is_adventure_effect = item.get('is_adventure_effect', False)

            sprite = self._get_sprite_sync(pokemon_id, pokemon_form, is_shiny)
            if sprite:
                sw, sh = sprite.size
                scale = min(90/sw, 90/sh, 1.0)
                new_size = (int(sw*scale), int(sh*scale))
                sprite = sprite.resize(new_size, Image.Resampling.LANCZOS)

                px = x + (CELL_W - new_size[0]) // 2
                py = y + 10 + (90 - new_size[1]) // 2
                img.alpha_composite(sprite, (px, py))

            # Name from DB
            p_name = item.get('pokemon_name', "Unknown")
            if pokemon_form != 'Normal':
                 # Maybe shorten form?
                 # p_name += f" ({pokemon_form})"
                 # If name is too long, maybe just name?
                 pass

            if len(p_name) > 12:
                p_name = p_name[:10] + "..."

            bbox = draw.textbbox((0,0), p_name, font=font_text)
            text_w = bbox[2] - bbox[0]
            tx = x + (CELL_W - text_w) // 2
            ty = y + 110
            draw.text((tx, ty), p_name, font=font_text, fill=(255, 255, 255))

            id_text = f"#{pokemon_id}"
            bbox2 = draw.textbbox((0,0), id_text, font=font_small)
            text_w2 = bbox2[2] - bbox2[0]
            tx2 = x + (CELL_W - text_w2) // 2
            ty2 = y + 130
            draw.text((tx2, ty2), id_text, font=font_small, fill=(150, 150, 150))

            # --- Status Indicators ---

            # Shiny: Top Right
            if is_shiny:
                cx = x + CELL_W - 15
                cy = y + 15
                self._draw_star(draw, (cx, cy), 8, fill=(255, 215, 0))

            # Purified: Top Left
            if is_purified:
                cx = x + 15
                cy = y + 15
                draw.ellipse([(cx-6, cy-6), (cx+6, cy+6)], fill=(200, 200, 255))
                draw.text((cx-3, cy-5), "P", font=font_small, fill=(0, 0, 0))

            # Dynamax / Gigantamax: Top Center
            # Priority to Gigantamax if both set (usually Gmax implies Dmax)
            if is_gigantamax:
                self._draw_badge(draw, "Giga", (x + CELL_W/2, y + 15), (139, 0, 0), (255, 255, 255), font_badge)
            elif is_dynamax:
                self._draw_badge(draw, "Dyna", (x + CELL_W/2, y + 15), (255, 20, 147), (255, 255, 255), font_badge)

            # Background: Bottom Right (above text)
            if is_background:
                self._draw_badge(draw, "BG", (x + CELL_W - 20, y + 95), (0, 100, 0), (255, 255, 255), font_badge)

            # Adventure Effect: Bottom Left (above text)
            if is_adventure_effect:
                self._draw_badge(draw, "Adv", (x + 20, y + 95), (75, 0, 130), (255, 255, 255), font_badge)

        # --- Footer ---
        footer_text = "senpai.cz/pogo"
        footer_y = IMG_H - FOOTER_H / 2
        draw.text((IMG_W // 2, footer_y), footer_text, font=font_footer, fill=(180, 180, 180), anchor="mm")

        out = BytesIO()
        img.save(out, format='PNG', optimize=True)
        out.seek(0)
        return out

    async def generate_card(self, listings, title, user_name, team_color_rgb, friend_code=None):
        """
        Generates a trade card image (Async Wrapper).
        """
        if not listings:
            return None

        # Limit items
        if len(listings) > MAX_ITEMS:
            listings = listings[:MAX_ITEMS]

        # 1. Download missing sprites (Network IO)
        await self.prepare_sprites(listings)

        # 2. Generate image (CPU/Disk IO) - Run in executor
        loop = asyncio.get_running_loop()
        image_buffer = await loop.run_in_executor(
            None,
            self._generate_card_sync,
            listings, title, user_name, team_color_rgb, friend_code
        )

        return image_buffer
