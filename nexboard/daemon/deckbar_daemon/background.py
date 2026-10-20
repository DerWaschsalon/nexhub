"""Hintergrundbild fürs Gerät: Standard (in der Firmware), KDE-Hintergrundbild oder eigene Datei.

`theme.background` im Layout:
  "default"    eingebautes Bild der Firmware, es wird nichts übertragen
  "wallpaper"  aktuelles Plasma-Hintergrundbild des Hauptbildschirms, folgt Änderungen
  "/pfad.jpg"  beliebige Bilddatei (auch per Upload aus der Web-UI, siehe save_upload)

Das Bild wird auf 640x172 zugeschnitten, weichgezeichnet und leicht abgedunkelt (wie
tools/gen_assets.py --bg), mit Dithering nach RGB565 gewandelt und in `bg`-Nachrichten
übertragen.
"""
from __future__ import annotations

import asyncio
import configparser
import hashlib
import io
import logging
import os
import random
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image, ImageFilter, ImageOps

log = logging.getLogger(__name__)

W, H = 640, 172
PLASMA_RC = "plasma-org.kde.plasma.desktop-appletsrc"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".avif", ".jxl"}
BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _to_path(value: str) -> Path:
    if value.startswith("file://"):
        return Path(unquote(urlparse(value).path))
    return Path(value).expanduser()


def _package_image(pkg: Path) -> Path | None:
    """Plasma-Wallpaper-Paket (Ordner mit contents/images/BxH.ext): größtes Bild nehmen."""
    best, best_px = None, -1
    for f in (pkg / "contents" / "images").glob("*"):
        m = re.match(r"(\d+)x(\d+)", f.stem)
        if f.suffix.lower() in IMAGE_EXT and m and int(m[1]) * int(m[2]) > best_px:
            best, best_px = f, int(m[1]) * int(m[2])
    return best


# kde_wallpaper() läuft alle 5 s: die ~50 KB große appletsrc nur neu parsen, wenn sie sich ändert
_wallpaper_cache: tuple[tuple, Path | None] | None = None


def kde_wallpaper(rc: Path | None = None) -> Path | None:
    """Hintergrundbild des Plasma-Hauptbildschirms (lastScreen=0), sonst das erste gefundene."""
    global _wallpaper_cache
    rc = rc or _config_home() / PLASMA_RC
    try:
        st = rc.stat()
        stamp = (str(rc), st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    if stamp and _wallpaper_cache and _wallpaper_cache[0] == stamp:
        return _wallpaper_cache[1]
    found = _parse_wallpaper(rc)
    if stamp:
        _wallpaper_cache = (stamp, found)
    return found


def _parse_wallpaper(rc: Path) -> Path | None:
    cp = configparser.RawConfigParser(strict=False)
    cp.optionxform = str  # KDE-Schlüssel sind case-sensitiv
    try:
        cp.read(rc, encoding="utf-8")
    except (OSError, configparser.Error) as e:
        log.debug("%s nicht lesbar: %s", rc, e)
        return None
    found: list[tuple[bool, Path]] = []
    for sec in cp.sections():
        m = re.fullmatch(r"Containments\]\[(\d+)\]\[Wallpaper\]\[org\.kde\.image\]\[General", sec)
        if not m or not cp.has_option(sec, "Image"):
            continue
        cont = f"Containments][{m[1]}"
        primary = cp.has_section(cont) and cp.get(cont, "lastScreen", fallback="") == "0"
        path = _to_path(cp.get(sec, "Image"))
        if path.is_dir():
            path = _package_image(path)
        if path and path.is_file():
            found.append((primary, path))
    found.sort(key=lambda x: not x[0])
    return found[0][1] if found else None


def render(path: Path) -> Image.Image:
    img = Image.open(path)
    img.load()
    img = ImageOps.fit(img.convert("RGB"), (W, H), Image.Resampling.LANCZOS)
    img = img.filter(ImageFilter.GaussianBlur(14))
    # abdunkeln, damit weiße Schrift auf den Glaskacheln lesbar bleibt
    return Image.blend(img, Image.new("RGB", img.size, (8, 10, 22)), 0.3)


def to_rgb565_dithered(img: Image.Image) -> bytes:
    """RGB565 little-endian mit geordnetem Dithering gegen Banding in weichen Verläufen."""
    raw = img.tobytes()
    out = bytearray(W * H * 2)
    rnd = random.Random(1)
    i = o = 0
    for y in range(H):
        row = BAYER4[y & 3]
        for x in range(W):
            t = (row[x & 3] + rnd.random() * 0.5) / 16.0 - 0.5
            r = min(255, max(0, int(raw[i] + t * 8)))
            g = min(255, max(0, int(raw[i + 1] + t * 4)))
            b = min(255, max(0, int(raw[i + 2] + t * 8)))
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out[o] = v & 0xFF
            out[o + 1] = v >> 8
            i += 3
            o += 2
    return bytes(out)


class Background:
    def __init__(self) -> None:
        self.mode = "default"
        self.source: Path | None = None
        self.id = ""             # "" = Standardbild der Firmware
        self.data: bytes | None = None
        self.png: bytes | None = None  # Vorschau für die Web-UI
        self._stamp: tuple | None = None
        self._lock = asyncio.Lock()

    def _resolve(self) -> Path | None:
        if self.mode == "wallpaper":
            return kde_wallpaper()
        if self.mode != "default":
            p = _to_path(self.mode)
            return p if p.is_file() else None
        return None

    async def update(self, mode: str | None = None) -> bool:
        """Neu berechnen, wenn sich Modus, Quelldatei oder deren Inhalt geändert haben.
        Liefert True, wenn die Geräte ein neues Bild brauchen."""
        async with self._lock:
            if mode is not None:
                self.mode = mode or "default"
            src = self._resolve()
            try:
                st = src.stat() if src else None
            except OSError:
                src, st = None, None
            stamp = (self.mode, str(src), st.st_mtime_ns if st else 0, st.st_size if st else 0)
            if stamp == self._stamp:
                return False
            self._stamp = stamp
            old = self.id
            if src is None:
                if self.mode != "default":
                    log.warning("Hintergrund '%s': kein Bild gefunden, nutze Standard", self.mode)
                self.source, self.id, self.data, self.png = None, "", None, None
            else:
                try:
                    self.data, self.png = await asyncio.to_thread(self._build, src)
                    self.source = src
                    self.id = hashlib.sha1(repr(stamp).encode()).hexdigest()[:12]
                    log.info("Hintergrund aus %s erzeugt", src)
                except Exception as e:
                    log.warning("Hintergrund aus %s nicht erzeugbar: %s", src, e)
                    self.source, self.id, self.data, self.png = None, "", None, None
            return self.id != old

    @staticmethod
    def _build(src: Path) -> tuple[bytes, bytes]:
        img = render(src)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return to_rgb565_dithered(img), buf.getvalue()


UPLOAD_MAX = 20 * 1024 * 1024


def save_upload(data: bytes, folder: Path) -> Path:
    """Hochgeladenes Bild prüfen, auf höchstens 1920 px verkleinern und als PNG ablegen.

    Der Dateiname ist der Hash des Inhalts, gleiches Bild = gleiche Datei. Wirft ValueError,
    wenn die Daten kein lesbares Bild sind."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:  # Pillow wirft je nach Format verschiedene Fehler
        raise ValueError("keine lesbare Bilddatei") from e
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((1920, 1920))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"upload-{hashlib.sha256(data).hexdigest()[:16]}.png"
    if not path.exists():
        img.save(path, "PNG")
    return path
