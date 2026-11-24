"""Spieldaten: Bosse und Zonen je Dungeon, Namen aus den A2Tools-Daten und der eigene gespeicherte Stand.

`bosses.json` und `zones.json` erzeugt `python -m werkzeuge.bosse` aus den Daten des A2Tools-Meters. Bosse,
die A2Tools nicht als Boss führt, kommen aus den Mechaniken dazu.
"""
from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data"
A2TOOLS_REPO = Path(__file__).resolve().parents[3] / "capture" / "a2tools" / "src" / "data"  # das Submodul
A2TOOLS_INSTALLED = Path("/usr/lib/A2Tools DPS Meter/data")
STORE = Path.home() / ".local" / "share" / "aion2-radar"  # Feldboss-Timer, Spawnpunkte, Karten


def load_data(name: str) -> Any:
    return json.loads((DATA / name).read_text())


MECHANICS: dict = load_data("mechanics.json")  # alle Regeln der Boss-Warnungen, Aufbau dort unter _felder
CALLOUTS: dict = load_data("callouts.json")  # Boss-Ansagen aus dem Plugin Boss Callouts (werkzeuge.ansagen)
ZONES: dict[int, str] = {int(k): v for k, v in load_data("zones.json").items()}  # Zonen-ID → Dungeon
BOSSES: dict[int, str] = {int(k): v for k, v in load_data("bosses.json").items()}  # Boss-NPC → Dungeon
for _mechanic in MECHANICS["mechaniken"]:
    for _npc in _mechanic["bosse"]:
        BOSSES.setdefault(_npc, _mechanic["dungeon"])


def a2tools_data_dir() -> Path:
    """Daten des A2Tools-Meters (Namen, Dungeons): das Submodul im Repo, aus dem auch der Mitschnitt gebaut
    ist; fehlt es, das installierte Meter."""
    if env := os.environ.get("DECKBAR_A2TOOLS_DATA"):
        return Path(env)
    return A2TOOLS_REPO if A2TOOLS_REPO.is_dir() or not A2TOOLS_INSTALLED.is_dir() else A2TOOLS_INSTALLED


@cache
def a2_i18n(name: str) -> dict:
    """Eine Übersetzungsdatei der A2Tools-Daten, etwa „skills/de.json“. Leer, wenn A2Tools fehlt."""
    try:
        data = json.loads((a2tools_data_dir() / "i18n" / name).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def a2_names(kind: str, language: str) -> dict:
    """Namen aus den A2Tools-Daten (kind = skills oder npcs)."""
    return a2_i18n(f"{kind}/{language}.json")


def npc_name(npc: int, language: str) -> str | None:
    return a2_names("npcs", language).get(str(npc), {}).get("name")


def skill_name(skill: int, language: str) -> str:
    return a2_names("skills", language).get(str(skill), str(skill))


@cache
def field_boss_npcs() -> set[int]:
    """Bosse außerhalb von Dungeons, darunter die Feldbosse."""
    return {int(k) for k, v in a2_names("npcs", "en").items() if v.get("isBoss") and not v.get("dungeonId")}


def load_state(name: str) -> dict:
    try:
        return json.loads((STORE / name).read_text())
    except (OSError, ValueError):
        return {}


def save_state(name: str, data: dict) -> None:
    try:
        STORE.mkdir(parents=True, exist_ok=True)
        (STORE / name).write_text(json.dumps(data, ensure_ascii=False))
    except OSError:
        pass
