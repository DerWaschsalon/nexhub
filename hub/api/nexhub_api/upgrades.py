"""Upgrade-Plan der Armory: welche Zeilen der Seelenbindung man neu würfelt, um eine Zielnote zu erreichen.
Vorbild ist der Reiter „Upgrades“ von kisk.app. Rein, ohne Netz und Datenbank; bewertet wird in rating.py.

Je Teil sucht der Planer die höchstens MAX_REROLLS Zeilen, die im Mittel die wenigsten Versuche bis zur
Zielnote brauchen. Für eine Zeile zählen nur Ziele, die schon beim schlechtesten Wurf ihren Anteil am
Bedarf bringen; die Zielnote stimmt so auch bei Pech. Alle Teile zusammen sind nach Punkten je Versuch
sortiert, das erste ist „als Nächstes“.

Annahmen: Ein Wurf ist in seiner Spanne gleichverteilt (Mittelwert = Mitte der Spanne). Bei mehreren
Zeilen eines Teils gilt für die späteren, dass die frühere ihr wahrscheinlichstes Ziel getroffen hat.
"""
from __future__ import annotations

from dataclasses import dataclass

from .rating import ARCANA, BOUNDS, Census, letter, lines_of, names_de, points, score

DEFAULT_GOAL = "S+"
GOALS = ("S+", "BiS")
MAX_REROLLS = 3  # mehr Zeilen auf einmal neu zu würfeln, plant niemand
# Stufen der Ziele: Zugewinn im Verhältnis zum besten Ziel des Schritts
TIER_BEST = 0.9
TIER_GOOD = 0.7
FULLY_BOUND = 100.0  # Seelenbindungsrate in Prozent


@dataclass(frozen=True)
class Target:
    """Was beim Neuwürfeln einer Zeile kommen kann, mit Chance je Versuch und Zugewinn in Notenpunkten."""
    name: str
    name_de: str | None
    skill: bool
    chance: float
    gain_lo: float
    gain_hi: float

    @property
    def gain_mean(self) -> float:
        return (self.gain_lo + self.gain_hi) / 2


@dataclass(frozen=True)
class Step:
    """Eine Zeile neu würfeln, bis eines der Ziele kommt."""
    line: str
    targets: tuple[Target, ...]

    @property
    def chance(self) -> float:
        return sum(t.chance for t in self.targets)

    @property
    def tries(self) -> float:
        return 1 / self.chance

    @property
    def low(self) -> float:
        return min(t.gain_lo for t in self.targets)

    @property
    def high(self) -> float:
        return max(t.gain_hi for t in self.targets)

    @property
    def mean(self) -> float:
        return sum(t.chance * t.gain_mean for t in self.targets) / self.chance

    @property
    def skill_only(self) -> bool:
        """Nur Skills als Ziel: Der Wurf muss nicht vor dem Binden kommen."""
        return all(t.skill for t in self.targets)


@dataclass(frozen=True)
class Card:
    """Der Plan für ein Teil: Note jetzt, die Schritte und wohin sie führen."""
    slot: str
    now: float
    steps: tuple[Step, ...]

    def _after(self, gains: list[float]) -> float:
        return round(min(self.now + sum(gains), 100.0), 1)

    @property
    def low(self) -> float:
        return self._after([s.low for s in self.steps])

    @property
    def high(self) -> float:
        return self._after([s.high for s in self.steps])

    @property
    def mean(self) -> float:
        return self._after([s.mean for s in self.steps])

    @property
    def tries(self) -> float:
        return sum(s.tries for s in self.steps)

    @property
    def per_try(self) -> float:
        return (self.mean - self.now) / self.tries


def pool(census: Census, item: dict, table: dict, cls: str) -> list[dict]:
    """Was beim Neuwürfeln einer Zeile kommen kann, ohne die Zeilen, die schon drauf sind: Werte mit
    ihrer Chance von MetaBot, Skills geschätzt über den Anteil der Skill-Zeilen auf dem Platz."""
    have = {ln["name"] for ln in lines_of(item)}
    stats = [r for r in table.get("rolls") or [] if r["name"] not in have]
    skill_table = (table.get("skills") or {}).get(cls) or {}
    skills = [o for o in skill_table.get("options") or [] if o["name"] not in have]
    p_skill = census.p_skill(item["slot_name"]) if skills and stats else (1.0 if skills else 0.0)
    out = []
    total = sum(r["chance"] for r in stats) or 1.0
    for r in stats:
        out.append({"name": r["name"], "name_de": r.get("name_de"), "skill": False,
                    "chance": (1 - p_skill) * r["chance"] / total, "lo": r["min"], "hi": r["max"]})
    total = sum(o["chance"] for o in skills) or 1.0
    for o in skills:
        out.append({"name": o["name"], "name_de": o.get("name_de"), "skill": True,
                    "chance": p_skill * o["chance"] / total, "lo": 1.0, "hi": float(skill_table.get("max_level") or 1)})
    return out


class Planner:
    """Plant die Würfe für die Teile eines Charakters gegen eine Zielnote."""

    def __init__(self, census: Census, cls: str, goal: str = DEFAULT_GOAL) -> None:
        self.census, self.cls = census, cls
        self.threshold = dict(BOUNDS)[goal]

    def reached(self, value: float) -> bool:
        return value >= self.threshold

    def card(self, item: dict, table: dict) -> Card | None:
        """Der Weg mit den wenigsten Versuchen zur Zielnote; None, wenn keiner hinführt."""
        now, lines = score(self.census, item, table, self.cls)
        need = self.threshold - now
        if need <= 0:
            return None  # schon auf Zielnote
        candidates = pool(self.census, item, table, self.cls)
        best: Card | None = None
        for count in range(1, MAX_REROLLS + 1):
            steps = self._steps(item["slot_name"], lines, candidates, need / count, count)
            if steps is None:
                continue
            card = Card(item["slot_name"], now, tuple(sorted(steps, key=lambda s: (-s.chance, s.line))))
            if best is None or (card.tries, -card.mean) < (best.tries, -best.mean):
                best = card
        return best

    def _steps(self, slot: str, lines: list[dict], candidates: list[dict], need: float,
               count: int) -> list[Step] | None:
        """`count` Zeilen, die jede `need` Punkte bringen, die mit den wenigsten Versuchen zuerst. Zwei Zeilen
        können nicht dasselbe werden: Das wahrscheinlichste Ziel eines Schritts fällt für die nächsten weg."""
        chosen: list[Step] = []
        for _ in range(count):
            done = {s.line for s in chosen}
            steps = [self._step(slot, line, candidates, need) for line in lines if line["name"] not in done]
            usable = [s for s in steps if s]
            if not usable:
                return None
            step = min(usable, key=lambda s: (s.tries, -s.mean))
            chosen.append(step)
            landed = max(step.targets, key=lambda t: t.chance).name
            candidates = [c for c in candidates if c["name"] != landed]
        return chosen

    def _step(self, slot: str, line: dict, candidates: list[dict], need: float) -> Step | None:
        """Diese Zeile neu würfeln: alle Ziele, die auch beim schlechtesten Wurf `need` Punkte bringen."""
        piece = self.census.best_piece(slot)
        targets = []
        for c in candidates:
            lo = 100 * (points(self.census, slot, c["name"], c["lo"]) - line["points"]) / piece
            hi = 100 * (points(self.census, slot, c["name"], c["hi"]) - line["points"]) / piece
            if lo >= need and c["chance"] > 0:
                targets.append(Target(c["name"], c["name_de"], c["skill"], c["chance"], lo, hi))
        return Step(line["name"], tuple(targets)) if targets else None

    def bound_reaches(self, item: dict, table: dict) -> bool:
        """Erreicht das Teil die Zielnote schon, wenn die vorhandenen Zeilen voll gebunden sind?"""
        rate = (item.get("detail") or {}).get("soul_bind_rate")
        if rate is None or rate >= FULLY_BOUND:
            return False
        _, lines = score(self.census, item, table, self.cls)
        slot = item["slot_name"]
        full = sum(points(self.census, slot, ln["name"], ln["max"] or ln["value"]) for ln in lines)
        return self.reached(100 * full / self.census.best_piece(slot))


# ---- Ausgabe für die Armory ----

def _tier(gain: float, top: float) -> str:
    if gain >= TIER_BEST * top:
        return "best"
    return "good" if gain >= TIER_GOOD * top else "fine"


def _tiers(step: Step, lang: str) -> dict[str, list[dict]]:
    """Ziele eines Schritts in Stufen nach ihrem Zugewinn, jede Stufe nach Priorität (größter Gewinn zuerst)."""
    tiers: dict[str, list[dict]] = {}
    for target in sorted(step.targets, key=lambda t: -t.gain_hi):
        tier = _tier(target.gain_hi, step.high)
        name = (target.name_de or target.name) if lang == "de" else target.name
        tiers.setdefault(tier, []).append({"name": name, "gain_lo": round(target.gain_lo, 1),
                                           "gain_hi": round(target.gain_hi, 1)})
    return tiers


def _piece(item: dict, value: float | None) -> dict:
    return {"slot": item["slot_name"], "name": item.get("name"), "icon": item.get("icon"), "grade": item.get("grade"),
            "score": value, "letter": letter(value) if value is not None else None}


def _card(card: Card, item: dict, names: dict[str, str], lang: str) -> dict:
    steps = [{"line": names.get(s.line, s.line), "chance": round(100 * s.chance, 1), "tries": round(s.tries, 1),
              "skill_only": s.skill_only, "tiers": _tiers(s, lang)} for s in card.steps]
    return {**_piece(item, card.now), "steps": steps, "after": [card.low, card.high], "mean": card.mean,
            "after_letter": letter(card.low), "tries": round(card.tries, 1), "per_try": round(card.per_try, 2)}


def plan(census: dict, rolls: dict, en: dict, de: dict | None, cls: str, lang: str, goal: str = DEFAULT_GOAL) -> dict:
    """Jedes Teil eines Charakters in genau einer Gruppe: würfeln (`cards`, nach Punkten je Versuch),
    nur noch binden (`bind`), schon auf Zielnote (`done`), nicht erreichbar (`unreachable`) und Arkana."""
    c = Census(census["slots"], census.get("tops") or {})
    planner = Planner(c, cls, goal)
    shown = {i["slot_name"]: i for i in ((de if lang == "de" else en) or {}).get("equipment") or []}
    out: dict = {"goal": goal, "group": census.get("group", ""), "cards": [], "bind": [], "done": [],
                 "unreachable": [], "arcana": []}
    for item in en.get("equipment") or []:
        slot = item["slot_name"]
        if not lines_of(item) or not c.rated(slot):
            continue
        table = rolls.get(item["name"]) or {}
        own = shown.get(slot, item)
        if slot in ARCANA:
            out["arcana"].append(_piece(own, score(c, item, table, cls)[0]))
        elif not table.get("rolls"):
            out["unreachable"].append({**_piece(own, None), "reason": "no_rolls"})
        else:
            _sort_in(out, planner, item, own, table, names_de(item, shown.get(slot)) if lang == "de" else {}, lang)
    out["cards"].sort(key=lambda card: -card["per_try"])
    return out


def _sort_in(out: dict, planner: Planner, item: dict, own: dict, table: dict, names: dict[str, str], lang: str) -> None:
    """Ein würfelbares Teil in seine Gruppe: schon dort, nur binden, würfeln oder zu weit weg."""
    value, _ = score(planner.census, item, table, planner.cls)
    if planner.reached(value):
        out["done"].append(_piece(own, value))
    elif planner.bound_reaches(item, table):
        out["bind"].append(_piece(own, value))
    elif card := planner.card(item, table):
        out["cards"].append(_card(card, own, names, lang))
    else:
        out["unreachable"].append({**_piece(own, value), "reason": "too_far"})
