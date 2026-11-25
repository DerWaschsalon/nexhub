"""Bewertung der Ausrüstung gegen Top-Spieler derselben Klasse, Vorbild kisk.app/scoring.

Rein, ohne Netz und Datenbank. Eingaben:
  census  Zählung einer Klasse (count_players + add_tops, gespeichert von census.py): je Platz, wie viele
          Top-Spieler welche Zeile der Seelenbindung tragen, und der größte Wert je Platz und Zeile
  rolls   Würfeltabellen je englischem Gegenstandsnamen (metabot.py)
  en, de  Momentaufnahme des Charakters je Sprache (Format aus aion2.py); gerechnet wird englisch,
          die deutschen Namen kommen über die Reihenfolge der Zeilen dazu

Punkte einer Zeile = Anteil der Top-Spieler mit ihr auf diesem Platz × Wert ÷ größter Wert des Platzes.
Note = Summe ÷ bestes Stück des Platzes: die häufigsten Zeilen, voll, und so viele davon, wie ein Teil der
Top-Spieler dort meist trägt. Der Nenner hängt also nicht am eigenen Teil; ein Teil mit weniger Zeilen
kann 100 nicht erreichen, und zwei Teile eines Platzes sind direkt vergleichbar. Den Weg zu einer
besseren Note plant upgrades.py.
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
    out = [{"kind": "stat", "name": s["name"], "value": number(s["value"]),
            "unit": "%" if "%" in str(s["value"]) else ""}
           for s in d.get("sub") or []]
    out += [{"kind": "skill", "name": k["name"], "value": float(k["level"]), "unit": ""} for k in d.get("skills") or []]
    return out


# ---- Zählung (census.py speichert das Ergebnis je Klasse) ----

def count_players(equipments: list[list[dict]]) -> dict:
    """Je Platz: wie viele Spieler ihn bewertbar belegt haben, wie viele welche Zeile tragen, wie viele
    Zeilen Werte bzw. Skills sind (für die Chance, dass ein Wurf ein Skill wird), welche Zeilen Skills
    sind und wie viele Werte und Skills ein Teil dort meist hat (`width`, für das beste Stück)."""
    slots: dict[str, dict] = {}
    sizes: dict[str, Counter[tuple[int, int]]] = {}
    for equipment in equipments:
        seen: dict[str, set[str]] = {}
        for item in equipment:
            slot = group(str(item.get("slot_name")))
            lines = lines_of(item)
            if not lines:
                continue
            entry = slots.setdefault(slot, {"players": 0, "lines": Counter(), "kinds": [0, 0], "skills": set()})
            seen.setdefault(slot, set()).update(ln["name"] for ln in lines)
            skills = [ln["name"] for ln in lines if ln["kind"] == "skill"]
            entry["skills"].update(skills)
            sizes.setdefault(slot, Counter())[len(lines) - len(skills), len(skills)] += 1
            if slot not in ARCANA:
                entry["kinds"][0] += len(lines) - len(skills)
                entry["kinds"][1] += len(skills)
        for slot, names in seen.items():
            slots[slot]["players"] += 1
            slots[slot]["lines"].update(names)
    # die häufigste Größe statt der größten, damit ein einzelnes Sonderteil das beste Stück nicht verschiebt
    return {slot: {**e, "lines": dict(e["lines"]), "skills": sorted(e["skills"]),
                   "width": list(sizes[slot].most_common(1)[0][0])}
            for slot, e in slots.items()}


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

    def rated(self, slot: str) -> bool:
        """Zählungen von vor dem 24.11.2026 kennen `width` noch nicht; bis zur nächsten Zählung (stündlich)
        gibt es für sie keine Note."""
        return bool((self.slots.get(group(slot)) or {}).get("width"))

    def width(self, slot: str) -> tuple[int, int]:
        """Wie viele Werte und Skills ein Teil der Top-Spieler auf diesem Platz meist hat."""
        stats, skills = (self.slots.get(group(slot)) or {}).get("width") or (0, 0)
        return stats, skills

    def skill_names(self, slot: str) -> list[str]:
        return (self.slots.get(group(slot)) or {}).get("skills") or []

    def best_piece(self, slot: str) -> float:
        """Punkte des besten Stücks dieses Platzes: die häufigsten Werte und Skills, voll, so viele wie ein
        Teil der Top-Spieler dort meist trägt. Gleich für jedes Teil des Platzes."""
        entry = self.slots.get(group(slot)) or {}
        if not entry.get("width"):
            return 1.0
        skill_names = set(self.skill_names(slot))
        stats = sorted((n for name, n in entry["lines"].items() if name not in skill_names), reverse=True)
        skills = sorted((n for name, n in entry["lines"].items() if name in skill_names), reverse=True)
        wide_stats, wide_skills = self.width(slot)
        return sum(stats[:wide_stats] + skills[:wide_skills]) / entry["players"] or 1.0


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
    best = census.best_piece(item["slot_name"])
    return round(100 * sum(ln["points"] for ln in lines) / best, 1), lines


def ideal_piece(census: Census, item: dict, table: dict, cls: str) -> list[dict]:
    """Das Idealteil des Platzes, soweit dieser Gegenstand es würfeln kann: die Werte und Skills, die
    Top-Spieler dort am häufigsten tragen (so viele, wie ein Teil meist hat), nach Priorität. Je Zeile der
    Anteil, der Höchstwert auf diesem Gegenstand und ob das Teil sie schon hat (`have`)."""
    slot = item["slot_name"]
    own = {line["name"]: line for line in lines_of(item)}
    values = {**{name: line["value"] for name, line in own.items()}, **_item_max(table, cls)}
    skills = set(census.skill_names(slot)) | {name for name, line in own.items() if line["kind"] == "skill"}
    skills |= {o["name"] for o in ((table.get("skills") or {}).get(cls) or {}).get("options") or []}
    ranked = sorted(values, key=lambda name: (-census.share(slot, name), -points(census, slot, name, values[name])))
    wide_stats, wide_skills = census.width(slot)
    chosen = [n for n in ranked if n not in skills][:wide_stats] + [n for n in ranked if n in skills][:wide_skills]
    return [{"name": name, "share": round(census.share(slot, name), 3), "max": values[name], "have": name in own}
            for name in chosen if census.share(slot, name) > 0]


# ---- Ausgabe für die Armory ----

def names_de(item_en: dict, item_de: dict | None) -> dict[str, str]:
    """Englischer → deutscher Name der Zeilen eines Gegenstands, über ihre Reihenfolge bei NC."""
    if not item_de:
        return {}
    return {en["name"]: de["name"] for en, de in zip(lines_of(item_en), lines_of(item_de))
            if en["kind"] == de["kind"]}


def _table_names_de(table: dict, cls: str) -> dict[str, str]:
    """Englischer → deutscher Name der Zeilen, die ein Gegenstand würfeln kann (aus der Würfeltabelle)."""
    rows = (table.get("rolls") or []) + (((table.get("skills") or {}).get(cls) or {}).get("options") or [])
    return {r["name"]: r["name_de"] for r in rows if r.get("name_de")}


def rate_item(census: Census, item: dict, item_de: dict | None, table: dict, cls: str, lang: str) -> dict:
    """Bewertung eines Gegenstands in einer Sprache (Format wie modules/logs/rating.ts)."""
    value, lines = score(census, item, table, cls)
    names = {**_table_names_de(table, cls), **names_de(item, item_de)} if lang == "de" else {}
    shown = [{"kind": ln["kind"], "name": names.get(ln["name"], ln["name"]), "value": ln["value"], "unit": ln["unit"],
              "max": ln["max"], "share": ln["share"]} for ln in lines]
    ideal = [{**line, "name": names.get(line["name"], line["name"])} for line in ideal_piece(census, item, table, cls)]
    return {"slot": item["slot_name"], "score": value, "letter": letter(value), "lines": shown,
            "ideal": len([line for line in ideal if line["have"]]), "ideal_of": len(ideal), "ideal_piece": ideal,
            "source": table.get("url"), "upgrade": None}


def rate(census: dict, rolls: dict, en: dict, de: dict | None, cls: str, lang: str) -> dict:
    """Alle bewertbaren Gegenstände eines Charakters: Würfeltabelle vorhanden oder Arkana. Den Weg zur
    Zielnote (`upgrade`) trägt die Armory-Route aus upgrades.plan() nach."""
    c = Census(census["slots"], census.get("tops") or {})
    by_slot_de = {i["slot_name"]: i for i in (de or {}).get("equipment") or []}
    items = []
    for item in en.get("equipment") or []:
        table = rolls.get(item["name"]) or {}
        if not lines_of(item) or not (table.get("rolls") or item["slot_name"] in ARCANA):
            continue
        if not c.rated(item["slot_name"]):
            continue
        items.append(rate_item(c, item, by_slot_de.get(item["slot_name"]), table, cls, lang))
    size = max((e["players"] for e in c.slots.values()), default=0)
    return {"size": size, "group": census.get("group", ""), "items": items}
