"""Dungeon-Runs als Daten: Kämpfe aus der History lesen, Namen auflösen, Kämpfe zu Runs gruppieren.

Ohne Netz und ohne Bild: runs.py beobachtet die History und postet, run_image.py zeichnet.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from nexproto.classes import JOB_CLASSES
from nexproto.dungeons import EXTRA_DUNGEONS

from .dps import a2tools_settings_path

log = logging.getLogger(__name__)

KILL_RATIO = 0.97
# Endbosse je Dungeon (englischer Name wie in i18n/npcs/en.json, gilt für alle Schwierigkeiten
# und Stufen). Recherche 11.10.2026: metabot.gg, games.gg, gamesfuze.com, thegameswiki.com, u4n.com.
# Nicht gelistet, weil unklar: Mirror of Scarlet Desire, Consumed Deus Research Base – dort
# greift weiter das Lernen über die HP.
END_BOSSES = {
    "Ultimate Berk",  # Krao Cave
    "Divine Auldor",  # Urugugu Canyon
    "Kromede's Desire",  # Fire Temple
    "Transcendent Bakarma",  # Draupnir
    "Decaying Durvati",  # Dying Dramata's Nest (nicht „… (Specimen)“)
    "Atiel",  # Deus Research Base (erscheint nach Gelcos + Nazmun)
    "Talisra of the Void",  # Shattered Arkanis (keine Quelle; im Spiel zuletzt, doppelte HP)
    "Vakron",  # Vakron Sky Island
    "Ferocious Horn Nuakum",  # Ferocious Horn Den
    "Afflicted Bakarma",  # Cradle of Nihility
    "Nathara",  # Hall of Illusion
    "Awakened Alturadon",  # Azure Breath Island
    "Basilus the False",  # Citadel of the Fallen Daeva
    "Submerged Emon",  # Submerged Life Temple
    "Gargaum",  # Abyssal Horn Den
}


def mask(name: str) -> str:
    """So maskiert das A2Tools-Meter Namen in der History: 2 Zeichen vorn, 1 hinten, höchstens 4 Sterne
    („Ironwhisper“ → „Ir****r“); kurze Namen: „Kan“ → „K*n“, „Xu“ → „X*“."""
    if "*" in name or len(name) < 2:
        return name
    if len(name) == 2:
        return name[0] + "*"
    head = 1 if len(name) == 3 else 2
    return name[:head] + "*" * min(4, len(name) - head - 1) + name[-1]


def char_key(name: str, cls: str | None) -> str:
    return f"{mask(name)}|{cls or ''}"


# ---------------------------------------------------------------- Daten des Meters
def a2tools_dir() -> Path:
    return a2tools_settings_path().parent


REPO_DATA = Path(__file__).resolve().parents[2] / "capture" / "a2tools" / "src" / "data"


def a2tools_data_dir() -> Path:
    """Übersetzungen (Boss-, Dungeonnamen): installiertes Meter, sonst das Submodul im Repo."""
    if env := os.environ.get("DECKBAR_A2TOOLS_DATA"):
        return Path(env)
    installed = Path("/usr/lib/A2Tools DPS Meter/data")
    return installed if installed.is_dir() or not REPO_DATA.is_dir() else REPO_DATA


@cache
def _i18n(name: str) -> dict:
    try:
        data = json.loads((a2tools_data_dir() / "i18n" / name).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def boss_name(mob: int, fallback: str) -> str:
    return (_i18n("npcs/de.json").get(str(mob)) or {}).get("name") or fallback or f"Boss {mob}"


def is_end_boss(mob: int) -> bool:
    return (_i18n("npcs/en.json").get(str(mob)) or {}).get("name") in END_BOSSES


def dungeon_name(dungeon: int) -> str:
    entry = _i18n("dungeons/en.json").get(str(dungeon)) or {}
    name = entry.get("name") or EXTRA_DUNGEONS.get(dungeon) or f"Dungeon {dungeon}"
    diff = {"normal": "Normal", "exploration": "Erkundung", "hard": "Schwer"}.get(entry.get("difficulty"))
    return f"{name} ({diff})" if diff else name


def dungeon_parts_en(dungeon: int) -> tuple[str, str | None]:
    """Englischer Name und Schwierigkeit („Hard“) – sprachunabhängig, für Weitergaben an andere
    Programme (report.py, der Bot), damit Meldungen verschiedener Spieler zusammenpassen."""
    entry = _i18n("dungeons/en.json").get(str(dungeon)) or {}
    diff = {"normal": "Normal", "exploration": "Exploration", "hard": "Hard"}.get(entry.get("difficulty"))
    return entry.get("name") or EXTRA_DUNGEONS.get(dungeon) or f"Dungeon {dungeon}", diff


def boss_name_en(mob: int, fallback: str = "") -> str:
    return (_i18n("npcs/en.json").get(str(mob)) or {}).get("name") or fallback or f"Boss {mob}"


@dataclass
class Player:
    name: str
    cls: str | None
    dmg: int
    you: bool = False
    cp: int = 0  # Kampfkraft (combatPower im Meter)
    gear: int = 0  # Ausrüstungswert/Itemlevel (gearScore im Meter)

    @property
    def key(self) -> str:
        return char_key(self.name, self.cls)


@dataclass
class Fight:
    id: str
    dungeon: int
    mob: int
    boss: str
    start_ms: int
    duration_ms: int
    max_hp: int
    dealt: int  # Schaden am Boss insgesamt
    killed: bool
    players: list[Player]

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


def parse_fight(data: dict, you_actor: int | None = None) -> Fight | None:
    """History-Eintrag → Fight; None für Übungspuppen und Kämpfe außerhalb von Dungeons."""
    try:
        dungeon = int(data.get("dungeonId") or 0)
        mob = int(data.get("mobCode") or 0)
        details = data.get("details") or {}
        if not dungeon or data.get("isTrain") or (_i18n("npcs/de.json").get(str(mob)) or {}).get("isDummy"):
            return None
        dmg: dict[int, int] = {}
        for s in details.get("skills") or []:
            dmg[s["actorId"]] = dmg.get(s["actorId"], 0) + max(0, int(s.get("dmg") or 0))
        players = [
            Player(str(a.get("nickname") or "?")[:24], JOB_CLASSES.get(a.get("jobId")), dmg.get(a["actorId"], 0),
                   a["actorId"] == you_actor, _int(a.get("combatPower")), _int(a.get("gearScore")))
            for a in data.get("actors") or [] if dmg.get(a["actorId"])
        ]
        max_hp = int(details.get("maxHp") or 0)
        total = int(details.get("totalTargetDamage") or data.get("totalDamage") or 0)
        return Fight(
            id=str(data["id"]), dungeon=dungeon, mob=mob, boss=boss_name(mob, str(data.get("bossName") or "")),
            start_ms=int(data["startTimeMs"]), duration_ms=max(0, int(data.get("durationMs") or 0)),
            max_hp=max_hp, dealt=total, killed=max_hp > 0 and total >= max_hp * KILL_RATIO, players=players,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _int(v) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def load_fight(path: Path) -> Fight | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    you = None
    try:  # wer das Meter laufen hat, steht in der zugehörigen slices-Datei
        you = json.loads((path.parent.parent / "slices" / path.name).read_text()).get("uploaderActorId")
    except (OSError, ValueError, AttributeError):
        pass
    return parse_fight(data, you) if isinstance(data, dict) else None


# ---------------------------------------------------------------- Runs
@dataclass
class Boss:
    mob: int
    name: str
    duration_ms: int = 0
    attempts: int = 0
    killed: bool = False
    max_hp: int = 0
    best: float = 0.0  # größter Anteil der HP, der in einem Kampf weg war (0–1)
    players: dict[str, Player] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(p.dmg for p in self.players.values())


@dataclass
class Run:
    dungeon: int
    fights: list[Fight] = field(default_factory=list)
    complete: bool = False  # Endboss besiegt
    names: dict[str, str] = field(default_factory=dict)  # echte Namen zu maskierten (siehe rename)
    bild: bytes | None = field(default=None, repr=False, compare=False)  # Cache für run_image

    @property
    def start_ms(self) -> int:
        return self.fights[0].start_ms

    @property
    def end_ms(self) -> int:
        return max(f.end_ms for f in self.fights)

    @property
    def name(self) -> str:
        return dungeon_name(self.dungeon)

    def rename(self, names: dict[str, str]) -> None:
        """Maskierte Namen beim Auswerten durch bekannte echte ersetzen (die Kämpfe bleiben unverändert).
        Nur Spieler dieses Runs: alle je gesehenen Namen sprengen die Grenze von 500 im NexLog."""
        keys = {p.key for f in self.fights for p in f.players}
        names = {k: v for k, v in names.items() if k in keys}
        if names != self.names:
            self.bild = None  # andere Namen, anderes Bild
        self.names = names

    def _display(self, p: Player) -> str:
        return self.names.get(p.key, p.name) if "*" in p.name else p.name

    def bosses(self) -> list[Boss]:
        """Kämpfe pro Boss zusammengefasst (mehrere Versuche oder vom Meter geteilte Kämpfe)."""
        out: dict[int, Boss] = {}
        for f in self.fights:
            b = out.setdefault(f.mob, Boss(f.mob, f.boss))
            b.duration_ms += f.duration_ms
            b.attempts += 1
            b.killed |= f.killed
            b.max_hp = max(b.max_hp, f.max_hp)
            if f.max_hp:
                b.best = max(b.best, min(1.0, f.dealt / f.max_hp))
            for p in f.players:
                q = b.players.setdefault(p.key, Player(self._display(p), p.cls, 0, p.you))
                q.dmg += p.dmg
                q.you |= p.you
                q.cp, q.gear = max(q.cp, p.cp), max(q.gear, p.gear)
                if "*" in q.name and "*" not in p.name:
                    q.name = p.name
        return list(out.values())

    def total(self) -> Boss:
        t = Boss(0, "Gesamt")
        for b in self.bosses():
            t.duration_ms += b.duration_ms
            for key, p in b.players.items():
                q = t.players.setdefault(key, Player(p.name, p.cls, 0, p.you))
                q.dmg += p.dmg
                q.you |= p.you
                q.cp, q.gear = max(q.cp, p.cp), max(q.gear, p.gear)
        return t

    @property
    def kills(self) -> int:
        return sum(b.killed for b in self.bosses())


class RunTracker:
    """Setzt Kämpfe zu Runs zusammen. `known` = maximale HP je Boss aus abgeschlossenen Runs,
    `listed` = Dungeons, deren Endboss in `END_BOSSES` steht (dort zählt nur die Liste)."""

    def __init__(self, idle_ms: int) -> None:
        self.idle_ms = idle_ms
        self.known: dict[int, dict[int, int]] = {}
        self.listed: set[int] = set()
        self.run: Run | None = None

    def learn(self, f: Fight) -> None:
        mobs = self.known.setdefault(f.dungeon, {})
        mobs[f.mob] = max(mobs.get(f.mob, 0), f.max_hp)
        if is_end_boss(f.mob):
            self.listed.add(f.dungeon)

    def end_boss(self, dungeon: int) -> int | None:
        mobs = self.known.get(dungeon)
        return max(mobs, key=mobs.__getitem__) if mobs else None

    def _is_end(self, f: Fight) -> bool:
        if not f.killed:
            return False
        if is_end_boss(f.mob):
            return True
        return f.dungeon not in self.listed and f.mob == self.end_boss(f.dungeon)

    def _close(self, complete: bool) -> Run:
        run, self.run = self.run, None
        assert run is not None
        run.complete = complete
        for f in run.fights:
            self.learn(f)
        return run

    def add(self, f: Fight) -> list[Run]:
        """Neuer Kampf oder neuer Stand eines Kampfs (gleiche id) → ggf. beendete Runs."""
        if self.run:
            for i, old in enumerate(self.run.fights):
                if old.id == f.id:
                    self.run.fights[i] = f
                    if self._is_end(f):
                        return [self._close(True)]
                    return []
        closed = []
        if self.run and (f.dungeon != self.run.dungeon or f.start_ms - self.run.end_ms > self.idle_ms
                         or self._again(f)):
            closed.append(self._close(False))
        if self.run is None:
            self.run = Run(f.dungeon)
        self.run.fights.append(f)
        if self._is_end(f):
            closed.append(self._close(True))
        return closed

    def _again(self, f: Fight) -> bool:
        """Schon besiegter Boss taucht wieder auf (nicht bloß der gleiche Kampf weiter) → nächster Run."""
        assert self.run is not None
        last = self.run.fights[-1]
        return last.mob != f.mob and any(x.mob == f.mob and x.killed for x in self.run.fights)

    def check_idle(self, now_ms: int) -> list[Run]:
        if self.run and now_ms - self.run.end_ms > self.idle_ms:
            return [self._close(False)]
        return []
