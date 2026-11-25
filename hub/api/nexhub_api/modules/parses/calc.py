"""Rechnung der Parses aus Run-Zusammenfassungen (logs/analysis.summarize) und sortierten DPS-Listen.

Ein Parse ist der Anteil der Vergleichswerte, die kleiner oder gleich dem eigenen Wert sind, in ganzen
Prozent (abgerundet). „Gleich“ zählt mit, damit der beste Charakter der Gilde, der selbst in der Liste steht,
auf 100 kommt.
"""
from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Iterator

from nexproto.classes import CLASS_KEYS

GUILD_MIN = 10  # Charaktere, ab denen der Gildenvergleich angezeigt wird


def percentile(value: float, ranked: list[float]) -> int | None:
    """`ranked` aufsteigend sortiert. Ohne Vergleichswerte: None."""
    if not ranked:
        return None
    return 100 * bisect_right(ranked, value) // len(ranked)


def _killed_players(summaries: Iterable[dict]) -> Iterator[tuple[int, dict]]:
    """(mob, Spieler) aus allen getöteten Bossen, nur Spieler mit bekannter Klasse."""
    for summary in summaries:
        for b in summary.get("bosses", []):
            if not b.get("killed"):
                continue
            for p in b.get("players", []):
                if p.get("cls") in CLASS_KEYS:
                    yield b["mob"], p


def needed_pairs(summaries: Iterable[dict]) -> set[tuple[int, str]]:
    """Boss und Klasse, für die eine Rangliste gebraucht wird."""
    return {(mob, p["cls"]) for mob, p in _killed_players(summaries)}


def guild_bests(summaries: Iterable[dict]) -> dict[tuple[int, str], list[float]]:
    """Je Boss und Klasse die Bestwerte je Charakter (Name und Klasse), aufsteigend."""
    best: dict[tuple[int, str], dict[str, float]] = {}
    for mob, p in _killed_players(summaries):
        names = best.setdefault((mob, p["cls"]), {})
        names[p["name"]] = max(names.get(p["name"], 0.0), float(p["dps"]))
    return {key: sorted(names.values()) for key, names in best.items()}
