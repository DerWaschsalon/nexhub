"""Bewertung der Ausrüstung gegen Top-Spieler derselben Klasse, Vorbild kisk.app/scoring.

Rein, ohne Netz und Datenbank. Eingaben:
  census  Zählung einer Klasse (count_players + add_tops, gespeichert von census.py): je Platz, wie viele
          Top-Spieler welche Zeile der Seelenbindung tragen, und der größte Wert je Platz und Zeile
  rolls   Würfeltabellen je englischem Gegenstandsnamen (metabot.py)
  en, de  Momentaufnahme des Charakters je Sprache (Format aus aion2.py); gerechnet wird englisch,
          die deutschen Namen kommen über die Reihenfolge der Zeilen dazu

Punkte einer Zeile = Anteil der Top-Spieler mit ihr auf diesem Platz × Wert ÷ größter Wert des Platzes.
Note = Summe ÷ bestes mögliches Stück (die häufigsten Zeilen des Platzes, voll). Upgrades: jede Zeile,
die nicht zu den idealen gehört, neu würfeln, Ziel sind die fehlenden idealen Zeilen nach Priorität.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# Gleiche Plätze zählen zusammen
SLOT_GROUP = {"Earring1": "Earring", "Earring2": "Earring", "Ring1": "Ring", "Ring2": "Ring",
              "Bracelet1": "Bracelet", "Bracelet2": "Bracelet"}
ARCANA = {"Arcana1", "Arcana2", "Arcana3", "Arcana4", "Arcana5"}
# Notenbänder in Prozent des besten Stücks, wie kisk.app/scoring sie veröffentlicht
BOUNDS = (("BiS", 90.0), ("S+", 55.0), ("S", 35.0), ("A", 22.0), ("B", 12.0), ("C", 5.0), ("D", 0.0))
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def group(slot: str) -> str:
    return SLOT_GROUP.get(slot, slot)


def number(text: object) -> float:
    found = _NUMBER.search(str(text or ""))
    return float(found.group()) if found else 0.0


def letter(score: float) -> str:
    return next(name for name, low in BOUNDS if score >= low)


def lines_of(item: dict) -> list[dict]:
    """Zeilen der Seelenbindung eines Gegenstands: Werte und verstärkte Skills, in der Reihenfolge von NC."""
    d = item.get("detail") or {}
    out = [{"kind": "stat", "name": s["name"], "value": number(s["value"]), "unit": "%" if "%" in str(s["value"]) else ""}
           for s in d.get("sub") or []]
    out += [{"kind": "skill", "name": k["name"], "value": float(k["level"]), "unit": ""} for k in d.get("skills") or []]
    return out


# ---- Zählung (census.py speichert das Ergebnis je Klasse) ----

def count_players(equipments: list[list[dict]]) -> dict:
    """Je Platz: wie viele Spieler ihn bewertbar belegt haben, wie viele welche Zeile tragen und wie
    viele Zeilen Werte bzw. Skills sind (für die Chance, dass ein Wurf ein Skill wird)."""
    slots: dict[str, dict] = {}
    for equipment in equipments:
        seen: dict[str, set[str]] = {}
        for item in equipment:
            slot = group(str(item.get("slot_name")))
            lines = lines_of(item)
            if not lines:
                continue
            entry = slots.setdefault(slot, {"players": 0, "lines": Counter(), "kinds": [0, 0]})
            seen.setdefault(slot, set()).update(l["name"] for l in lines)
            if slot not in ARCANA:
                for line in lines:
                    entry["kinds"][line["kind"] == "skill"] += 1
        for slot, names in seen.items():
            slots[slot]["players"] += 1
            slots[slot]["lines"].update(names)
    return {slot: {**e, "lines": dict(e["lines"])} for slot, e in slots.items()}


def add_tops(census: dict, items_by_slot: dict[str, set[str]], rolls: dict, cls: str) -> dict:
    """Größter Wert je Platz und Zeile aus den Würfeltabellen aller Gegenstände dieses Platzes."""
    tops: dict[str, dict[str, float]] = {}
    for slot, names in items_by_slot.items():
        best = tops.setdefault(group(slot), {})
        for name in names:
            table = rolls.get(name) or {}
            for r in table.get("rolls") or []:
                best[r["name"]] = max(best.get(r["name"], 0.0), r["max"])
            skills = (table.get("skills") or {}).get(cls) or {}
            for o in skills.get("options") or []:
                best[o["name"]] = max(best.get(o["name"], 0.0), float(skills.get("max_level") or 1))
    return {**census, "tops": tops}


@dataclass
class Census:
    """Gespeicherte Zählung einer Klasse, zum Nachschlagen."""
    slots: dict[str, dict]
    tops: dict[str, dict[str, float]]

    def share(self, slot: str, name: str) -> float:
        entry = self.slots.get(group(slot)) or {}
        return (entry.get("lines") or {}).get(name, 0) / entry["players"] if entry.get("players") else 0.0

    def top(self, slot: str, name: str) -> float | None:
        return (self.tops.get(group(slot)) or {}).get(name)

    def p_skill(self, slot: str) -> float:
        """Schätzung: wie oft ein Wurf auf diesem Platz ein Skill wird (Anteil bei den Top-Spielern)."""
        stats, skills = (self.slots.get(group(slot)) or {}).get("kinds") or [0, 0]
        return skills / (stats + skills) if stats + skills else 0.0

    def best_piece(self, slot: str, n: int) -> float:
        entry = self.slots.get(group(slot)) or {}
        shares = sorted((c / entry["players"] for c in (entry.get("lines") or {}).values()), reverse=True) \
            if entry.get("players") else []
        return sum(shares[:n]) or 1.0


# ---- Bewertung eines Gegenstands ----

def points(census: Census, slot: str, name: str, value: float) -> float:
    top = census.top(slot, name) or value or 1.0
    return census.share(slot, name) * min(value / top, 1.0)


def _item_max(table: dict, cls: str) -> dict[str, float]:
    """Höchstwert je Zeile auf genau diesem Gegenstand."""
    out = {r["name"]: r["max"] for r in table.get("rolls") or []}
    skills = (table.get("skills") or {}).get(cls) or {}
    out.update({o["name"]: float(skills.get("max_level") or 1) for o in skills.get("options") or []})
    return out


def score(census: Census, item: dict, table: dict, cls: str) -> tuple[float, list[dict]]:
    """Note in Punkten (0 bis 100) und die Zeilen mit Anteil, Höchstwert und Punkten."""
    lines = lines_of(item)
    own_max = _item_max(table, cls)
    for line in lines:
        line["share"] = round(census.share(item["slot_name"], line["name"]), 3)
        line["max"] = own_max.get(line["name"]) or census.top(item["slot_name"], line["name"])
        line["points"] = points(census, item["slot_name"], line["name"], line["value"])
    best = census.best_piece(item["slot_name"], max(len(lines), 1))
    return round(100 * sum(l["points"] for l in lines) / best, 1), lines


def ideal_lines(census: Census, item: dict, table: dict, cls: str, n: int) -> list[str]:
    """Die n Zeilen, die Top-Spieler auf diesem Platz am häufigsten tragen und dieser Gegenstand würfeln
    kann, nach Priorität (Anteil, bei Gleichstand der größere Wert)."""
    values = _item_max(table, cls)
    for line in lines_of(item):
        values.setdefault(line["name"], line["value"])
    slot = item["slot_name"]
    ranked = sorted(values, key=lambda nm: (-census.share(slot, nm), -points(census, slot, nm, values[nm])))
    return ranked[:n]


def pool(census: Census, item: dict, table: dict, cls: str) -> list[dict]:
    """Was beim Neuwürfeln einer Zeile kommen kann, ohne die Zeilen, die schon drauf sind: Werte mit
    ihrer Chance von MetaBot, Skills geschätzt über den Anteil der Skill-Zeilen auf dem Platz."""
    have = {l["name"] for l in lines_of(item)}
    stats = [r for r in table.get("rolls") or [] if r["name"] not in have]
    skill_table = (table.get("skills") or {}).get(cls) or {}
    skills = [o for o in skill_table.get("options") or [] if o["name"] not in have]
    p_skill = census.p_skill(item["slot_name"]) if skills and stats else (1.0 if skills else 0.0)
    out = []
    total = sum(r["chance"] for r in stats) or 1.0
    for r in stats:
        out.append({"name": r["name"], "name_de": r.get("name_de"), "chance": (1 - p_skill) * r["chance"] / total,
                    "lo": r["min"], "hi": r["max"]})
    total = sum(o["chance"] for o in skills) or 1.0
    for o in skills:
        out.append({"name": o["name"], "name_de": o.get("name_de"), "chance": p_skill * o["chance"] / total,
                    "lo": 1.0, "hi": float(skill_table.get("max_level") or 1)})
    return out


def _gains(census: Census, slot: str, line: dict, candidates: list[dict], best: float) -> list[dict]:
    """Zugewinn in Punkten, wenn diese Zeile zu einem der Kandidaten wird (niedrigster/höchster Wurf)."""
    out = []
    for c in candidates:
        lo = 100 * (points(census, slot, c["name"], c["lo"]) - line["points"]) / best
        hi = 100 * (points(census, slot, c["name"], c["hi"]) - line["points"]) / best
        out.append({**c, "gain_lo": round(lo, 1), "gain_hi": round(hi, 1)})
    return out


def upgrade(census: Census, item: dict, table: dict, cls: str) -> dict | None:
    """Weg zu Best in Slot: jede Zeile, die nicht ideal ist, neu würfeln (die schwächste zuerst); Ziel
    sind die fehlenden idealen Zeilen nach Priorität, daneben, was mindestens halb so viel bringt."""
    if not table.get("rolls"):
        return None  # Arkana und feste Werte (Armbänder) würfelt man nicht neu
    now, lines = score(census, item, table, cls)
    slot = item["slot_name"]
    ideal = ideal_lines(census, item, table, cls, len(lines))
    missing = [nm for nm in ideal if nm not in {l["name"] for l in lines}]
    weak = sorted((l for l in lines if l["name"] not in ideal), key=lambda l: l["points"])
    best = census.best_piece(slot, max(len(lines), 1))
    candidates = pool(census, item, table, cls)
    steps, lo_total, hi_total = [], now, now
    for line in weak:
        if not missing:
            break
        gains = _gains(census, slot, line, candidates, best)
        hits = sorted((g for g in gains if g["name"] in missing), key=lambda g: missing.index(g["name"]))
        if not hits:
            continue
        top = max(g["gain_hi"] for g in hits)
        fallback = sorted((g for g in gains if g["name"] not in missing and g["gain_lo"] > 0 and g["gain_hi"] >= top / 2),
                          key=lambda g: -g["gain_hi"])
        steps.append({"line": line, "chance": round(100 * sum(g["chance"] for g in hits), 1),
                      "best": hits, "good": fallback})
        # angenommen, die wichtigste fehlende Zeile kommt; sie fällt für die nächsten Schritte weg
        landed = hits[0]
        lo_total += landed["gain_lo"]
        hi_total += landed["gain_hi"]
        missing.remove(landed["name"])
        candidates = [c for c in candidates if c["name"] != landed["name"]]
    if not steps:
        return None
    lo_total, hi_total = round(min(lo_total, 100.0), 1), round(min(hi_total, 100.0), 1)
    return {"steps": steps, "after": [lo_total, hi_total], "after_letter": letter(lo_total)}


# ---- Ausgabe für die Armory ----

def _names_de(item_en: dict, item_de: dict | None) -> dict[str, str]:
    """Englischer → deutscher Name der Zeilen eines Gegenstands, über ihre Reihenfolge bei NC."""
    if not item_de:
        return {}
    return {en["name"]: de["name"] for en, de in zip(lines_of(item_en), lines_of(item_de))
            if en["kind"] == de["kind"]}


def _target(g: dict, lang: str) -> dict:
    name = (g.get("name_de") or g["name"]) if lang == "de" else g["name"]
    return {"name": name, "gain_lo": g["gain_lo"], "gain_hi": g["gain_hi"]}


def rate_item(census: Census, item: dict, item_de: dict | None, table: dict, cls: str, lang: str) -> dict:
    """Bewertung eines Gegenstands in einer Sprache (Format wie modules/logs/rating.ts)."""
    value, lines = score(census, item, table, cls)
    ideal = set(ideal_lines(census, item, table, cls, len(lines)))
    names = _names_de(item, item_de) if lang == "de" else {}
    up = upgrade(census, item, table, cls)
    shown = [{"kind": l["kind"], "name": names.get(l["name"], l["name"]), "value": l["value"], "unit": l["unit"],
              "max": l["max"], "share": l["share"]} for l in lines]
    steps = [{"line": names.get(s["line"]["name"], s["line"]["name"]), "chance": s["chance"],
              "tiers": {k: [_target(g, lang) for g in s[k]] for k in ("best", "good") if s[k]}}
             for s in up["steps"]] if up else []
    return {"slot": item["slot_name"], "score": value, "letter": letter(value), "lines": shown,
            "ideal": len([l for l in lines if l["name"] in ideal]), "ideal_of": len(lines),
            "source": table.get("url"),
            "upgrade": {"steps": steps, "after": up["after"], "after_letter": up["after_letter"]} if up else None}


def rate(census: dict, rolls: dict, en: dict, de: dict | None, cls: str, lang: str) -> dict:
    """Alle bewertbaren Gegenstände eines Charakters: Würfeltabelle vorhanden oder Arkana."""
    c = Census(census["slots"], census.get("tops") or {})
    by_slot_de = {i["slot_name"]: i for i in (de or {}).get("equipment") or []}
    items = []
    for item in en.get("equipment") or []:
        table = rolls.get(item["name"]) or {}
        if not lines_of(item) or not (table.get("rolls") or item["slot_name"] in ARCANA):
            continue
        if not (c.slots.get(group(item["slot_name"])) or {}).get("players"):
            continue
        items.append(rate_item(c, item, by_slot_de.get(item["slot_name"]), table, cls, lang))
    size = max((e["players"] for e in c.slots.values()), default=0)
    return {"size": size, "group": census.get("group", ""), "items": items}
