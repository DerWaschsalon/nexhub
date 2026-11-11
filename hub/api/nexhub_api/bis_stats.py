"""Auswertung der BiS-Listen: was die Top-Spieler einer Klasse je Platz tragen, als Anteile.

Rein, ohne Netz und Datenbank. Eingabe ist der Bestand einer Klasse (bis_collector.py) in einer Sprache:
je Spieler {"equipment": [...], "skills": [...]} im Format von aion2.py. Gezählt wird „kommt vor“, nicht die
Summe: wer Krit doppelt auf einem Teil hat, zählt für den Anteil einmal.

Je Platz entsteht ein typischer Gegenstand im Format der Armory (häufigster Gegenstand, Median der
Verzauberung, Zusatzwerte mit Median, häufige Manasteine, Göttersteine und Skills), dazu der Anteil je
Zeile (`lines`, Format wie rating.py) und die häufigsten Gegenstände. So zeigt die Web-Oberfläche ihn mit
denselben Bausteinen wie einen Charakter der Armory.
"""
from __future__ import annotations

from collections import Counter
from statistics import median

from .rating import lines_of, number

MIN_SAMPLE = 10  # mit weniger Spielern gibt es keine Prozente (BiS-Seite) und keine Bewertung (census.py)
MIN_SHARE = 0.10  # seltener ist Rauschen und macht das Fenster nur lang
ITEMS_SHOWN = 3  # die häufigsten Gegenstände je Platz
# Skills: gelernt und angelegt zählt bei aktiven und Stigmen, bei passiven reicht gelernt (die legt man nicht an)
COUNT_EQUIPPED = {"Active", "Dp"}


def aggregate(samples: list[dict]) -> dict:
    """Plätze und Skills einer Klasse. `samples`: Bestand in einer Sprache."""
    by_slot: dict[str, list[dict]] = {}
    for sample in samples:
        for item in sample.get("equipment") or []:
            if item.get("detail"):
                by_slot.setdefault(str(item["slot_name"]), []).append(item)
    return {"slots": [_slot(items, len(samples)) for items in by_slot.values()],
            "skills": _skills([s.get("skills") or [] for s in samples])}


def _shares(sets: list[set[str]], size: int) -> dict[str, float]:
    """Anteil je Name über alle Spieler, häufigste zuerst, ohne die seltenen."""
    counts = Counter(name for names in sets for name in names)
    return {name: n / size for name, n in counts.most_common() if n / size >= MIN_SHARE}


def _slot(items: list[dict], size: int) -> dict:
    """Ein Platz: typischer Gegenstand, Anteile seiner Zeilen und die häufigsten Gegenstände."""
    names = Counter(str(i["name"]) for i in items)
    top_name = names.most_common(1)[0][0]
    enchant = round(median(i.get("enchant") or 0 for i in items))
    typical = _representative([i for i in items if i["name"] == top_name], enchant)
    stats, stat_lines = _rolls(items, "stat")
    skills, skill_lines = _rolls(items, "skill")
    stones, stone_lines = _named(items, "stones")
    godstones, godstone_lines = _named(items, "godstones")
    at_max = [i for i in items if _at_max_enchant(i)]
    detail = {**typical["detail"], "sub": stats, "skills": skills, "stones": stones, "godstones": godstones}
    return {
        "item": {**typical, "enchant": enchant, "exceed": round(median(i.get("exceed") or 0 for i in items)),
                 "detail": detail},
        "players": len(items),
        "share": len(items) / size,
        "max_enchant": len(at_max) / len(items),
        "items": [_common_item(items, name, count) for name, count in names.most_common(ITEMS_SHOWN)],
        "lines": stat_lines + skill_lines + stone_lines + godstone_lines,
    }


def _at_max_enchant(item: dict) -> bool:
    top = item["detail"].get("max_enchant")
    return bool(top) and (item.get("enchant") or 0) >= top


def _common_item(items: list[dict], name: str, count: int) -> dict:
    """Einer der häufigsten Gegenstände eines Platzes mit seinem Anteil."""
    first = next(i for i in items if i["name"] == name)
    return {"name": name, "share": count / len(items), "icon": first.get("icon"), "grade": first.get("grade")}


def _representative(items: list[dict], enchant: int) -> dict:
    """Ein Stück des häufigsten Gegenstands, möglichst mit der üblichen Verzauberung: von ihm kommen
    Grundwerte, Kategorie und Set."""
    return next((i for i in items if i.get("enchant") == enchant), items[0])


def _rolls(items: list[dict], kind: str) -> tuple[list[dict], list[dict]]:
    """Zusatzwerte (kind „stat“) oder verstärkte Skills („skill“): je Name Anteil und Median des Werts.
    Gibt die Zeilen für den typischen Gegenstand und die Anteile (Format rating.RatedLine) zurück."""
    rows = [[line for line in lines_of(i) if line["kind"] == kind] for i in items]
    shares = _shares([{line["name"] for line in r} for r in rows], len(items))
    shown, lines = [], []
    for name, share in shares.items():
        found = [line for r in rows for line in r if line["name"] == name]
        value, unit = round(median(line["value"] for line in found), 1), found[0]["unit"]
        if kind == "skill":
            shown.append({"name": name, "level": value, "icon": _skill_icon(items, name)})
        else:
            shown.append({"name": name, "value": f"{value:g}{unit}"})
        lines.append({"kind": kind, "name": name, "value": value, "unit": unit,
                      "max": max(line["value"] for line in found), "share": round(share, 3)})
    return shown, lines


def _skill_icon(items: list[dict], name: str) -> str | None:
    skills = [s for i in items for s in i["detail"].get("skills") or [] if s.get("name") == name]
    return skills[0].get("icon") if skills else None


def _named(items: list[dict], field: str) -> tuple[list[dict], list[dict]]:
    """Manasteine („stones“) oder Göttersteine („godstones“): je Name Anteil, dazu das häufigste Stück."""
    pieces = [i["detail"].get(field) or [] for i in items]
    shares = _shares([{p["name"] for p in ps} for ps in pieces], len(items))
    kind = "stone" if field == "stones" else "godstone"
    shown, lines = [], []
    for name, share in shares.items():
        found = [p for ps in pieces for p in ps if p["name"] == name]
        piece = _most_common_piece(found)
        shown.append(piece)
        value = number(piece.get("value")) if kind == "stone" else 0.0
        lines.append({"kind": kind, "name": name, "value": value, "unit": "", "max": None, "share": round(share, 3)})
    return shown, lines


def _most_common_piece(found: list[dict]) -> dict:
    """Das häufigste Stück unter gleichnamigen, z. B. Manastein „Krit +6“ öfter als „Krit +4“."""
    def text(piece: dict) -> str:
        return str(piece.get("value") or piece.get("desc") or "")
    common = Counter(text(p) for p in found).most_common(1)[0][0]
    return next(p for p in found if text(p) == common)


def _skills(samples: list[list[dict]]) -> list[dict]:
    """Skills und Stigmen: Anteil der Spieler, die sie nutzen, und Median der Stufe bei ihnen."""
    used: dict[str, list[dict]] = {}
    for skills in samples:
        for s in skills:
            in_use = s.get("equipped") or s.get("category") not in COUNT_EQUIPPED
            if s.get("learned") and in_use and s.get("name"):
                used.setdefault(str(s["name"]), []).append(s)
    out = []
    for name, found in used.items():
        share = len(found) / len(samples)
        if share < MIN_SHARE:
            continue
        out.append({"name": name, "category": found[0].get("category"), "icon": found[0].get("icon"),
                    "level": round(median(s.get("level") or 0 for s in found)), "learned": True,
                    "equipped": found[0].get("category") in COUNT_EQUIPPED, "share": round(share, 3)})
    return sorted(out, key=lambda s: -s["share"])
