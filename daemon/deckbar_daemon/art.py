"""Cover-Bilder: lädt `mpris:artUrl`, schneidet quadratisch zu und liefert RGB565 in Wunschgröße.

Das Gerät nennt per `art_request` die Kantenlänge in Pixeln. Der Daemon skaliert genau darauf,
damit das Gerät nichts umrechnen muss, und schickt das Bild in `art`-Nachrichten zu je ein paar
Zeilen (die WebSocket-Bibliothek der Firmware nimmt höchstens 15 KB pro Nachricht an).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import struct
from collections import OrderedDict
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiohttp
from PIL import Image, ImageOps

log = logging.getLogger(__name__)

MAX_SIZE = 160          # größte Kantenlänge, die ein Gerät anfordern darf
MAX_DOWNLOAD = 8 << 20  # Cover größer als 8 MB ignorieren
CHUNK_BYTES = 2000      # Rohdaten pro Nachricht (base64 ≈ 2,7 KB, unter dem TCP-Fenster des ESP32)


def art_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def to_rgb565(img: Image.Image, size: int) -> bytes:
    """Quadratisch mittig zuschneiden, skalieren, als RGB565 little-endian (LVGL-Format)."""
    img = ImageOps.fit(img.convert("RGB"), (size, size), Image.Resampling.LANCZOS)
    raw = img.tobytes()
    out = bytearray(size * size * 2)
    o = 0
    for i in range(0, len(raw), 3):
        v = ((raw[i] >> 3) << 11) | ((raw[i + 1] >> 2) << 5) | (raw[i + 2] >> 3)
        out[o] = v & 0xFF
        out[o + 1] = v >> 8
        o += 2
    return bytes(out)


def chunks(aid: str, w: int, h: int, data: bytes) -> list[dict]:
    """Zerlegt ein RGB565-Bild in `art`-/`bg`-Nachrichten (Felder ohne v/type)."""
    row_bytes = w * 2
    rows = max(1, CHUNK_BYTES // row_bytes)
    msgs = []
    for y in range(0, h, rows):
        n = min(rows, h - y)
        part = data[y * row_bytes:(y + n) * row_bytes]
        msgs.append({"id": aid, "w": w, "h": h, "y": y, "rows": n,
                     "data": base64.b64encode(part).decode()})
    return msgs


BIN_CHUNK_BYTES = 12000  # Rohdaten pro Binärframe (WebSockets-Lib der Firmware: max. 15 KB/Nachricht)


def bin_chunks(kind: bytes, aid: str, w: int, h: int, data: bytes) -> list[bytes]:
    """Zerlegt ein RGB565-Bild in Binärframes für Geräte mit `caps: ["bin"]` (kind b"a" Cover,
    b"b" Hintergrund): "DB", Art, id (16 Byte), w, h, y, rows (uint16 LE), dann die Zeilen.
    Gegenüber JSON + base64 ein Drittel weniger Daten und ~9× weniger Nachrichten."""
    row_bytes = w * 2
    rows = max(1, BIN_CHUNK_BYTES // row_bytes)
    idb = aid.encode()[:16].ljust(16, b"\0")
    return [struct.pack("<2sc16sHHHH", b"DB", kind, idb, w, h, y, min(rows, h - y))
            + data[y * row_bytes:(y + min(rows, h - y)) * row_bytes]
            for y in range(0, h, rows)]


CACHE_ENTRIES = 20  # zuletzt gezeigte Cover (verkleinert, je ~0,3 MB): Titelwechsel ohne neuen Download


class Art:
    def __init__(self) -> None:
        self.url: str | None = None
        self._image: Image.Image | None = None
        self._cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._scaled: dict[int, bytes] = {}
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    @property
    def id(self) -> str:
        return art_id(self.url) if self.url and self._image else ""

    async def set_url(self, url: str | None) -> bool:
        """Lädt ein neues Cover. Liefert True, wenn sich das angezeigte Bild geändert hat."""
        url = url or None
        async with self._lock:
            if url == self.url:
                return False
            had = self._image is not None
            self.url, self._image, self._scaled = url, None, {}
            if url in self._cache:
                self._cache.move_to_end(url)
                self._image = self._cache[url]
            elif url:
                try:
                    raw = await self._fetch(url)
                    self._image = await asyncio.to_thread(self._decode, raw)
                except Exception as e:  # Netz, Datei, kaputtes Bild: einfach ohne Cover
                    log.info("Cover nicht ladbar (%s): %s", url, e)
                else:
                    self._cache[url] = self._image
                    while len(self._cache) > CACHE_ENTRIES:
                        self._cache.popitem(last=False)
            return had or self._image is not None

    async def render(self, size: int) -> tuple[str, bytes] | None:
        """(id, RGB565) in Kantenlänge `size`, oder None ohne Cover."""
        size = max(8, min(size, MAX_SIZE))
        async with self._lock:
            if self._image is None or not self.url:
                return None
            data = self._scaled.get(size)
            if data is None:
                data = await asyncio.to_thread(to_rgb565, self._image, size)
                self._scaled[size] = data
            return art_id(self.url), data

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    @staticmethod
    def _decode(raw: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(raw))
        img.load()
        # to_rgb565 schneidet quadratisch auf höchstens MAX_SIZE zu: kurze Seite 2 × MAX_SIZE reicht
        # dafür und hält den Cache klein (statt z. B. 1200 × 1200 von Spotify)
        f = 2 * MAX_SIZE / min(img.size)
        if f < 1:
            img = img.convert("RGB").resize((round(img.width * f), round(img.height * f)), Image.Resampling.LANCZOS)
        return img

    async def _fetch(self, url: str) -> bytes:
        u = urlparse(url)
        if u.scheme == "file":
            path = Path(unquote(u.path))
            if path.stat().st_size > MAX_DOWNLOAD:
                raise ValueError("Datei zu groß")
            return await asyncio.to_thread(path.read_bytes)
        if u.scheme not in ("http", "https"):
            raise ValueError(f"Schema {u.scheme!r} nicht unterstützt")
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            raw = await resp.content.read(MAX_DOWNLOAD + 1)
            if len(raw) > MAX_DOWNLOAD:
                raise ValueError("Download zu groß")
            return raw
