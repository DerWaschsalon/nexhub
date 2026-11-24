"""Dropraten aus der Würfel-Beute der hochgeladenen Runs. Rein, ohne Netz und Datenbank.

Eingabe sind die Zusammenfassungen der Runs (analysis.summarize): je besiegtem Boss die Gegenstände, um die
gewürfelt wurde. Gezählt werden nur Runs, deren Aufnahme Beute meldet (`loot_tracked`). Die Rate ist „bei
wie vielen Siegen lag der Gegenstand drin“, mit einem Band, in dem die wahre Rate wahrscheinlich liegt
(Wilson-Intervall). Unter MIN_KILLS Siegen gibt es nur die Zählung, keine Rate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MIN_KILLS = 20
Z_90 = 1.645  # zweiseitig 90 %: so breit ist das Band „wahrscheinlich 1 zu a bis b“


@dataclass
class Boss:
    mob: int
    name: str
    kills: int = 0
    drops: dict[int, int] = field(default_factory=dict)  # Gegenstand → Siege, bei denen er drin lag


def wilson(hits: int, tries: int, z: float = Z_90) -> tuple[float, float]:
    """Unter- und Obergrenze der wahren Rate, wenn bei `tries` Versuchen `hits` Treffer waren."""
    p = hits / tries
    spread = z * math.sqrt(p * (1 - p) / tries + z * z / (4 * tries * tries))
    middle = p + z * z / (2 * tries)
    scale = 1 + z * z / tries
    return max(0.0, (middle - spread) / scale), min(1.0, (middle + spread) / scale)


def rate(drops: int, kills: int) -> dict:
    """Ein Gegenstand eines Bosses: Zählung, und ab MIN_KILLS Siegen „1 zu N“ mit Band (`one_in` von
    `one_in_low` bis `one_in_high`, klein = häufig)."""
    row: dict = {"drops": drops, "kills": kills, "one_in": None, "one_in_low": None, "one_in_high": None}
    if kills < MIN_KILLS or not drops:
        return row
    low, high = wilson(drops, kills)
    return {**row, "one_in": round(kills / drops, 1), "one_in_low": round(1 / high, 1),
            "one_in_high": round(1 / low, 1)}


def count(summaries: list[dict]) -> list[Boss]:
    """Siege und Beute je Boss über alle Runs, die Beute melden; Bosse in der Reihenfolge ihres Auftretens."""
    bosses: dict[int, Boss] = {}
    for summary in summaries:
        if not summary.get("loot_tracked"):
            continue
        for b in summary.get("bosses") or []:
            if not b.get("killed"):
                continue
            boss = bosses.setdefault(b["mob"], Boss(b["mob"], b["name"]))
            boss.kills += 1
            for item_id in {drop["item_id"] for drop in b.get("loot") or []}:
                boss.drops[item_id] = boss.drops.get(item_id, 0) + 1
    return list(bosses.values())


def table(summaries: list[dict]) -> list[dict]:
    """Je Boss seine Gegenstände, der häufigste zuerst (Format der Seite „Beute“)."""
    out = []
    for boss in count(summaries):
        items = [{"item_id": item_id, **rate(drops, boss.kills)} for item_id, drops in boss.drops.items()]
        items.sort(key=lambda item: (-item["drops"], item["item_id"]))
        out.append({"mob": boss.mob, "name": boss.name, "kills": boss.kills, "items": items})
    return out
