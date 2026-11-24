"""Regeln der Boss-Warnungen aus data/mechanics.json (Aufbau dort unter _felder), die Schalter der Seite
„Warnungen“ und die englischen Texte. Hier steht nur, was eine Regel ist; ausgelöst wird sie in
mechanic_warnings.py, stagger_calls.py, combat_aids.py und cast_trainer.py, gezeigt in warning_board.py."""
from __future__ import annotations

from dataclasses import dataclass

from .gamedata import BOSSES, CALLOUTS, MECHANICS
from .settings import settings

Color = tuple[int, int, int]
COLORS: dict[str, Color] = {"GRUEN": (0, 230, 118), "LILA": (186, 85, 255), "ORANGE": (255, 120, 0),
                            "GELB": (255, 210, 0), "BLAU": (80, 170, 255), "ROT": (255, 70, 70),
                            "GRAU": (160, 170, 190)}
HINT_YOU = "Weg von der Gruppe!"
TRAINER_GROUP = "casts"  # Gruppe der grauen Lernhilfe (jeder Boss-Cast ohne eigene Regel)
TRAINER_SWITCH = "Alle Boss-Casts zeigen (Lernhilfe, Bosse ohne Warnungen)"
ON_YOU, TO, YOU_SUFFIX = " auf dir", " auf ", "  –  DU!"


@dataclass(frozen=True)
class Rule:
    title: str
    hint: str
    lead: float  # Sekunden bis zum Einschlag bzw. so lange zeigen
    color: Color
    group: str  # Schalter der Seite; eine neue Warnung ersetzt ältere derselben Gruppe
    together: tuple["Rule", ...] = ()  # Vorhersagen, die sofort mit erscheinen
    plan: tuple[tuple[float, "Rule"], ...] = ()  # (Sekunden später, Vorhersage)
    on_you: bool = False  # zielt der Cast auf dich, steht „DU!“ im Titel
    on: str = "du"  # Status-Effekt zählt auf: du, mitspieler, spieler, boss
    hint_you: str = HINT_YOU  # Hinweis, wenn es dich trifft
    # Was gesprochen wird: None = der Titel; sonst diese Texte, der erste wichtig, die weiteren (Zeile des
    # Bosses) dürfen von der nächsten Warnung abgebrochen werden; () = nichts
    speak: tuple[str, ...] | None = None

    def all_titles(self) -> list[str]:
        return [self.title, *(r.title for r in self.together), *(r.title for _, r in self.plan)]


def side_rule(d: dict, main: dict) -> Rule:
    """Vorhersage zu einer Mechanik; ohne eigene Farbe oder Gruppe gilt die der Mechanik."""
    return Rule(d["titel"], d["hinweis"], d["sekunden"], COLORS[d.get("farbe", main["farbe"])],
                d.get("gruppe", main["gruppe"]))


def mechanic_rule(m: dict) -> Rule:
    """Eine Regel aus mechanics.json. „danach“ wird als geplante Folge-Warnung derselben Gruppe eingehängt
    und ersetzt die erste, wenn sie abgelaufen ist."""
    plan = tuple((p["nach"], side_rule(p, m)) for p in m.get("plan", ()))
    if m.get("danach"):
        plan += ((m["sekunden"], side_rule({"titel": m["titel"], **m["danach"]}, m)),)
    when = m.get("wann", {})
    return Rule(m["titel"], m["hinweis"], m["sekunden"], COLORS[m["farbe"]], m["gruppe"],
                together=tuple(side_rule(z, m) for z in m.get("zugleich", ())), plan=plan,
                on=when.get("auf", "du"), on_you=when.get("auf_dir", False), hint_you=m.get("hinweis_ich", HINT_YOU))


_MECHANICS: list[dict] = MECHANICS["mechaniken"]
CAST_RULES: dict[int, Rule] = {}  # Skill, den ein Boss beginnt → Regel
STATUS_RULES: dict[int, Rule] = {}  # Status-Effekt → Regel
HIT_RULES: dict[int, Rule] = {}  # Skill, der dich trifft (Pfützen, Zonen) → Regel
STAGGER_RULES: dict[int, Rule] = {}  # Boss-NPC mit Stagger-Prüfung → „Jetzt staggern“
WINDOWS: dict[int, dict] = {}  # Skill → Zeitfenster, in dem er frühestens wiederkommt
for _m in _MECHANICS:
    _rule, _when = mechanic_rule(_m), _m["wann"]
    if _when["art"] == "cast":
        CAST_RULES.update({skill: _rule for skill in _when["skills"]})
        if "fenster" in _m:
            WINDOWS.update({skill: _m["fenster"] for skill in _when["skills"]})
    elif _when["art"] == "effekt":
        STATUS_RULES[_when["id"]] = _rule
    elif _when["art"] == "treffer":
        HIT_RULES.update({skill: _rule for skill in _when["skills"]})
    elif _when["art"] == "stagger":
        STAGGER_RULES.update({npc: _rule for npc in _m["bosse"]})
# Warnungen jedes Dungeons: Boss groggy, eigene HP, Mitspieler mit wenig LP, Fläche unter dir
EVERYWHERE: dict[str, Rule] = {a["gruppe"]: mechanic_rule(a) for a in MECHANICS["alle"]}
PROBE_SKILL: int = MECHANICS["probe"]  # Skill des Knopfs „Warnung testen“
# Skills mit Boss-Ansage: dazu keine graue Lernhilfe mehr
CALLOUT_SKILLS = {r["id"] for r in CALLOUTS["rufe"] if r["art"] != "effekt"}
# Die Lernhilfe gilt für Bosse, zu denen es noch keine Cast-Warnung gibt. Die Feuertempel-Regeln stehen
# ohne Boss-IDs, ihre Bosse haben alle Cast-Warnungen.
BOSSES_WITH_CAST_RULES = {npc for m in _MECHANICS if m["wann"]["art"] == "cast" for npc in m["bosse"]} | {
    npc for npc, dungeon in BOSSES.items() if dungeon == "Feuertempel"}


def callout_group(slug: str) -> str:
    """Schalter der Boss-Ansagen: einer je Boss."""
    return "ansage_" + slug.replace("-", "_")


def switches() -> dict:
    """Schalter der Seite „Warnungen“: Gruppe → Name, je Dungeon in der Reihenfolge der Daten, dann die
    Lernhilfe und je Boss mit Ansagen einer; dazu die Warnungen aller Dungeons."""
    dungeons: dict[str, dict[str, str]] = {d["name"]: {} for d in MECHANICS["dungeons"]}
    for m in _MECHANICS:
        dungeons[m["dungeon"]].setdefault(m["gruppe"], m["meldung"])
    for d in MECHANICS["dungeons"]:
        if d.get("lernhilfe"):
            dungeons[d["name"]][TRAINER_GROUP] = TRAINER_SWITCH
    for slug in sorted({r["boss"] for r in CALLOUTS["rufe"]}):
        boss = CALLOUTS["bosse"][slug]
        dungeons.setdefault(boss["dungeon"], {})[callout_group(slug)] = f"{boss['name']['de']}: Ansagen"
    return {"alle": {a["gruppe"]: a["meldung"] for a in MECHANICS["alle"]}, "dungeons": dungeons}


SWITCHES = switches()
DUNGEON_GROUPS: dict[str, dict[str, str]] = SWITCHES["dungeons"]  # Dungeon → {Gruppe: Name}

# Englische Texte (Deutsch ist der Grundtext). Fehlt ein Eintrag, bleibt der deutsche Text.
ENGLISH: dict[str, str] = dict(MECHANICS["en"])
for _m in (*MECHANICS["alle"], *_MECHANICS):
    ENGLISH.update(_m["en"])


def tr(text: str) -> str:
    """Text in der eingestellten Sprache."""
    return ENGLISH.get(text, text) if settings()["sprache"] == "en" else text
