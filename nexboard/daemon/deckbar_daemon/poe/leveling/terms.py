"""Schlüsselwörter der Guide-Sprache von Exile-UI (data/english/UI.txt im Original), an einer Stelle.

Eine Guide-Seite ist eine Liste von Zeilen wie „enter areaid1_1_2 ;; the coast“ oder
„(img:quest) tarkleigh: <enemy_at_the_gate>“. Daran erkennen Seitenbau, Tracker und Anzeige,
was eine Zeile bedeutet.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

AREA = "areaid"  # „areaid1_1_2“: Zone; die letzte auf einer Seite ist ihr Ziel
HINT = "(hint)_"  # Unterpunkt der Zeile davor
OPTIONAL = "optional:"
LEAGUE_START = "leaguestart:"  # nur beim Ligastart
TWINK = "twinkrun:"  # nur bei einem Durchlauf mit Ausrüstung (kein Ligastart)
QUEST_CHECK = "quest-check"  # Seite nur, wenn es dort für den Build etwas gibt
COMMENT = " ;"  # dahinter steht nur ein Kommentar (z. B. der Zonenname)
KILL = "kill"
GEM_REWARD = "take:"
BUY_GEM = "buy gem:"
BUY_ITEM = "buy item:"
LEVEL_HINTS = ("recommended level:", "farm level:")
END_MARKERS = ("an_end_to_hunger", "act-tracker")  # Schnellvorlauf hört hier auf (letzte Seite)
QUEST = re.compile(r"<([^>]*)>")

BANDITS = ("none", "alira", "kraityn", "oak")
STAT_COLORS = ("D81C1C", "00BF40", "0077FF")  # Stärke, Geschick, Intelligenz
ACT_NAMES = {act: f"A{act}" for act in range(1, 11)} | {11: "Epilog"}


@dataclass
class Options:
    """Die Wahl, die bestimmt, welche Zeilen und Seiten gelten."""
    league_start: bool = False
    bandit: str = "none"
    optionals: bool = True
    gem_hints: bool = True  # Gems des Builds als Belohnung/Kauf einsetzen
    gems_all: bool = False  # Quests ohne passende Belohnung trotzdem zeigen
    level_hints: bool = False  # „recommended level“-Zeilen

    def skips(self, line: str) -> bool:
        """Gilt die Zeile für diese Wahl nicht (Ligastart- oder Twink-Zeile)?"""
        return (self.league_start and TWINK in line) or (not self.league_start and LEAGUE_START in line)


@dataclass
class Page:
    lines: list[str]
    condition: list[Any] | None = None  # ["league-start", "yes"] oder ["bandit", "alira" | [...]]

    @classmethod
    def from_raw(cls, raw: Any) -> Page:
        if isinstance(raw, dict):
            return cls(list(raw.get("lines", [])), raw.get("condition") or None)
        return cls(list(raw))

    def applies(self, options: Options) -> bool:
        if not self.condition:
            return True
        kind, value = self.condition[0], self.condition[1]
        if kind == "league-start":
            return bool(value == "yes") == options.league_start
        if kind == "bandit":
            return options.bandit in (value if isinstance(value, list) else [value])
        return False

    def contains(self, text: str) -> bool:
        """Steht text (ohne Groß-/Kleinschreibung) in einer der Zeilen?"""
        needle = text.lower()
        return any(needle in line.lower() for line in self.lines)


@dataclass
class Guide:
    pages: list[Page] = field(default_factory=list)
    gems_left: list[str] = field(default_factory=list)  # Gems des Builds, die nirgends untergekommen sind
