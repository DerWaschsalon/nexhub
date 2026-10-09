#!/usr/bin/env python3
"""Erzeugt alle generierten Assets für DeckBar.

    uv run --with pillow tools/gen_assets.py            # alles
    uv run --with pillow tools/gen_assets.py --bg foto.jpg   # eigenes Hintergrundbild

Ausgaben (alle eingecheckt, damit Firmware/Simulator ohne Node bauen):
  shared-ui/fonts/*.c            LVGL-Schriften (lv_font_conv, via npx)
  shared-ui/src/icons_table.c    Icon-Name -> UTF-8-Glyph
  shared-ui/assets/bg_default.c  vorgeblurrter Hintergrund, RGB565 mit Dithering
  daemon/deckbar_daemon/web/icons.json + mdi.woff   für die Web-UI
  docs/icons.md
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / ".cache"
MDI_VERSION = "7.4.47"
INTER_URL = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
LV_FONT_CONV = "lv_font_conv@1.5.3"

W, H = 640, 172

# Latin-1 + Latin Extended-A + typografische Zeichen (– — ‘ ’ ‚ “ ” „ • … €)
TEXT_RANGES = "0x20-0x7E,0xA0-0x17F,0x2013-0x2014,0x2018-0x201E,0x2022,0x2026,0x20AC"

TEXT_FONTS = [
    # (C-Name, Datei, Größe)
    ("db_font_label", "Inter-Medium.ttf", 14),
    ("db_font_small", "Inter-Medium.ttf", 12),
    ("db_font_title", "Inter-SemiBold.ttf", 17),
    ("db_font_value", "Inter-SemiBold.ttf", 22),
]
ICON_FONTS = [("db_icons_20", 20), ("db_icons_28", 28), ("db_icons_40", 40)]


def fetch_mdi() -> Path:
    pkg = CACHE / "package"
    if not (pkg / "css" / "materialdesignicons.css").exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        url = f"https://registry.npmjs.org/@mdi/font/-/font-{MDI_VERSION}.tgz"
        print("lade", url)
        with urllib.request.urlopen(url) as r:
            tarfile.open(fileobj=io.BytesIO(r.read())).extractall(CACHE, filter="data")
    return pkg


def fetch_inter() -> Path:
    d = CACHE / "inter"
    ttf = d / "extras" / "ttf"
    if not ttf.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print("lade", INTER_URL)
        with urllib.request.urlopen(INTER_URL) as r:
            zipfile.ZipFile(io.BytesIO(r.read())).extractall(d)
    return ttf


def read_icon_names() -> list[str]:
    names = []
    for line in (ROOT / "tools" / "icons.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def mdi_codepoints(pkg: Path) -> dict[str, int]:
    css = (pkg / "css" / "materialdesignicons.css").read_text()
    return {m[1]: int(m[2], 16) for m in re.finditer(r'\.mdi-([a-z0-9-]+)::before\s*\{\s*content:\s*"\\([0-9A-Fa-f]+)"', css)}


def lv_font_conv(name: str, font: Path, size: int, ranges: str) -> None:
    out = ROOT / "shared-ui" / "fonts" / f"{name}.c"
    cmd = [
        "npx", "-y", LV_FONT_CONV,
        "--font", str(font), "-r", ranges,
        "--size", str(size), "--bpp", "4", "--no-compress",
        "--format", "lvgl", "--lv-include", "lvgl.h", "--lv-font-name", name,
        "-o", str(out),
    ]
    print("  ", name)
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # absolute Pfade aus dem Opts-Kommentar entfernen
    out.write_text(out.read_text().replace(str(ROOT) + "/", ""))


def gen_fonts(pkg: Path, icons: dict[str, int]) -> None:
    (ROOT / "shared-ui" / "fonts").mkdir(parents=True, exist_ok=True)
    inter = fetch_inter()
    print("Schriften:")
    for name, file, size in TEXT_FONTS:
        lv_font_conv(name, inter / file, size, TEXT_RANGES)
    ranges = ",".join(hex(cp) for cp in sorted(set(icons.values())))
    ttf = pkg / "fonts" / "materialdesignicons-webfont.ttf"
    for name, size in ICON_FONTS:
        lv_font_conv(name, ttf, size, ranges)


def gen_icon_table(icons: dict[str, int]) -> None:
    lines = [
        "/* generiert von tools/gen_assets.py – nicht von Hand ändern */",
        '#include "deckbar/icons.h"',
        "",
        "const deckbar_icon_t deckbar_icons[] = {",
    ]
    for name in sorted(icons):
        utf8 = chr(icons[name]).encode("utf-8")
        esc = "".join(f"\\x{b:02X}" for b in utf8)
        lines.append(f'    {{"{name}", "{esc}"}},')
    lines += ["};", f"const unsigned deckbar_icons_count = {len(icons)};", ""]
    (ROOT / "shared-ui" / "src" / "icons_table.c").write_text("\n".join(lines))


def gen_web_icons(pkg: Path, icons: dict[str, int]) -> None:
    web = ROOT / "daemon" / "deckbar_daemon" / "web"
    web.mkdir(parents=True, exist_ok=True)
    (web / "icons.json").write_text(json.dumps({k: icons[k] for k in sorted(icons)}, indent=0))
    shutil.copy(pkg / "fonts" / "materialdesignicons-webfont.woff", web / "mdi.woff")
    # dieselbe Textschrift wie auf dem Gerät, damit die Vorschau passt
    inter_web = fetch_inter().parent.parent / "web"
    for name in ("Inter-Medium.woff2", "Inter-SemiBold.woff2"):
        shutil.copy(inter_web / name, web / name)
    (web / "Inter-LICENSE.txt").write_text("Inter – https://rsms.me/inter – SIL Open Font License 1.1\n")
    (web / "mdi-LICENSE.txt").write_text(
        "Material Design Icons – https://pictogrammers.com – Pictogrammers Free License\n"
        "(Icons: Apache 2.0, Font: SIL OFL 1.1)\n"
    )


def gen_docs(icons: dict[str, int]) -> None:
    rows = "\n".join(f"| `{n}` | U+{icons[n]:X} |" for n in sorted(icons))
    (ROOT / "docs" / "icons.md").write_text(
        "# Verfügbare Icons\n\n"
        "Material Design Icons (https://pictogrammers.com/library/mdi/). Nur diese Namen sind\n"
        "in der Geräte-Schrift enthalten. Weitere trägt man in `tools/icons.txt` ein und führt\n"
        "`uv run --with pillow tools/gen_assets.py` aus.\n\n"
        "| Name | Codepoint |\n|---|---|\n" + rows + "\n"
    )


# ---------------------------------------------------------------- Hintergrund
def default_background():
    from PIL import Image, ImageDraw, ImageFilter

    # Farbflecken auf dunklem Grund, doppelt so groß rendern und stark weichzeichnen
    s = 2
    img = Image.new("RGB", (W * s, H * s), (10, 13, 28))
    d = ImageDraw.Draw(img)
    blobs = [
        # (cx, cy, r, Farbe) in 640x172-Koordinaten. Farben aus dem eigenen Desktop-Hintergrund
        # (grafik-wqhd.png): Blau, Tiefblau, Violett, Lila, Türkis. Ursprünglich:
        # (88,60,220) (20,120,200) (190,60,170) (230,110,60) (40,180,170)
        (60, 30, 150, (40, 105, 235)),
        (250, 170, 140, (15, 70, 200)),
        (430, 0, 130, (125, 70, 235)),
        (600, 150, 160, (95, 45, 205)),
        (330, 60, 70, (20, 165, 175)),
    ]
    for cx, cy, r, c in blobs:
        d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], fill=c)
    img = img.filter(ImageFilter.GaussianBlur(70 * s))
    # abdunkeln, damit weiße Schrift auf Glas sicher lesbar bleibt
    img = Image.blend(img, Image.new("RGB", img.size, (8, 10, 22)), 0.35)
    return img.resize((W, H), Image.LANCZOS)


def load_background(path: Path):
    from PIL import Image, ImageFilter, ImageOps

    img = Image.open(path).convert("RGB")
    img = ImageOps.fit(img, (W, H), Image.LANCZOS)
    img = img.filter(ImageFilter.GaussianBlur(18))
    return Image.blend(img, Image.new("RGB", img.size, (8, 10, 22)), 0.4)


BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def to_rgb565_dithered(img) -> bytes:
    """Geordnetes Dithering gegen Banding in den weichen Verläufen."""
    px = img.load()
    out = bytearray()
    rnd = random.Random(1)
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            t = (BAYER4[y & 3][x & 3] + rnd.random() * 0.5) / 16.0 - 0.5
            r = min(255, max(0, int(r + t * 8)))
            g = min(255, max(0, int(g + t * 4)))
            b = min(255, max(0, int(b + t * 8)))
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out += v.to_bytes(2, "little")
    return bytes(out)


def gen_background(src: Path | None) -> None:
    img = load_background(src) if src else default_background()
    (CACHE).mkdir(parents=True, exist_ok=True)
    img.save(CACHE / "bg_preview.png")
    data = to_rgb565_dithered(img)
    body = ",\n".join(
        "    " + ", ".join(f"0x{b:02X}" for b in data[i : i + 24]) for i in range(0, len(data), 24)
    )
    (ROOT / "shared-ui" / "assets").mkdir(parents=True, exist_ok=True)
    (ROOT / "shared-ui" / "assets" / "bg_default.c").write_text(
        "/* generiert von tools/gen_assets.py – vorgeblurrter Hintergrund 640x172 RGB565 */\n"
        '#include "lvgl.h"\n\n'
        "#ifndef LV_ATTRIBUTE_LARGE_CONST\n#define LV_ATTRIBUTE_LARGE_CONST\n#endif\n\n"
        f"static const LV_ATTRIBUTE_LARGE_CONST uint8_t bg_map[{len(data)}] = {{\n{body}\n}};\n\n"
        "const lv_image_dsc_t deckbar_bg_default = {\n"
        "    .header = {\n"
        "        .magic = LV_IMAGE_HEADER_MAGIC,\n"
        "        .cf = LV_COLOR_FORMAT_RGB565,\n"
        f"        .w = {W},\n        .h = {H},\n        .stride = {W * 2},\n"
        "    },\n"
        f"    .data_size = {len(data)},\n"
        "    .data = bg_map,\n"
        "};\n"
    )
    print("Hintergrund geschrieben (Vorschau: tools/.cache/bg_preview.png)")
    # Web-UI-Vorschau nutzt dasselbe Bild
    img.save(ROOT / "daemon" / "deckbar_daemon" / "web" / "bg.png")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bg", type=Path, help="eigenes Hintergrundbild (wird eingepasst + weichgezeichnet)")
    ap.add_argument("--only", choices=["fonts", "bg", "icons"], help="nur einen Teil erzeugen")
    args = ap.parse_args()

    pkg = fetch_mdi()
    cps = mdi_codepoints(pkg)
    names = read_icon_names()
    missing = [n for n in names if n not in cps]
    if missing:
        print("Unbekannte MDI-Namen:", ", ".join(missing), file=sys.stderr)
        return 1
    icons = {n: cps[n] for n in names}

    if args.only in (None, "icons", "fonts"):
        gen_icon_table(icons)
        gen_web_icons(pkg, icons)
        gen_docs(icons)
    if args.only in (None, "fonts"):
        gen_fonts(pkg, icons)
    if args.only in (None, "bg"):
        gen_background(args.bg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
