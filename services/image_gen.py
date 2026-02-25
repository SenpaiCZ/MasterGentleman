import aiohttp
import asyncio
import os
import math
import logging
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from data.pokemon import POKEMON_IMAGES, POKEMON_IDS

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
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    # Write in executor to avoid blocking disk IO on main thread
                    await asyncio.to_thread(self._write_file, filepath, data)
                    return True
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
            pid = item['pokemon_id']
            is_shiny = item['is_shiny']
            key = (pid, is_shiny)
            if key in needed:
                continue
            needed.add(key)

            img_info = POKEMON_IMAGES.get(pid)
            if not img_info:
                continue

            url = img_info.get('shiny') if is_shiny else img_info.get('normal')
            if not url:
                url = img_info.get('normal')

            if not url:
                continue

            filename = f"{pid}_{'shiny' if is_shiny else 'normal'}.png"
            filepath = os.path.join(self.sprite_dir, filename)

            if not os.path.exists(filepath):
                tasks.append((url, filepath))

        if tasks:
            async with aiohttp.ClientSession() as session:
                download_tasks = [self._download_image(session, url, path) for url, path in tasks]
                await asyncio.gather(*download_tasks)

    def _get_sprite_sync(self, pokemon_id, is_shiny):
        """Sync function to load image from disk."""
        filename = f"{pokemon_id}_{'shiny' if is_shiny else 'normal'}.png"
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

    def _generate_card_sync(self, listings, title, user_name, team_color_rgb):
        """Sync implementation of image generation."""
        num_items = len(listings)
        cols = math.ceil(math.sqrt(num_items))
        if cols < 3: cols = 3
        if cols > 6: cols = 6

        rows = math.ceil(num_items / cols)

        # Dimensions
        CELL_W, CELL_H = 120, 150
        MARGIN = 20
        HEADER_H = 60

        IMG_W = cols * CELL_W + 2 * MARGIN
        IMG_H = rows * CELL_H + 2 * MARGIN + HEADER_H

        bg_color = (54, 57, 63)
        img = Image.new('RGBA', (IMG_W, IMG_H), bg_color)
        draw = ImageDraw.Draw(img)

        # Header
        draw.rectangle([(0, 0), (IMG_W, 10)], fill=team_color_rgb)

        try:
            font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
            font_text = ImageFont.truetype("DejaVuSans.ttf", 14)
            font_small = ImageFont.truetype("DejaVuSans.ttf", 10)
        except OSError:
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()
            font_small = ImageFont.load_default()

        draw.text((MARGIN, 20), title, font=font_title, fill=(255, 255, 255))
        draw.text((IMG_W - MARGIN - 100, 25), user_name, font=font_text, fill=(200, 200, 200), anchor="ra")

        for i, item in enumerate(listings):
            col = i % cols
            row = i // cols

            x = MARGIN + col * CELL_W
            y = MARGIN + HEADER_H + row * CELL_H

            draw.rectangle([(x + 2, y + 2), (x + CELL_W - 2, y + CELL_H - 2)], fill=(47, 49, 54), outline=None)

            pokemon_id = item['pokemon_id']
            is_shiny = item['is_shiny']
            is_purified = item['is_purified']

            sprite = self._get_sprite_sync(pokemon_id, is_shiny)
            if sprite:
                sw, sh = sprite.size
                scale = min(90/sw, 90/sh, 1.0)
                new_size = (int(sw*scale), int(sh*scale))
                sprite = sprite.resize(new_size, Image.Resampling.LANCZOS)

                px = x + (CELL_W - new_size[0]) // 2
                py = y + 10 + (90 - new_size[1]) // 2
                img.alpha_composite(sprite, (px, py))

            p_name = POKEMON_IDS.get(pokemon_id, "Unknown")
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

            if is_shiny:
                cx = x + CELL_W - 15
                cy = y + 15
                self._draw_star(draw, (cx, cy), 8, fill=(255, 215, 0))

            if is_purified:
                cx = x + 15
                cy = y + 15
                draw.ellipse([(cx-6, cy-6), (cx+6, cy+6)], fill=(200, 200, 255))
                draw.text((cx-3, cy-5), "P", font=font_small, fill=(0, 0, 0))

        out = BytesIO()
        img.save(out, format='PNG', optimize=True)
        out.seek(0)
        return out

    async def generate_card(self, listings, title, user_name, team_color_rgb):
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
            listings, title, user_name, team_color_rgb
        )

        return image_buffer
