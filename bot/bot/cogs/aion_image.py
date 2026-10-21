"""Balkendiagramme (PNG) für AION-2-Lauf-Posts — wie die DPS-Rangliste, nur als Bild statt Text,
analog zur Rangkarte in rankcard.py (selbe DejaVu-Schrift, selbes Pillow-Fallback-Muster). Je ein
Bild für die Gesamt-Rangliste und eines pro Boss.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

WIDTH = 960
HEADER_HEIGHT = 110
BOSS_HEADER_HEIGHT = 70
ROW_HEIGHT = 52
MARGIN = 36
MAX_ROWS = 10

BG_COLOUR = (35, 39, 42)
TRACK_COLOUR = (60, 64, 68)
TEXT_COLOUR = (255, 255, 255)
MUTED_COLOUR = (170, 170, 170)
GOLD = (240, 186, 60)
SILVER = (200, 200, 205)
BRONZE = (205, 140, 90)
ACCENT = (88, 101, 242)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

RANK_COLOURS = [GOLD, SILVER, BRONZE]


def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _draw_rows(draw: ImageDraw.ImageDraw, rows: list[dict], top: int) -> None:
    from .aion_dedup import fmt_dps, fmt_num

    max_damage = rows[0]["damage"] if rows else 0
    name_x = MARGIN
    name_width = 220
    bar_x = MARGIN + name_width
    bar_width = WIDTH - bar_x - MARGIN - 170
    value_x = bar_x + bar_width + 16

    for i, p in enumerate(rows):
        y = top + i * ROW_HEIGHT
        bar_y = y + (ROW_HEIGHT - 26) // 2
        colour = RANK_COLOURS[i] if i < len(RANK_COLOURS) else ACCENT

        draw.text((name_x, y + 14), f"{i + 1}.", font=_font(FONT_BOLD, 20), fill=MUTED_COLOUR)
        name = str(p.get("name") or "?")
        draw.text((name_x + 32, y + 14), name[:18], font=_font(FONT_BOLD, 20), fill=TEXT_COLOUR)

        draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_width, bar_y + 26), radius=13, fill=TRACK_COLOUR)
        fraction = min(1.0, p["damage"] / max_damage) if max_damage else 0.0
        if fraction > 0:
            filled = max(26, int(bar_width * fraction))
            draw.rounded_rectangle((bar_x, bar_y, bar_x + filled, bar_y + 26), radius=13, fill=colour)

        value_text = f"{fmt_num(p['damage'])}  {fmt_dps(p.get('dps') or 0)}"
        draw.text((value_x, y + 14), value_text, font=_font(FONT_REGULAR, 20), fill=MUTED_COLOUR)


def render_run_image(
    dungeon: str, difficulty: str | None, players: list[dict], bosses_killed: int,
    bosses_total: int, fight_ms: int,
) -> io.BytesIO:
    rows = players[:MAX_ROWS]
    height = HEADER_HEIGHT + max(1, len(rows)) * ROW_HEIGHT + MARGIN
    img = Image.new("RGB", (WIDTH, height), BG_COLOUR)
    draw = ImageDraw.Draw(img)

    title = dungeon + (f" ({difficulty})" if difficulty else "")
    draw.text((MARGIN, 24), title, font=_font(FONT_BOLD, 34), fill=TEXT_COLOUR)
    minutes, seconds = divmod(round(fight_ms / 1000), 60)
    subtitle = f"{bosses_killed}/{bosses_total} Bosse besiegt  •  Kampfzeit {minutes}:{seconds:02d}"
    draw.text((MARGIN, 70), subtitle, font=_font(FONT_REGULAR, 22), fill=MUTED_COLOUR)

    _draw_rows(draw, rows, HEADER_HEIGHT)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def render_boss_image(boss_name: str, players: list[dict]) -> io.BytesIO:
    rows = players[:MAX_ROWS]
    height = BOSS_HEADER_HEIGHT + max(1, len(rows)) * ROW_HEIGHT + MARGIN
    img = Image.new("RGB", (WIDTH, height), BG_COLOUR)
    draw = ImageDraw.Draw(img)

    draw.text((MARGIN, 20), boss_name, font=_font(FONT_BOLD, 30), fill=TEXT_COLOUR)
    _draw_rows(draw, rows, BOSS_HEADER_HEIGHT)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
