"""Run-Bild: die Schadensaufteilung je Boss als PNG (Pillow), für Webhook und Bot dasselbe Bild."""
import asyncio
import ctypes
import io
import logging
import subprocess
from datetime import datetime
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .run_model import Boss, Player, Run

log = logging.getLogger(__name__)

# Optik nach dem A2Tools-Meter (src/styles.css dort): dunkles HUD, Balken als Tönung hinter der
# Zeile mit leuchtender Kante, Klassen-Icons, schmale Ziffern. Gezeichnet in doppelter Größe (S).
ASSETS = Path(__file__).parent / "assets"
WEB = Path(__file__).parent / "web"
S = 2
HUD_BG = (9, 13, 24)
ROW_FILL = (95, 191, 135)  # --row-fill
USER_FILL = (106, 166, 255)  # --isUser-fill
HP_KILL = ((71, 212, 125), (46, 167, 95), (216, 255, 232))  # Verlauf oben/unten, Kante
HP_OPEN = ((240, 187, 82), (207, 145, 44), (255, 240, 208))
END_DOT = (123, 109, 255)  # --indicator-end
WHITE = (255, 255, 255)


def _rgba(c: tuple[int, int, int], a: float) -> tuple[int, int, int, int]:
    return (*c, round(255 * a))


def _mix(c: tuple[int, int, int], other: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """t = Anteil von c (wie color-mix(in srgb, c t, other))."""
    return tuple(round(a * t + b * (1 - t)) for a, b in zip(c, other))  # type: ignore[return-value]


@cache
def _font_file(spec: str) -> str | None:
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", spec], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


@cache
def font(kind: str, size: float) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """kind: name/name_bold (Inter wie Pretendard), num/num_bold (Barlow Semi Condensed wie Bahnschrift), cjk."""
    files = {
        "name": WEB / "Inter-Medium.woff2",
        "name_bold": WEB / "Inter-SemiBold.woff2",
        "num": ASSETS / "fonts" / "BarlowSemiCondensed-SemiBold.ttf",
        "num_bold": ASSETS / "fonts" / "BarlowSemiCondensed-Bold.ttf",
    }
    path = str(files[kind]) if kind in files else _font_file("Noto Sans CJK KR:medium")
    px = round(size * S)
    try:
        return ImageFont.truetype(path, px) if path else ImageFont.load_default(px)
    except OSError:
        return ImageFont.load_default(px)


def name_font(name: str, size: float, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Inter hat kein Chinesisch/Koreanisch/Japanisch – dafür Noto Sans CJK (wie .name.isCjk im Meter)."""
    if any(ord(ch) >= 0x2E80 for ch in name):
        return font("cjk", size - 0.5)
    return font("name_bold" if bold else "name", size)


@cache
def class_icon(cls: str, size: int) -> Image.Image | None:
    try:
        return Image.open(ASSETS / "classes" / f"{cls}.png").convert("RGBA").resize((size, size), Image.LANCZOS)
    except OSError:
        return None


def fmt_amount(v: float) -> str:
    if v >= 1e6:
        return f"{v / 1e6:.2f} M".replace(".", ",")
    if v >= 1e4:
        return f"{v / 1e3:.1f} k".replace(".", ",")
    return f"{v:,.0f}".replace(",", ".")


def fmt_time(ms: int) -> str:
    s = round(ms / 1000)
    return f"{s // 60}:{s % 60:02d}"


def _tracked(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, f, fill, tracking: float,
             anchor: str = "la") -> float:
    """Text mit Laufweite (letter-spacing); gibt die Breite zurück. anchor: la oder ra."""
    gap = tracking * S
    w = sum(d.textlength(ch, font=f) for ch in text) + gap * (len(text) - 1)
    x, y = xy
    if anchor == "ra":
        x -= w
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + gap
    return w


def _hgrad(w: int, h: int, color: tuple[int, int, int], a0: float, a1: float) -> Image.Image:
    """Waagerechter Verlauf derselben Farbe von Deckkraft a0 nach a1."""
    # linear_gradient läuft von oben (0) nach unten (255); gespiegelt an der Diagonale → links nach rechts
    mask = Image.linear_gradient("L").transpose(Image.TRANSPOSE).resize((max(1, w), max(1, h)))
    mask = mask.point(lambda v: round(255 * (a0 + (a1 - a0) * v / 255)))
    img = Image.new("RGBA", mask.size, color)
    img.putalpha(mask)
    return img


def _vgrad(w: int, h: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    mask = Image.linear_gradient("L").resize((max(1, w), max(1, h)))
    return Image.composite(Image.new("RGBA", mask.size, bottom), Image.new("RGBA", mask.size, top), mask)


def _rounded(img: Image.Image, r: int) -> Image.Image:
    """Ecken abrunden (overflow: hidden mit border-radius)."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, fill=255)
    out = img.copy()
    out.putalpha(Image.composite(img.getchannel("A"), mask, mask))
    return out


class _Layers:
    """Grundfläche, Leuchten (weichgezeichnet), Textschatten (weichgezeichnet), Text – wie im CSS gestapelt."""

    def __init__(self, size: tuple[int, int]) -> None:
        self.base = Image.new("RGBA", size, (0, 0, 0, 0))
        self.glow = Image.new("RGBA", size, (0, 0, 0, 0))
        self.shadow = Image.new("RGBA", size, (0, 0, 0, 0))
        self.text = Image.new("RGBA", size, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.base)
        self.g = ImageDraw.Draw(self.glow)
        self.s = ImageDraw.Draw(self.shadow)
        self.t = ImageDraw.Draw(self.text)

    def label(self, xy, text, f, fill, anchor="la", shadow=0.85) -> None:
        self.s.text((xy[0], xy[1] + S), text, font=f, fill=(0, 0, 0, round(255 * shadow)), anchor=anchor)
        self.t.text(xy, text, font=f, fill=fill, anchor=anchor)

    def flatten(self) -> Image.Image:
        out = self.base
        out.alpha_composite(self.glow.filter(ImageFilter.GaussianBlur(4 * S)))
        out.alpha_composite(self.shadow.filter(ImageFilter.GaussianBlur(1.5 * S)))
        out.alpha_composite(self.text)
        return out


PANEL_W = 400  # CSS-Pixel wie im Meter (dort 380)
ROW_H = 30
ROW_GAP = 3
PAD = 8


def _panel_height(boss: Boss) -> int:
    rows = len(boss.players)
    head = 40 + (24 if boss.mob else 0)
    return head + 7 + rows * ROW_H + max(0, rows - 1) * ROW_GAP + 9


def _hp_strip(L: _Layers, x: int, y: int, w: int, boss: Boss) -> None:
    """Wie die Boss-HP-Leiste im Meter: besiegt = voll und grün, sonst bernstein bis zum besten Versuch."""
    h = 16 * S
    L.d.rounded_rectangle((x, y, x + w, y + h), 4 * S, fill=(0, 0, 0, 90))
    top, bottom, edge = HP_KILL if boss.killed else HP_OPEN
    fw = round(w * (1.0 if boss.killed else boss.best))
    if fw > 2 * S:
        fill = _vgrad(fw, h, top, bottom)
        fill.putalpha(Image.new("L", fill.size, round(255 * 0.8)))
        L.base.alpha_composite(_rounded(fill, 4 * S), (x, y))
        L.d.rectangle((x + fw - 2 * S, y, x + fw, y + h), fill=edge)
        L.g.rectangle((x + fw - 2 * S, y, x + fw, y + h), fill=_rgba(top, 0.9))
    f = font("num", 10.5)
    left = "BESIEGT" if boss.killed else f"{round(100 * boss.best)} % · NICHT BESIEGT"
    L.s.text((x + 8 * S, y + 2.5 * S + S), left, font=f, fill=(0, 0, 0, 230))
    _tracked(L.t, (x + 8 * S, y + 2.5 * S), left, f, WHITE, 0.6)
    if boss.max_hp:
        hp = f"{fmt_amount(boss.max_hp)} HP"
        L.s.text((x + w - 8 * S, y + 2.5 * S + S), hp, font=f, fill=(0, 0, 0, 230), anchor="ra")
        L.t.text((x + w - 8 * S, y + 2.5 * S), hp, font=f, fill=_rgba(WHITE, 0.72), anchor="ra")


def _row(L: _Layers, x: int, y: int, w: int, rank: int, p: Player, best: int, total: int, secs: float) -> None:
    h = ROW_H * S
    row = Image.new("RGBA", (w, h), (255, 255, 255, 9))  # --hud-row-bg
    bar = USER_FILL if p.you else ROW_FILL
    fw = max(2 * S, round(w * p.dmg / best))
    # Balken = Tönung hinter der Zeile (30 % → 62 %, mal 0,8 Deckkraft) …
    row.alpha_composite(_hgrad(fw, h, bar, 0.30 * 0.8, 0.62 * 0.8))
    rd = ImageDraw.Draw(row)
    # … mit heller Kante am Ende, die leuchtet
    rd.rectangle((fw - 2 * S, 0, fw - 1, h), fill=_mix(bar, WHITE, 0.35))
    if p.you:  # eigene Zeile: Leuchtschiene links
        rd.rectangle((0, 0, 2 * S - 1, h), fill=USER_FILL)
    # Abdunklung hinter den Zahlen rechts (wie der Scrim im Meter)
    scrim_w = 190 * S
    row.alpha_composite(_hgrad(scrim_w, h, HUD_BG, 0.0, 0.8), (w - scrim_w, 0))
    L.base.alpha_composite(_rounded(row, 4 * S), (x, y))
    L.g.rectangle((x + fw - 3 * S, y, x + fw + S, y + h), fill=_rgba(bar, 0.75))
    if p.you:
        L.g.rectangle((x, y, x + 2 * S, y + h), fill=_rgba(USER_FILL, 0.7))

    cy = y + h // 2
    cx = x + 6 * S
    rf = font("num", 11)
    L.label((cx + 13 * S, cy), str(rank), rf, _rgba(WHITE, 0.8 if rank == 1 else 0.3), anchor="rm", shadow=0.9)
    cx += 13 * S + 7 * S
    icon = class_icon(p.cls, 20 * S) if p.cls else None
    if icon:
        sh = Image.new("RGBA", icon.size, (0, 0, 0, 0))
        sh.putalpha(icon.getchannel("A").point(lambda v: v * 0.8))
        L.shadow.alpha_composite(sh, (cx, cy - 10 * S + S))
        L.text.alpha_composite(icon, (cx, cy - 10 * S))
    cx += 20 * S + 7 * S
    nf = name_font(p.name, 14.5, p.you)
    L.label((cx, cy), p.name, nf, _rgba(WHITE, 0.95), anchor="lm")

    # Anzeige rechts: Gesamtschaden (leise) · DPS (groß) · Anteil
    rx = x + w - 8 * S
    pct = f"{100 * p.dmg / total:.1f}".replace(".", ",") + " %"
    pf, df, sf = font("num", 11.5), font("num_bold", 16.5), font("num", 11.5)
    L.label((rx, cy), pct, pf, _rgba(WHITE, 0.88), anchor="rm", shadow=0.95)
    rx -= max(L.t.textlength(pct, font=pf), 40 * S) + 9 * S
    dps = fmt_amount(p.dmg / secs) + "/s"
    L.label((rx, cy), dps, df, WHITE, anchor="rm", shadow=0.95)
    rx -= L.t.textlength(dps, font=df) + 10 * S
    amount = fmt_amount(p.dmg)
    L.label((rx, cy), amount, sf, _rgba(WHITE, 0.45), anchor="rm", shadow=0.9)
    rx -= L.t.textlength(amount, font=sf)

    # Itemlevel und Kampfkraft hinter dem Namen, nur wenn Platz bis zu den Zahlen ist
    info = player_info(p)
    if info:
        inf = font("num", 11)
        ix = cx + L.t.textlength(p.name, font=nf) + 8 * S
        if ix + L.t.textlength(info, font=inf) <= rx - 10 * S:
            L.label((ix, cy), info, inf, _rgba(WHITE, 0.5), anchor="lm", shadow=0.9)


def player_info(p: Player) -> str:
    """„IL 2848 · KK 163,8 k“; leer, wenn das Meter nichts dazu weiß."""
    parts = ([f"IL {p.gear}"] if p.gear else []) + ([f"KK {fmt_amount(p.cp)}"] if p.cp else [])
    return " · ".join(parts)


def _panel(boss: Boss, height: int) -> Image.Image:
    w, h = PANEL_W * S, height * S
    L = _Layers((w, h))
    L.d.rounded_rectangle((0, 0, w - 1, h - 1), 10 * S, fill=(*_mix(WHITE, HUD_BG, 0.035), 245),
                          outline=(255, 255, 255, 31), width=S)
    # Kopf: Bossname links, Kampfzeit (+ Versuche) rechts
    tf = font("name_bold", 15.5)
    L.label((12 * S, 21 * S), boss.name if boss.mob else "Gesamt", tf, _rgba(WHITE, 0.96), anchor="lm")
    mf = font("num", 13)
    meta = fmt_time(boss.duration_ms)
    if boss.attempts > 1:
        meta = f"{boss.attempts} Kämpfe · {meta}"
    if not boss.mob:
        meta = f"Kampfzeit {meta}"
    L.label((w - 12 * S, 21 * S), meta, mf, _rgba(WHITE, 0.5), anchor="rm")
    y = 40 * S
    if boss.mob:
        _hp_strip(L, PAD * S, y, w - 2 * PAD * S, boss)
        y += 24 * S
    y += 7 * S
    players = sorted(boss.players.values(), key=lambda p: -p.dmg)
    best = max((p.dmg for p in players), default=1) or 1
    total = boss.total or 1
    secs = max(1.0, boss.duration_ms / 1000)
    for i, p in enumerate(players):
        _row(L, PAD * S, y, w - 2 * PAD * S, i + 1, p, best, total, secs)
        y += (ROW_H + ROW_GAP) * S
    return L.flatten()


def render_run(run: Run) -> bytes:
    """Run → Bild (WebP): Kopf mit Dungeon, dann je ein Meter-Fenster für „Gesamt“ und jeden Boss."""
    bosses = run.bosses()
    panels = [run.total(), *bosses] if len(bosses) > 1 else bosses
    cols = 1 if len(panels) == 1 else 2 if len(panels) <= 4 else 3
    rows = [panels[i:i + cols] for i in range(0, len(panels), cols)]
    heights = [max(_panel_height(b) for b in r) for r in rows]
    gap, margin, head, foot = 16, 28, 92, 30
    W = (margin * 2 + cols * PANEL_W + (cols - 1) * gap) * S
    H = (margin + head + sum(heights) + gap * (len(rows) - 1) + foot) * S

    img = Image.new("RGBA", (W, H), (*HUD_BG, 255))
    # leichtes Leuchten oben links, damit die Fläche nicht tot wirkt. Ein so weicher Verlauf sieht
    # in 1/8 gerechnet und hochskaliert gleich aus, kostet aber nur einen Bruchteil.
    q = 8
    halo = Image.new("RGBA", (W // q, H // q), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((-W // 4 // q, -H // 2 // q, W // 2 // q, H // 3 // q), fill=(95, 202, 255, 22))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(80 * S / q)).resize((W, H), Image.BILINEAR))

    L = _Layers((W, (margin + head) * S))  # nur der Kopf
    x0 = margin * S
    L.label((x0, margin * S), run.name, font("name_bold", 28), WHITE, shadow=0.6)
    start = datetime.fromtimestamp(run.start_ms / 1000)
    end = datetime.fromtimestamp(run.end_ms / 1000)
    kills = run.kills
    sub = (f"{start:%d.%m.%Y}  ·  {start:%H:%M}–{end:%H:%M}  ·  {kills}/{len(bosses)} "
           f"{'BOSS' if len(bosses) == 1 else 'BOSSE'}  ·  KAMPFZEIT {fmt_time(sum(b.duration_ms for b in bosses))}")
    _tracked(L.t, (x0, (margin + 44) * S), sub, font("num", 14), _rgba(WHITE, 0.5), 0.8)
    # Status-Chip rechts oben
    chip = "RUN ABGESCHLOSSEN" if run.complete or kills == len(bosses) else "RUN BEENDET"
    cf = font("num", 12)
    cw = sum(L.t.textlength(ch, font=cf) for ch in chip) + 0.8 * S * (len(chip) - 1)
    cx1, cy0 = W - x0, (margin + 6) * S
    cx0 = cx1 - cw - 34 * S
    L.d.rounded_rectangle((cx0, cy0, cx1, cy0 + 26 * S), 13 * S, fill=(255, 255, 255, 14), outline=(255, 255, 255, 36), width=S)
    dot = END_DOT if chip == "RUN ABGESCHLOSSEN" else HP_OPEN[0]
    L.d.ellipse((cx0 + 12 * S, cy0 + 10 * S, cx0 + 18 * S, cy0 + 16 * S), fill=dot)
    L.g.ellipse((cx0 + 10 * S, cy0 + 8 * S, cx0 + 20 * S, cy0 + 18 * S), fill=_rgba(dot, 0.9))
    _tracked(L.t, (cx0 + 25 * S, cy0 + 5.5 * S), chip, cf, _rgba(WHITE, 0.85), 0.8)
    img.alpha_composite(L.flatten())

    y = (margin + head) * S
    for r, rh in zip(rows, heights):
        for i, boss in enumerate(r):
            px = x0 + i * (PANEL_W + gap) * S
            p = _panel(boss, rh)
            # Schatten nur in Panelgröße plus Rand für die Unschärfe (nicht über die ganze Leinwand)
            m = 3 * 14 * S
            shadow = Image.new("RGBA", (p.width + 2 * m, p.height + 2 * m), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rounded_rectangle((m, m, m + p.width, m + p.height), 10 * S, fill=(0, 0, 0, 115))
            sx, sy = px - m, y + 8 * S - m
            crop = (max(0, -sx), max(0, -sy))
            img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14 * S)), (max(0, sx), max(0, sy)), crop)
            img.alpha_composite(p, (px, y))
        y += (rh + gap) * S
    d = ImageDraw.Draw(img)
    _tracked(d, (W - x0, H - (foot - 6) * S), "NEXBOARD  ·  DATEN: A2TOOLS DPS METER", font("num", 11),
             _rgba(WHITE, 0.25), 1.0, anchor="ra")
    buf = io.BytesIO()
    # verlustfreies WebP: ~30 % kleiner als PNG; method 4 wäre noch kleiner, braucht aber +50 MB
    img.convert("RGB").save(buf, "WEBP", lossless=True, method=0)
    del img, L
    _trim()
    return buf.getvalue()


async def run_image(run: Run) -> bytes:
    """Run-Bild einmal rendern und am Run merken: Webhook und Bot posten dasselbe Bild."""
    if run.bild is None:
        run.bild = await asyncio.to_thread(render_run, run)
    return run.bild


def _trim() -> None:
    """Nach dem Rendern (~70 MB Spitze) den freien Speicher ans System zurückgeben; glibc behält
    ihn sonst im Prozess (gemessen: +28 MB statt +6 MB nach einem Run-Bild)."""
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):  # nicht glibc
        pass
