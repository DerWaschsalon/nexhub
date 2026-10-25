"""Erzeugt radar/bosse.json (Boss-NPC-ID -> Dungeon), radar/zonen.json (Zonen-ID -> Dungeon)
und radar/vertraute.json (Vertrauten-ID -> Name deutsch/englisch, Art, Fundorte, Monster mit der Seele).

Die Dungeon-Namen sind dieselben wie in DUNGEONS in radar/warnung.py.

Quelle sind die Daten des A2Tools-DPS-Meters. Nach einem Update des Meters neu ausfuehren.
Aufruf: python -m werkzeuge.bosse
"""
import json
import urllib.request
from pathlib import Path

DATEN = Path("/usr/lib/A2Tools DPS Meter/data/i18n")
UMBENENNEN = {"Fire Temple": "Feuertempel", "the Hall of Illusion": "Hall of Illusion"}
# Katalog der 207 Vertrauten aus dem Projekt aion2pettracker (GPL-3.0, Daten von questlog.gg, Namen (c) NCSOFT):
# englischer Name, Kategorie, Fundgebiete und die Monster, die die Seele fallen lassen
VERTRAUTE = ("https://raw.githubusercontent.com/keytftw/aion2pettracker/main/data/pet-catalog.json")
ARTEN = {"Special": "Spezial"}  # Cogni, Fera, Natura, Varian heissen im Spiel genauso


def main() -> None:
    dungeons = json.loads((DATEN / "dungeons/en.json").read_text())
    npcs = json.loads((DATEN / "npcs/en.json").read_text())
    bosse = {}
    for npc, v in npcs.items():
        dungeon = dungeons.get(str(v.get("dungeonId")))
        if v.get("isBoss") and dungeon:
            bosse[npc] = UMBENENNEN.get(dungeon["name"], dungeon["name"])
    zonen = {k: UMBENENNEN.get(v["name"], v["name"]) for k, v in dungeons.items()}
    # Deutsch nur, wenn ein NPC genau so heisst (z.B. Baby Odyle Spider -> Odspinnling)
    deutsch = json.loads((DATEN / "npcs/de.json").read_text())
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
