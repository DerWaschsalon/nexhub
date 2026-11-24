"""Der Stand des Meters in den Formen, die der Daemon weitergibt: gekürzt für die Leiste (`compact`),
vollständig als Endstand eines Kampfs (`fight_view`). Rein, ohne Zustand.

Beide Quellen liefern dasselbe Zeilenformat: das Stream-Overlay des A2Tools-Meters und deckbar-capture,
das es genauso baut (capture/src/view.rs).
"""
from __future__ import annotations

from typing import Any

from nexproto.classes import CLASS_KEYS

MAX_ROWS = 8


def _int(v: Any) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def compact(snap: dict, limit: int = MAX_ROWS) -> dict:
    """Snapshot des Meters → State-Wert `dps` (nur, was das Display braucht)."""
    rows = []
    for r in snap.get("rows") or []:
        if not isinstance(r, dict) or len(rows) >= limit:
            continue
        cls = r.get("cls")
        pct = r.get("pct")
        rows.append({
            "name": str(r.get("name") or "?")[:24],
            "cls": cls if cls in CLASS_KEYS else None,
            "dps": _int(r.get("dps")),
            "dmg": _int(r.get("dmg")),
            "pct": round(float(pct), 1) if isinstance(pct, (int, float)) else 0.0,
            "you": bool(r.get("you")),
        })
    hp = snap.get("hp")
    return {
        "target": str(snap.get("target") or "")[:40],
        "time": _int(snap.get("timeMs")) // 1000,
        "hp": round(float(hp), 1) if isinstance(hp, (int, float)) else None,
        "rows": rows,
    }


def fight_view(snap: dict) -> dict:
    """Snapshot → Endstand eines Kampfs für Weitergaben (hub.py): alle Zeilen, mit Ziel-ID, Boss und
    Gruppen-Flag. `party` ist None, wenn die Quelle es nicht kennt (A2Tools-Stream, altes deckbar-capture)."""
    rows = []
    for r in snap.get("rows") or []:
        if not isinstance(r, dict):
            continue
        cls = r.get("cls")
        party = r.get("party")
        rows.append({
            "name": str(r.get("name") or "?")[:32],
            "cls": cls if cls in CLASS_KEYS else None,
            "dps": _int(r.get("dps")),
            "dmg": _int(r.get("dmg")),
            "you": bool(r.get("you")),
            "party": party if isinstance(party, bool) else None,
        })
    hp = snap.get("hp")
    tid = snap.get("targetId")
    return {
        "target": str(snap.get("target") or "")[:80],
        "target_id": tid if isinstance(tid, int) else None,
        "boss": bool(snap.get("boss")),
        "time": _int(snap.get("timeMs")) // 1000,
        "hp": round(float(hp), 1) if isinstance(hp, (int, float)) else None,
        "rows": rows,
    }


def total_damage(value: dict | None) -> int:
    return sum(r["dmg"] for r in value["rows"]) if value else 0
