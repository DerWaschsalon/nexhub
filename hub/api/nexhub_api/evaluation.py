"""Build-Check: ein Charakter gegen eine Gruppe von Top-Spielern, Feld für Feld.

Rein, ohne Netz und Datenbank: Eingabe sind Momentaufnahmen in einer Sprache (Format aus aion2.py),
Ausgabe je Feld eine Ampel und was die Gruppe dort hat. Für Laien nachvollziehbar statt gewichtet:
die Priorität einer Empfehlung ist, wie viele aus der Gruppe es besser haben („12 von 15“).
"""
from __future__ import annotations

from collections import Counter
from statistics import median

from .aion2 import combat_power, item_level

Key = tuple[str, str, str]  # (Bereich, Platz, Feld)
NONE = "—"  # Auswahl, die fehlt (kein Flügel, kein Titel)
# Felder, die nur zählen, wenn sie mindestens zwei Drittel der Gruppe haben: mit echten Daten war
# „8 von 15 haben Manastein HP“ Rauschen, keine Empfehlung
PRESENCE = ("sub:", "stone:", "godstone:", "skill:")
PRESENCE_SHARE = 2 / 3
# Eine Auswahl, bei der nicht mal ein Drittel dasselbe hat, ist keine Empfehlung (z. B. das Haustier)
CONSENSUS = 1 / 3
TODO = 5


def _equipment(item: dict) -> dict[str, float | str]:
    detail = item.get("detail") or {}
    out: dict[str, float | str] = {"grade": item.get("grade") or NONE, "enchant": item.get("enchant") or 0,
                                   "exceed": item.get("exceed") or 0, "stones": len(detail.get("stones") or [])}
    if detail.get("set"):
        out["set"] = detail["set"].get("name") or NONE
    # Vorhandensein als 0/1, damit es wie eine Zahl ausgewertet wird
    for prefix, rows in (("sub:", "sub"), ("stone:", "stones"), ("godstone:", "godstones"), ("skill:", "skills")):
        for row in detail.get(rows) or []:
            out[prefix + str(row.get("name"))] = 1
    return out


def fields(snapshot: dict) -> dict[Key, float | str]:
    """Alle vergleichbaren Werte einer Momentaufnahme. Was fehlt, ist 0 bzw. „—“."""
    out: dict[Key, float | str] = {
        ("profile", "", "combat_power"): combat_power(snapshot) or 0,
        ("profile", "", "item_level"): item_level(snapshot) or 0,
        ("wing", "", "name"): (snapshot.get("wing") or {}).get("name") or NONE,
        ("wing", "", "enchant"): (snapshot.get("wing") or {}).get("enchant") or 0,
        ("pet", "", "name"): (snapshot.get("pet") or {}).get("name") or NONE,
    }
    for s in snapshot.get("stats") or []:
        if s.get("type") != "ItemLevel":
            out[("stats", "", str(s.get("type")))] = s.get("value") or 0
    for item in snapshot.get("equipment") or []:
        for key, value in _equipment(item).items():
            out[("equipment", str(item.get("slot_name")), key)] = value
    for board in snapshot.get("daevanion") or []:
        out[("daevanion", str(board.get("name")), "open_nodes")] = board.get("open_nodes") or 0
    for skill in snapshot.get("skills") or []:
        if skill.get("learned", True):
            out[("skills", str(skill.get("name")), "level")] = skill.get("level") or 0
    for title in (snapshot.get("titles") or {}).get("equipped") or []:
        out[("titles", str(title.get("category")), "name")] = title.get("name") or NONE
    return out


def _number(mine: float, values: list[float]) -> dict:
    mid = median(values)
    better = sum(v > mine for v in values)
    light = "green" if mine >= mid else "red" if better > len(values) * 2 / 3 else "yellow"
    return {"kind": "number", "median": mid, "common": [], "better": better, "light": light}


def _choice(mine: str, values: list[str]) -> dict:
    counts = Counter(values)
    common = [{"value": v, "count": n} for v, n in counts.most_common(2)]
    if mine in [c["value"] for c in common] or common[0]["count"] < len(values) * CONSENSUS:
        light = "green"
    else:
        light = "yellow" if counts[mine] >= 2 else "red"
    return {"kind": "choice", "median": None, "common": common, "better": common[0]["count"], "light": light}


def _keys(own: dict[Key, float | str], group: list[dict[Key, float | str]]) -> list[Key]:
    """Eigene Felder plus, was zwei Drittel der Gruppe haben und dem Charakter fehlt (Zusatzwerte,
    Manasteine, Gottsteine, verstärkte Skills, gelernte Skills)."""
    counts = Counter(k for g in group for k in g)
    extra = [k for k, n in counts.items() if k not in own and n >= len(group) * PRESENCE_SHARE
             and (k[2].startswith(PRESENCE) or k[0] == "skills")]
    return list(own) + sorted(extra)


def evaluate(own: dict, group: list[dict]) -> dict:
    mine_all = fields(own)
    theirs = [fields(g) for g in group]
    result = []
    for key in _keys(mine_all, theirs):
        mine = mine_all.get(key, 0)
        values = [g.get(key, NONE if isinstance(mine, str) else 0) for g in theirs]
        rated = _choice(mine, values) if isinstance(mine, str) else _number(mine, values)
        result.append({"area": key[0], "slot": key[1], "key": key[2], "mine": mine, **rated})
    # Kampfkraft und Gegenstandsstufe steigen von selbst, wenn man den Rest verbessert
    open_items = [f for f in result if f["light"] != "green" and f["area"] != "profile"]
    # Gleichstand: Ausrüstung zuerst, weil man dort am ehesten selbst etwas tun kann
    open_items.sort(key=lambda f: (-f["better"], f["area"] != "equipment"))
    return {"size": len(group), "fields": result, "todo": open_items[:TODO]}
