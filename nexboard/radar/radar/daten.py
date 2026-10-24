"""Spieldaten (Namen) und gespeicherte Zustaende, ohne Qt."""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

A2TOOLS = Path("/usr/lib/A2Tools DPS Meter/data/i18n")  # Skill- und NPC-Namen des DPS-Meters
SPEICHER = Path.home() / ".local" / "share" / "aion2-radar"

# Namen und Art der Vertrauten (aus aion2assistant, Namen (c) NCSOFT), erzeugt mit `python -m werkzeuge.bosse`
VERTRAUTE: dict[str, dict] = json.loads((Path(__file__).parent / "vertraute.json").read_text())


@cache
def a2_namen(art: str, sprache: str) -> dict:
    """Namen aus den A2Tools-Daten (art = skills oder npcs). Leer, wenn A2Tools fehlt."""
    try:
        return json.loads((A2TOOLS / art / f"{sprache}.json").read_text())
    except (OSError, ValueError):
        return {}


def npc_name(npc: int, sprache: str) -> str | None:
    return a2_namen("npcs", sprache).get(str(npc), {}).get("name")


@cache
def feldboss_npcs() -> set[int]:
    """Bosse ausserhalb von Dungeons, darunter die Feldbosse."""
    return {int(k) for k, v in a2_namen("npcs", "en").items() if v.get("isBoss") and not v.get("dungeonId")}


def laden(name: str) -> dict:
    try:
        return json.loads((SPEICHER / name).read_text())
    except (OSError, ValueError):
        return {}


def speichern(name: str, daten: dict) -> None:
    try:
        SPEICHER.mkdir(parents=True, exist_ok=True)
        (SPEICHER / name).write_text(json.dumps(daten, ensure_ascii=False))
    except OSError:
        pass
