"""Desktop-Benachrichtigung über notify-send (KDE, GNOME …), auf demselben Weg wie update.sh --notify."""
from __future__ import annotations

import asyncio
import logging
import shutil

log = logging.getLogger(__name__)

APP = "NexBoard"
ICON = "system-software-update"
OPEN = "open"  # Kennung des Knopfs, notify-send gibt sie beim Klick aus


async def notify(title: str, body: str, button: str, url: str) -> None:
    """Benachrichtigung mit einem Knopf, der `url` im Browser öffnet.

    notify-send wartet wegen des Knopfs, bis die Benachrichtigung geschlossen oder geklickt wird.
    Deshalb als eigene Aufgabe starten; wird sie abgebrochen, verschwindet auch der Prozess.
    """
    if not shutil.which("notify-send"):
        log.debug("notify-send fehlt, keine Desktop-Benachrichtigung")
        return
    proc = await asyncio.create_subprocess_exec(
        "notify-send", "-a", APP, "-i", ICON, "-A", f"{OPEN}={button}", title, body,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await proc.communicate()
    except asyncio.CancelledError:
        proc.kill()
        raise
    if out.decode(errors="replace").strip() == OPEN:
        await _open(url)


async def _open(url: str) -> None:
    """Losgelöst starten, damit der Browser den Daemon überlebt."""
    try:
        await asyncio.create_subprocess_exec("xdg-open", url, start_new_session=True,
                                             stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    except FileNotFoundError:
        log.warning("xdg-open fehlt, %s nicht geöffnet", url)
