"""Befehle vom NexBoard-Daemon: eine Textzeile pro Befehl auf stdin, z.B. "ton_testen".

Gelesen wird in einem eigenen Thread, ausgefuehrt im Qt-Thread (Fenster duerfen nur dort
angefasst werden). Unbekannte Befehle werden ignoriert. Endet stdin (Daemon abgestuerzt), kommt
"beenden", damit kein Radar mit tcpdump ohne Daemon weiterlaeuft.
"""
from __future__ import annotations

import sys
import threading
from typing import Callable

from PySide6.QtCore import QObject, Signal


def ausfuehren(zeile: str, aktionen: dict[str, Callable[[], None]]) -> None:
    aktion = aktionen.get(zeile.strip())
    if aktion:
        aktion()


class _Bote(QObject):
    zeile = Signal(str)


def starten(aktionen: dict[str, Callable[[], None]]) -> QObject:
    """Liest stdin bis zum Ende. Den Rueckgabewert festhalten, sonst raeumt Python ihn weg."""
    bote = _Bote()
    bote.zeile.connect(lambda z: ausfuehren(z, aktionen))

    def lesen() -> None:
        for zeile in sys.stdin:
            bote.zeile.emit(zeile)
        bote.zeile.emit("beenden")

    threading.Thread(target=lesen, daemon=True).start()
    return bote
