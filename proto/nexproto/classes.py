"""AION-2-Klassen: die einzige Klassentabelle im Repo.

Daemon, Hub, Web-UI und Leiste nehmen sie von hier; JavaScript, TypeScript und C bekommen sie über
`python -m nexproto.codegen`. Farben wie im A2Tools-Meter (public/src/js/core.js, jobColorMap), damit
Meter, Leiste, Run-Bild und Hub dieselbe Klasse gleich zeigen.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameClass:
    key: str      # Schlüssel in allen eigenen Formaten (Live-Stream, NexLog, Geräteprotokoll)
    job_id: int   # jobId in den Kampfdateien des Mitschnitts
    name_en: str
    name_de: str
    color: str    # #RRGGBB


CLASSES: tuple[GameClass, ...] = (
    GameClass("gladiator", 11, "Gladiator", "Gladiator", "#4FD1C5"),
    GameClass("templar", 12, "Templar", "Templer", "#5F8CFF"),
    GameClass("assassin", 13, "Assassin", "Assassine", "#7BE35A"),
    GameClass("ranger", 14, "Ranger", "Waldläufer", "#41D98A"),
    GameClass("sorcerer", 15, "Sorcerer", "Magier", "#9A6BFF"),
    GameClass("spiritmaster", 16, "Spiritmaster", "Beschwörer", "#E06BFF"),
    GameClass("cleric", 17, "Cleric", "Kleriker", "#F2C15A"),
    GameClass("chanter", 18, "Chanter", "Kantor", "#FF9A3D"),
    GameClass("brawler", 19, "Brawler", "Faustkämpfer", "#E85D5D"),
)
UNKNOWN_COLOR = "#8E8E93"  # Klasse noch nicht bekannt
CLASS_KEYS: tuple[str, ...] = tuple(c.key for c in CLASSES)
BY_KEY: dict[str, GameClass] = {c.key: c for c in CLASSES}
# jobId der Kampfdateien → Klassen-Schlüssel
JOB_CLASSES: dict[int, str] = {c.job_id: c.key for c in CLASSES}
