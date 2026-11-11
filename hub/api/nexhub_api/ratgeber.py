"""Ratgeber der Armory: was ein Charakter für sich genommen zuerst verbessern kann, ohne Vergleich
mit anderen.

Rein, ohne Netz: Eingabe ist eine Momentaufnahme in einer Sprache (Format aus aion2.py), Ausgabe eine
Liste von Hinweisen in fester Reihenfolge, von schnell erledigt bis teuer. Die Idee folgt der
Endpunkt-Doku von doarjo/aion2-tracker (ohne Lizenz, nur die Erkenntnis übernommen).
"""
from __future__ import annotations

# Klassen, die Schaden machen. Für Tank und Heiler wären Verteidigung und LP kein verschenkter Wert.
DAMAGE_CLASSES = {"ranger", "assassin", "gladiator", "sorcerer", "spiritmaster"}
# Kennungen von Werten, die einem Schadens-Build nichts bringen (in jeder Sprache gleich)
WASTED_FOR_DAMAGE = {
    "HPMax", "MPMax", "HPRegen", "MPRegen", "Restoration", "HpPotionRate",
    "ArmorDefense", "ArmorEvasion", "Evasion", "Block", "CriticalResist", "CriticalDamageDefense",
    "PvEDecreaseDamage", "PvPDamageDefense", "FrontAttackDefense", "MoveSpeed",
}
ORDER = ("sockel", "verzaubern", "stein", "nebenwert", "set")  # leere Sockel sind am schnellsten erledigt


def _item(item: dict) -> dict:
    return {"slot": item.get("slot_name"), "item": item.get("name"), "icon": item.get("icon"),
            "grade": item.get("grade")}


def _wasted(rows: list[dict] | None) -> list[str]:
    return [f"{r.get('name')} {r.get('value')}" for r in rows or [] if r.get("id") in WASTED_FOR_DAMAGE]


def _set_hint(detail: dict, seen: set[str]) -> dict | None:
    """Arkana-Set ohne Bonus: weniger Teile angelegt, als der kleinste Bonus braucht. Je Set einmal."""
    s = detail.get("set")
    degrees = [b.get("degree") for b in (s or {}).get("bonuses") or [] if isinstance(b.get("degree"), int)]
    if not s or not degrees or s.get("name") in seen or s.get("equipped", 0) >= min(degrees):
        return None
    seen.add(s.get("name"))
    return {"art": "set", "set": s.get("name"), "hat": s.get("equipped", 0), "braucht": min(degrees)}


def hints(snapshot: dict, cls: str | None) -> list[dict]:
    """Alle Hinweise zu einer Momentaufnahme. Ohne Werte je Gegenstand (alte Stände) bleibt sie leer."""
    out: list[dict] = []
    sets: set[str] = set()
    damage = cls in DAMAGE_CLASSES
    for item in snapshot.get("equipment") or []:
        detail = item.get("detail") or {}
        where = _item(item)
        slots, stones = detail.get("stone_slots"), detail.get("stones") or []
        if isinstance(slots, int) and len(stones) < slots:
            out.append({"art": "sockel", **where, "frei": slots - len(stones)})
        if detail.get("gain"):
            out.append({"art": "verzaubern", **where, "stufe": detail["gain"]["enchant"],
                        "werte": [f"{s['name']} {s['value']}" for s in detail["gain"]["stats"]]})
        if damage:
            for art, rows in (("stein", stones), ("nebenwert", detail.get("sub"))):
                wasted = _wasted(rows)
                if wasted:
                    out.append({"art": art, **where, "werte": wasted})
        hint = _set_hint(detail, sets)
        if hint:
            out.append(hint)
    out.sort(key=lambda h: ORDER.index(h["art"]))  # stabil: innerhalb einer Art bleibt die Reihenfolge der Plätze
    return out
