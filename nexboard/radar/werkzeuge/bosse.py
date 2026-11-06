"""Erzeugt radar/bosse.json (Boss-NPC-ID -> Dungeon), radar/zonen.json (Zonen-ID -> Dungeon)
und radar/vertraute.json (Vertrauten-ID -> Name deutsch/englisch, Art, Fundorte, Monster mit der Seele).

Die Dungeon-Namen sind dieselben wie in DUNGEONS in radar/warnung.py.

Quelle sind die Daten des A2Tools-DPS-Meters. Nach einem Update des Meters neu ausfuehren.
Dungeons, die A2Tools nur als Nummer kennt (Ludra, Kelch von Muspel ...), bekommen ihren Namen ueber
ihre Bosse aus radar/ansagen.json (werkzeuge.ansagen).
Aufruf: python -m werkzeuge.bosse [Ordner data/i18n, Standard: der installierte Meter]
"""
import json
import sys
import urllib.request
from pathlib import Path

from .ansagen import OHNE_DUNGEON

DATEN = Path("/usr/lib/A2Tools DPS Meter/data/i18n")
UMBENENNEN = {"Fire Temple": "Feuertempel", "the Hall of Illusion": "Hall of Illusion"}
# Katalog der 207 Vertrauten aus dem Projekt aion2pettracker (GPL-3.0, Daten von questlog.gg, Namen (c) NCSOFT):
# englischer Name, Kategorie, Fundgebiete und die Monster, die die Seele fallen lassen
VERTRAUTE = ("https://raw.githubusercontent.com/keytftw/aion2pettracker/main/data/pet-catalog.json")
ARTEN = {"Special": "Spezial"}  # Cogni, Fera, Natura, Varian heissen im Spiel genauso


def dungeons_ueber_bosse(npcs: dict, bekannt: dict) -> dict[str, str]:
    """Dungeon-ID -> Name fuer IDs, die A2Tools nicht benennt, ueber ihre Bosse in den Boss-Ansagen
    (ansagen.json). Mindestens die Haelfte der Bosse muss dort stehen, alle beim selben Dungeon: Der
    Albtraum hat zwar auch eine Kromede, ist aber nicht der Feuertempel."""
    ansagen = json.loads((Path(__file__).parent.parent / "radar" / "ansagen.json").read_text())
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
    dungeons = json.loads((daten / "dungeons/en.json").read_text())
    npcs = json.loads((daten / "npcs/en.json").read_text())
    zonen = {k: UMBENENNEN.get(v["name"], v["name"]) for k, v in dungeons.items()}
    zonen.update(dungeons_ueber_bosse(npcs, zonen))
    bosse = {npc: zonen[str(v["dungeonId"])] for npc, v in npcs.items()
             if v.get("isBoss") and str(v.get("dungeonId")) in zonen}
    # Deutsch nur, wenn ein NPC genau so heisst (z.B. Baby Odyle Spider -> Odspinnling)
    deutsch = json.loads((daten / "npcs/de.json").read_text())
    npc_id = {v["name"].lower(): k for k, v in reversed(npcs.items())}
    vertraute = {}
    for v in json.loads(urllib.request.urlopen(VERTRAUTE).read()):
        de = deutsch.get(npc_id.get(v["Name"].lower(), ""), {}).get("name") or v["Name"]
        vertraute[str(v["Id"])] = {"de": de, "en": v["Name"], "art": ARTEN.get(v["Genus"], v["Genus"]),
                                   "orte": [f"{o['Region']}: {o['Area']}" for o in v["Places"]],
                                   "monster": [m["NpcCode"] for m in v["Droppers"]]}
    ordner = Path(__file__).parent.parent / "radar"
    for datei, daten in (("bosse.json", bosse), ("zonen.json", zonen), ("vertraute.json", vertraute)):
        (ordner / datei).write_text(json.dumps(daten, indent=0, sort_keys=True, ensure_ascii=False))
    print(f"{len(bosse)} Bosse, {len(zonen)} Dungeon-Zonen, {len(vertraute)} Vertraute -> {ordner}")


if __name__ == "__main__":
    main()
