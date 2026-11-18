"""Suchtexte für das Händlerfenster: im Spiel Strg+F, einfügen, und die gesuchten Gems leuchten auf.

Das Suchfeld nimmt höchstens 250 Zeichen; längere Listen werden auf mehrere Suchtexte verteilt.
Sortiert wie im Original (Stärke, Geschick, Intelligenz, Rest; je erst aktive Gems, dann Supports),
damit zusammengehörige Gems im selben Suchtext landen.
"""
from __future__ import annotations

from .data import LevelingData

MAX_PATTERN = 246  # 250 minus „^(“ und „)$“
ATTRIBUTE_COUNT = 4  # Stärke, Geschick, Intelligenz, ohne


def _pattern(gem: str) -> str:
    # „support“ ist im Händlerfenster nur am Ende sichtbar; „.*t“ passt auf „… Support“
    return gem.replace(" support", ".*t").replace(" ", ".")


def _ordered(gems: list[str], data: LevelingData) -> list[str]:
    def order(gem: str) -> tuple[int, int]:
        attribute = data.gem(gem).get("attribute") or ATTRIBUTE_COUNT
        return attribute, 1 if " support" in gem else 0
    return sorted(dict.fromkeys(gems), key=order)


def gem_search(gems: list[str], data: LevelingData) -> list[str]:
    return _chunks([_pattern(gem) for gem in _ordered(gems, data)])


def item_search(items: list[str]) -> list[str]:
    return _chunks([item.replace(" ", r"\s") for item in items])


def _chunks(patterns: list[str]) -> list[str]:
    out: list[str] = []
    current = ""
    for pattern in patterns:
        if current and len(current) + 1 + len(pattern) > MAX_PATTERN:
            out.append(current)
            current = ""
        current = f"{current}|{pattern}" if current else pattern
    if current:
        out.append(current)
    return [f"^({text})$" for text in out]
