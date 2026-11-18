"""XP-Abzug nach Stufenabstand zwischen Charakter und Zone (Leveltracker_Experience, Formel aus dem Wiki).

Innerhalb der „sicheren Zone“ (3 + Stufe/16 Stufen um die eigene) gibt es volle XP, darüber hinaus
sinkt sie steil. Ab Stufe 95 kommt ein fester Abzug dazu.
"""
from __future__ import annotations

from dataclasses import dataclass

HIGH_LEVEL_PENALTY = {95: 1.069518717, 96: 1.129943503, 97: 1.2300123, 98: 1.393728223, 99: 1.666666667}
MIN_MULTIPLIER = 0.01
MAP_LEVEL_START = 70  # ab hier ist die Monsterstufe nicht mehr die „effektive“ Stufe der Zone


@dataclass(frozen=True)
class Experience:
    percent: float  # XP in % der vollen XP
    low: int  # sichere Zone: niedrigste …
    high: int  # … und höchste Zonenstufe ohne Abzug

    def text(self) -> str:
        return f"{self.percent:.0f} %" if self.percent >= 99.5 else f"{self.percent:.1f} %"


def effective_area_level(area_level: int) -> float:
    if area_level <= MAP_LEVEL_START:
        return area_level
    return -0.03 * area_level ** 2 + 5.17 * area_level - 144.9


def experience(level: int, area_level: int, in_town: bool = False) -> Experience:
    """In Stadt und Versteck zählt die eigene Stufe (dort gibt es nichts zu holen)."""
    safe = int(3 + level / 16)
    low, high = max(level - safe, 1), level + safe
    if in_town:
        return Experience(100.0, low, high)
    difference = max(abs(level - effective_area_level(area_level)) - safe, 0) ** 2.5
    multiplier = ((level + 5) / (level + 5 + difference)) ** 1.5
    if level > 94:
        multiplier *= 1 / (1 + 0.1 * (level - 94)) / HIGH_LEVEL_PENALTY.get(level, 1)
    return Experience(max(multiplier, MIN_MULTIPLIER) * 100, low, high)
