"""USB-Brücke: DeckBar per USB-Kabel statt WLAN.

Die Firmware spricht über USB dasselbe JSON-Protokoll wie über WebSocket, nur zeilenweise mit
Präfix „@@“ (alles andere auf der Schnittstelle sind Log-Ausgaben und wird ignoriert):

  Gerät -> PC   @@DECKBAR       Kennung, alle 2 s, solange keine USB-Verbindung besteht
                @@{...}         Protokollnachricht (hello, event, pong …)
  PC -> Gerät   @@OPEN          Daemon erreichbar, Gerät schickt jetzt hello
                @@CLOSE         Verbindung zum Daemon weg
                @@KEEP          Lebenszeichen alle 5 s (ohne fällt das Gerät nach 15 s auf WLAN zurück)
                @@{...}         Protokollnachricht vom Daemon

Die Brücke verbindet sich für jedes gefundene Gerät als normaler WebSocket-Client mit dem
eigenen /ws, der Daemon sieht also ein ganz gewöhnliches Gerät von 127.0.0.1.

Sicherheit für fremde ESP32 am selben PC (z. B. WLED): Kandidaten werden nur passiv geöffnet
(DTR/RTS bleiben unverändert, kein Reset) und es wird nichts geschrieben, bevor dort „@@DECKBAR“
kam. Ein Port ohne Kennung wird nach PROBE_S geschlossen und bis zum Abstecken nicht mehr geöffnet.
"""
from __future__ import annotations

import asyncio
import glob
import logging
import threading
import time
from pathlib import Path

from aiohttp import ClientSession, WSMsgType

log = logging.getLogger(__name__)

PREFIX = b"@@"
BEACON = b"DECKBAR"
PROBE_S = 8          # so lange auf die Kennung warten
SCAN_S = 3           # neue Ports suchen
KEEP_S = 5           # Lebenszeichen ans Gerät
MAX_LINE = 64 * 1024
CANDIDATES = ("/dev/serial/by-id/*Espressif*", "/dev/serial/by-id/*DeckBar*")


def parse_line(raw: bytes) -> bytes | None:
    """Nutzlast einer Protokollzeile (ohne „@@“), None für Log-Zeilen.

    Läuft eine Log-Ausgabe ohne Zeilenende in die Zeile hinein, zählt das letzte „@@“."""
    i = raw.rfind(PREFIX)
    if i < 0:
        return None
    return raw[i + len(PREFIX):].strip(b"\r\n")


class _Port:
    """Serielle Schnittstelle mit Lesethread; Zeilen landen in einer asyncio-Queue."""

    def __init__(self, path: str, loop: asyncio.AbstractEventLoop) -> None:
        import serial  # pyserial erst hier: ohne USB-Nutzung keine Pflicht

        self.path = path
        self.lines: asyncio.Queue[bytes | None] = asyncio.Queue()
        # Standardwerte für DTR/RTS lassen: beide gesetzt = kein Reset beim USB-JTAG der ESP32-S3
        self.ser = serial.Serial(path, 115200, timeout=0.5)
        self._loop = loop
        self._lock = threading.Lock()
        self._closed = False
        threading.Thread(target=self._reader, name=f"usb-{Path(path).name[-20:]}", daemon=True).start()

    def _reader(self) -> None:
        buf = bytearray()
        try:
            while not self._closed:
                chunk = self.ser.read(self.ser.in_waiting or 1)
                if not chunk:
                    continue
                buf += chunk
                while (n := buf.find(b"\n")) >= 0:
                    line = bytes(buf[:n])
                    del buf[: n + 1]
                    self._loop.call_soon_threadsafe(self.lines.put_nowait, line)
                if len(buf) > MAX_LINE:
                    buf.clear()
        except Exception as e:  # Abstecken: SerialException/OSError
            if not self._closed:
                log.info("USB %s: %s", self.path, e)
        self._loop.call_soon_threadsafe(self.lines.put_nowait, None)

    def write(self, payload: bytes) -> None:
        with self._lock:
            self.ser.write(PREFIX + payload + b"\n")

    def close(self) -> None:
        self._closed = True
        try:
            self.ser.close()
        except Exception:
            pass


class UsbBridge:
    def __init__(self, mode: str, ws_url: str) -> None:
        self.mode = mode          # "auto", "off" oder fester Pfad
        self.ws_url = ws_url
        self.busy: set[str] = set()      # gerade geprüft oder verbunden
        self.rejected: set[str] = set()  # ohne Kennung, bis zum Abstecken ignorieren

    def _candidates(self) -> list[str]:
        if self.mode == "auto":
            found: set[str] = set()
            for pat in CANDIDATES:
                found.update(glob.glob(pat))
            return sorted(found)
        return [self.mode] if Path(self.mode).exists() else []

    async def watch(self) -> None:
        if self.mode == "off":
            return
        try:
            import serial  # noqa: F401
        except ImportError:
            log.warning("USB: pyserial fehlt, nur WLAN möglich")
            return
        while True:
            present = set(self._candidates())
            self.rejected &= present  # abgesteckt = beim nächsten Einstecken neu prüfen
            for path in present - self.busy - self.rejected:
                self.busy.add(path)
                asyncio.ensure_future(self._handle(path))
            await asyncio.sleep(SCAN_S)

    async def _handle(self, path: str) -> None:
        loop = asyncio.get_running_loop()
        try:
            port = await asyncio.to_thread(_Port, path, loop)
        except Exception as e:
            log.debug("USB %s nicht zu öffnen: %s", path, e)
            self.rejected.add(path)
            self.busy.discard(path)
            return
        try:
            if not await self._probe(port):
                log.debug("USB %s: keine DeckBar", path)
                self.rejected.add(path)
                return
            log.info("USB: DeckBar an %s", path)
            await self._link(port)
        finally:
            port.close()
            self.busy.discard(path)

    @staticmethod
    async def _probe(port: _Port) -> bool:
        end = time.monotonic() + PROBE_S
        while (left := end - time.monotonic()) > 0:
            try:
                line = await asyncio.wait_for(port.lines.get(), left)
            except TimeoutError:
                return False
            if line is None:
                return False
            if parse_line(line) == BEACON:
                return True
        return False

    async def _link(self, port: _Port) -> None:
        """Gerät <-> /ws, bis das Kabel gezogen wird. Daemon weg = neu verbinden."""
        while True:
            try:
                async with ClientSession() as http, http.ws_connect(self.ws_url, heartbeat=None, max_msg_size=0) as ws:
                    await asyncio.to_thread(port.write, b"OPEN")
                    unplugged = await self._pump(port, ws)
                    if unplugged:
                        return
            except OSError as e:
                log.debug("USB: Daemon nicht erreichbar (%s)", e)
            try:
                await asyncio.to_thread(port.write, b"CLOSE")
            except Exception:
                return
            # bis zum nächsten Versuch auf Abstecken achten
            try:
                line = await asyncio.wait_for(port.lines.get(), 2)
                if line is None:
                    return
            except TimeoutError:
                pass

    @staticmethod
    async def _pump(port: _Port, ws) -> bool:
        """Leitet weiter, bis eine Seite zumacht. True = Gerät abgesteckt."""

        async def dev_to_ws() -> bool:
            while True:
                line = await port.lines.get()
                if line is None:
                    return True
                p = parse_line(line)
                if p is None:
                    continue
                if p == BEACON:  # Gerät neu gestartet: Sitzung neu aufbauen
                    return False
                if p.startswith(b"{"):
                    await ws.send_str(p.decode("utf-8", "replace"))

        async def ws_to_dev() -> bool:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await asyncio.to_thread(port.write, msg.data.encode())
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
            return False

        async def keep() -> bool:
            while True:
                await asyncio.sleep(KEEP_S)
                await asyncio.to_thread(port.write, b"KEEP")

        tasks = [asyncio.ensure_future(c) for c in (dev_to_ws(), ws_to_dev(), keep())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            t = done.pop()
            return bool(t.result()) if not t.exception() else isinstance(t.exception(), OSError)
        finally:
            for t in tasks:
                t.cancel()
            await ws.close()
