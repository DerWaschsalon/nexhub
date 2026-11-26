"""Dungeon-Namen, die A2Tools (src/data/i18n/dungeons/en.json) nicht kennt.

Der Daemon nimmt Namen aus den A2Tools-Daten und schreibt sonst „Dungeon <ID>“. Diese Tabelle
füllt die Lücken, englisch wie dort. Nachtragen, sobald ein Run mit unbekannter ID auftaucht
(Name über die Bosse herausfinden); fällt weg, sobald A2Tools die ID selbst führt.
"""
from __future__ import annotations

EXTRA_DUNGEONS: dict[int, str] = {
    200003: "Nightmare",                          # Albtraum: Gatekeeper Pinopi, Guardian Notun, Mutated Gerod
    600081: "Abyssal Forge: Ludra",               # Isolation Specialist Rahu, Abyssal Wing Ketu, Fusion Reactor
    600082: "Abyssal Forge: Ludra",               # Rahu, Central Abyss Fusion Reactor, Eternal Ludra
    610052: "Deus Research Base",                 # Gelcos, Nazmun, Atiel
    610062: "Shattered Arkanis",                  # Siliator of Deceit, Ruthilis of Pain, Talisra of the Void
    620011: "Corroded Decontamination Facility",  # Surveillance Device, Devouring Klawfly, Black Blood Blatt, Bargott
    910013: "Nightmare Altar",                    # Ascension Trial (Hard): Divided Aponos
    910014: "Nightmare Altar",                    # Ascension Trial (Extreme): Divided Aponos
    910033: "Sanctum of Loathing",                # Ascension Trial: Featherstorm Duduri, Watchful Raptor Dodori
    910034: "Sanctum of Loathing",                # Ascension Trial: Featherstorm Duduri, Watchful Raptor Dodori
}


def dungeon_label(dungeon_id: int, name: str) -> str:
    """Anzeigename: der mitgeschickte Name, außer er ist der Platzhalter „Dungeon <ID>“."""
    if name == f"Dungeon {dungeon_id}":
        return EXTRA_DUNGEONS.get(dungeon_id, name)
    return name
