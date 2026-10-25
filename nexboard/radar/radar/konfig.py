"""Einstellungen (~/.config/aion2-radar.json) und der Ton bei neuem Cube."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import wave
from pathlib import Path

KONFIG = Path.home() / ".config" / "aion2-radar.json"
TON = Path.home() / ".cache" / "aion2-radar" / "ping.wav"

# Standardwerte stehen in standard.json, damit der NexBoard-Daemon dieselben nutzt
STANDARD = json.loads((Path(__file__).parent / "standard.json").read_text())

_konfig: dict | None = None


def konfig_laden() -> dict:
    """Gemeinsames Einstellungs-dict fuer alle Teile (nur einmal gelesen)."""
    global _konfig
    if _konfig is None:
        try:
            _konfig = {**STANDARD, **json.loads(KONFIG.read_text())}
        except (OSError, ValueError):
            _konfig = dict(STANDARD)
    return _konfig


def konfig_neu_laden() -> dict:
    """Datei neu lesen (nach einer Aenderung auf der NexBoard-Seite). Aendert dasselbe dict, das
    alle Teile halten."""
    k = konfig_laden()
    try:
        neu = json.loads(KONFIG.read_text())
    except (OSError, ValueError):
        return k
    k.clear()
    k.update({**STANDARD, **neu})
    return k


def konfig_speichern(k: dict) -> None:
    try:
        KONFIG.parent.mkdir(parents=True, exist_ok=True)
        tmp = KONFIG.with_suffix(".tmp")  # erst ganz schreiben, dann ersetzen: nie eine halbe Datei
        tmp.write_text(json.dumps(k, indent=2))
        os.replace(tmp, KONFIG)
    except OSError:
        pass


def abspielen(datei: Path) -> None:
    spieler = shutil.which("pw-play") or shutil.which("paplay")
    if spieler:
        subprocess.Popen([spieler, str(datei)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ton_erzeugen() -> Path:
    if not TON.exists():
        TON.parent.mkdir(parents=True, exist_ok=True)
        rate, daten = 44100, bytearray()
        for i in range(int(rate * 0.22)):
            t = i / rate
            huelle = math.exp(-t * 14)
            wert = int(0.5 * 32767 * huelle * math.sin(2 * math.pi * 1250 * t))
            daten += wert.to_bytes(2, "little", signed=True)
        with wave.open(str(TON), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(daten))
    return TON


def ton_abspielen() -> None:
    abspielen(ton_erzeugen())
