"""Erzeugt bosses.json (Boss-NPC-ID -> Dungeon) und zones.json (Zonen-ID -> Dungeon) im Ordner
daemon/deckbar_daemon/aion2/data.

Die Dungeon-Namen sind dieselben wie unter „dungeons“ in mechanics.json.

Quelle sind die Daten des A2Tools-DPS-Meters. Nach einem Update des Meters neu ausfuehren.
Dungeons, die A2Tools nur als Nummer kennt (Ludra, Kelch von Muspel ...), bekommen ihren Namen ueber
ihre Bosse aus callouts.json (werkzeuge.ansagen).
Aufruf: python -m werkzeuge.bosse [Ordner data/i18n, Standard: der installierte Meter]
"""
import json
import sys
from pathlib import Path

from deckbar_daemon.aion2.gamedata import DATA

from .ansagen import OHNE_DUNGEON

DATEN = Path("/usr/lib/A2Tools DPS Meter/data/i18n")
UMBENENNEN = {"Fire Temple": "Feuertempel", "the Hall of Illusion": "Hall of Illusion"}
NACHTRAG = {"200003": {"name": "Albtraum"}}  # fehlt in den A2Tools-Dungeons (Zikel, Sura, Hohepriesterin, ...)


def dungeons_ueber_bosse(npcs: dict, bekannt: dict) -> dict[str, str]:
    """Dungeon-ID -> Name fuer IDs, die A2Tools nicht benennt, ueber ihre Bosse in den Boss-Ansagen
    (callouts.json). Mindestens die Haelfte der Bosse muss dort stehen, alle beim selben Dungeon: Der
    Albtraum hat zwar auch eine Kromede, ist aber nicht der Feuertempel."""
    ansagen = json.loads((DATA / "callouts.json").read_text())
    dungeon_von = {b["name"]["en"]: b["dungeon"] for b in ansagen["bosse"].values()
                   if b["dungeon"] != OHNE_DUNGEON}
    bosse_von: dict[str, set[str]] = {}
    for v in npcs.values():
        dungeon_id = str(v.get("dungeonId") or "")
        if dungeon_id and dungeon_id not in bekannt and v.get("isBoss") and v.get("name"):
            bosse_von.setdefault(dungeon_id, set()).add(v["name"])
    gefunden = {}
    for dungeon_id, namen in bosse_von.items():
        treffer = {dungeon_von[n] for n in namen if n in dungeon_von}
        anzahl = sum(n in dungeon_von for n in namen)
        if len(treffer) == 1 and anzahl * 2 >= len(namen):
            gefunden[dungeon_id] = treffer.pop()
    return gefunden


def main() -> None:
    daten = Path(sys.argv[1]) if len(sys.argv) > 1 else DATEN
    dungeons = json.loads((daten / "dungeons/en.json").read_text()) | NACHTRAG
    npcs = json.loads((daten / "npcs/en.json").read_text())
    zonen = {k: UMBENENNEN.get(v["name"], v["name"]) for k, v in dungeons.items()}
    zonen.update(dungeons_ueber_bosse(npcs, zonen))
    bosse = {npc: zonen[str(v["dungeonId"])] for npc, v in npcs.items()
             if v.get("isBoss") and str(v.get("dungeonId")) in zonen}
    for datei, inhalt in (("bosses.json", bosse), ("zones.json", zonen)):
        (DATA / datei).write_text(json.dumps(inhalt, indent=0, sort_keys=True, ensure_ascii=False))
    print(f"{len(bosse)} Bosse, {len(zonen)} Dungeon-Zonen -> {DATA}")


if __name__ == "__main__":
    main()
