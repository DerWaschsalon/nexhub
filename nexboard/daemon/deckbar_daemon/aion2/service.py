"""Das Radar ohne Fenster: Paketquelle, Welt, Tracker, Warnungen, Ansagen, Ton und Aufnahme.

Der NexBoard-Daemon hält einen RadarService, solange AION 2 läuft, ruft tick() mehrmals pro Sekunde auf
und zeigt state() als Widgets im Overlay (Radar, Warnungen, Karte). Die Schlüssel von state(), fight() und
map() sind die der Overlay-Widgets und der Route /api/radar/kampf.
"""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path

from ..core.packets import TcpdumpSource
from ..core.speech import Speech
from . import minimap
from .callouts import Callouts, short_texts
from .cast_trainer import CastTrainer
from .combat_aids import CombatAids
from .cubes import Cube, CubeTracker
from .field_bosses import FieldBossCalls, FieldBossTracker
from .fight import FightEvents
from .gamedata import STORE
from .maps import GameMap
from .mechanic_warnings import MechanicWarnings
from .party import PartyTracker
from .rules import CAST_RULES, EVERYWHERE, ON_YOU, PROBE_SKILL, STAGGER_RULES, STATUS_RULES, TRAINER_GROUP, tr
from .settings import reload, settings
from .spawn_points import SpawnPoints
from .stagger import StaggerTracker
from .stagger_calls import StaggerCalls
from .warning_board import LINE, SPEAK, WAVE, Warning, WarningBoard
from .world import World

SPAWN_LOG = STORE / "spawns.jsonl"  # alle erschienenen Objekte, für die Werkzeuge
MINIMAP_S = 0.2  # so oft die Minikarte lesen (ca. 5 ms je Bild), so oft wie der Stand ans Overlay geht
LOOK_VALID_S = 2.0  # so lange nach dem letzten Blick aus der Minikarte zählt die Laufrichtung nicht
DEATHS_KEPT = 200
# Teile, die der Daemon einzeln schaltet (Module AION 2 · Radar, Boss-Warnungen, Feldbosse)
CUBES, WARNINGS, FIELD_BOSSES = "radar", "warnings", "field_bosses"
PARTS = frozenset({CUBES, WARNINGS, FIELD_BOSSES})
SHOWN_WARNINGS = 3


class RadarService:
    def __init__(self, name: str = "", spawn_log: Path | None = SPAWN_LOG) -> None:
        self.settings = settings()
        self.parts: set[str] = set(PARTS)  # was davon an ist; der Daemon setzt hier seine Modulschalter ein
        if spawn_log:
            spawn_log.parent.mkdir(parents=True, exist_ok=True)
        self.source = TcpdumpSource()
        self.speech = Speech(lambda: self.settings["sprache"])
        self.world = World(name)
        self.cubes = CubeTracker(self.world, spawn_log)
        self.party = PartyTracker(self.world)
        self.field_bosses = FieldBossTracker(self.world, persist=True)
        self.fight = FightEvents(self.world)
        self.stagger = StaggerTracker(self.world, set(STAGGER_RULES))
        self.board = WarningBoard(self.world)
        self._apply_switches()
        # Reihenfolge = Reihenfolge der Warnungen zu demselben Cast: erst die eigenen Regeln, dann die Ansagen
        self.mechanics = MechanicWarnings(self.board, self.fight)
        self.trainer = CastTrainer(self.board, self.fight)
        self.callouts = Callouts(self.board, self.fight)
        self.stagger_calls = StaggerCalls(self.board, self.stagger)
        self.aids = CombatAids(self.board, self.fight, self.party)
        self.field_boss_calls = FieldBossCalls(self.field_bosses, self.speech.say)
        for part in (self.world, self.cubes, self.party, self.field_bosses, self.fight, self.stagger, self.aids):
            part.attach(self.source)
        self.spawn_points = SpawnPoints()  # jeder gesehene Cube wird als Spawnpunkt gemerkt
        self.cubes.appeared.connect(self._new_cube)
        # Tode von dir und Mitspielern durch Monster, für den Run im Hub (der Daemon liest sie aus)
        self.deaths: deque[dict] = deque(maxlen=DEATHS_KEPT)
        self.fight.death.connect(self._death)
        self._ping_due = False
        self._dungeon: str | None = None
        self._second = 0
        self._minimap_read = 0.0

    # ------------------------------------------------------------ Lebenszyklus und Knöpfe der Seite
    def start(self) -> None:
        self._apply_switches()
        self._prepare_speech()
        self.source.start()

    def stop(self) -> None:
        self.source.stop()

    def reload(self) -> None:
        """Einstellungen von der NexBoard-Seite und Modulschalter übernehmen."""
        reload()
        self._apply_switches()
        self._prepare_speech()  # falls die Sprache gewechselt hat

    def _apply_switches(self) -> None:
        self.board.enabled = self.settings["warn_an"] and WARNINGS in self.parts

    def _prepare_speech(self) -> None:
        """Alle festen Ansagen vorab erzeugen, damit sie im Kampf sofort kommen."""
        rules = [*CAST_RULES.values(), *STATUS_RULES.values(), EVERYWHERE["groggy"], EVERYWHERE["hp"]]
        texts = {tr(title) for rule in rules for title in rule.all_titles()}
        texts |= {tr(rule.title) + tr(ON_YOU) for rule in rules if rule.on_you}
        self.speech.prepare(texts | set(short_texts(self.settings["sprache"])))

    def test_callout(self, key: str) -> None:
        """▶ einer Boss-Ansage auf der NexBoard-Seite."""
        self.callouts.test(key)

    def test_warning(self) -> None:
        self.mechanics.cast(0, PROBE_SKILL, self.world.own_id)

    def test_ping(self) -> None:
        self.speech.ping()

    def start_recording(self) -> None:
        self.source.start_recording(self.world.dungeon or "dungeon")

    def stop_recording(self) -> None:
        self.source.stop_recording()

    @property
    def recording(self) -> bool:
        return self.source.recording

    @property
    def error(self) -> str | None:
        """Warum der Mitschnitt nicht läuft (etwa tcpdump ohne Rechte), sonst None."""
        return self.source.error

    # ------------------------------------------------------------ Ereignisse aus dem Mitschnitt-Thread
    def _new_cube(self, cube: Cube) -> None:
        """Nur merken, der Ton kommt im nächsten Takt."""
        self.spawn_points.add(cube.x, cube.y, cube.z, cube.object_id)
        self._ping_due = True

    def _death(self, victim: int, skill: int, killer_name: str) -> None:
        """Tod merken mit Skill und der Warnung, die das Radar gerade zeigte. PvP (Täter ist ein Spieler)
        und tote Monster zählen nicht."""
        name = self.world.players.get(victim) or (self.world.character_name if victim == self.world.own_id else "")
        if killer_name or not name:
            return
        now = self.board.clock()
        warning = self.board.latest(now)
        self.deaths.append({"t_ms": int(now * 1000), "name": name, "skill": skill,
                            "warning": tr(warning.rule.title) if warning else None,
                            "lead_ms": int((now - warning.start) * 1000) if warning else None})

    # ------------------------------------------------------------ Takt
    def tick(self) -> None:
        """Was im Takt des Daemons passiert: Aufnahme je Dungeon, Feldboss-Ansagen, Töne, Blickrichtung."""
        dungeon = self.world.dungeon
        if dungeon != self._dungeon:  # Dungeon betreten oder verlassen
            self._dungeon = dungeon
            if not dungeon:
                self.stop_recording()
            elif self.settings["aufnahme_auto"]:
                self.source.start_recording(dungeon)  # Lernmodus: jeder Lauf eine eigene Datei
        if int(time.time()) != self._second:
            self._second = int(time.time())
            if FIELD_BOSSES in self.parts:
                self.field_boss_calls.tick()
        if self._ping_due:
            self._ping_due = False
            if self.settings["ton"] and CUBES in self.parts:
                self.speech.ping()
        self._read_minimap()
        self.callouts.tick()  # abgelaufene Phasen: „Wieder angreifen“
        self.board.snapshot()  # holt fällige Vorhersagen nach vorn, auch ohne Overlay
        while self.board.sounds:
            kind, text = self.board.sounds.pop(0)
            if kind in (SPEAK, LINE):
                self.speech.say(text, important=kind == SPEAK)  # eine Boss-Zeile darf abgebrochen werden
            elif kind == WAVE:
                self.speech.beep()  # kurzer Ton je Welle (Boss-Ansagen)
            else:
                self.speech.alarm()

    def _read_minimap(self) -> None:
        """Blickrichtung aus der Minikarte (Einstellung minikarte = [x, y, Breite, Höhe]), fünfmal pro
        Sekunde. Sie ersetzt die Laufrichtung aus zwei Positionen, die beim normalen Laufen fehlt."""
        area = self.settings["minikarte"]
        if len(area) != 4 or time.time() - self._minimap_read < MINIMAP_S:
            return
        self._minimap_read = time.time()
        image = minimap.grab(area)
        degrees = minimap.view_direction(image) if image is not None else None
        if degrees is not None:
            self.world.heading = minimap.heading(degrees)
            self.world.look_until = time.time() + LOOK_VALID_S

    # ------------------------------------------------------------ für Overlay und andere Programme
    def fight_state(self) -> dict:
        """Für andere Programme auf diesem PC (GET /api/radar/kampf): Boss groggy und die laufenden Warnungen
        mit Gruppe (Schalter auf der NexBoard-Seite), Titel, ob sie dich trifft, und Restzeit. Abgeschaltete
        Warnungen kommen auch hier nicht vor, die Lernhilfe nie."""
        now = self.board.clock()
        return {"groggy": self.stagger.groggy(),
                "warnungen": [{"gruppe": w.rule.group, "titel": w.title(), "ich": w.me, "rest": round(w.rest(now), 2)}
                              for w in self.board.snapshot() if w.rule.group != TRAINER_GROUP]}

    def state(self) -> dict:
        """Alles, was die Widgets zeichnen. Weltkoordinaten in cm, Zeiten in Sekunden."""
        world, now = self.world, self.board.clock()
        return {
            "position": world.position,
            "position_alter": world.position_age(),
            "kurs": world.heading,
            "cubes": [{"x": c.x, "y": c.y, "z": c.z, "alter": time.time() - c.since, "oeffner": c.opener}
                      for c in self.cubes.current()],
            "gruppe": [{"name": name, "x": x, "y": y} for name, x, y, *_ in self.party.visible()],
            "feldbosse": [b["pos"][:2] for b in self.field_bosses.alive_here()],
            "status": self._status(),
            "warnungen": [self._warning(w, now) for w in self.board.snapshot()[-SHOWN_WARNINGS:]],
            "vorschau": [[tr(text), rest] for text, rest in self.board.preview()],
            "jetzt_text": tr("JETZT"),
            "karte": self.settings["karte_name"] or "",
            "zone": world.zone,  # Zonen-ID = Karten-ID der Weltkarten, danach wählt das Widget das Kartenbild
            "karte_offen": self.field_bosses.map_open and self.settings["bei_karte_ausblenden"],  # Overlay ausblenden
            "punkte": len(self.spawn_points.points),  # ändert sich die Zahl, lädt die Karte die Punkte neu
            "einstellungen": {k: self.settings[k]
                              for k in ("reichweite", "drehung", "spiegeln", "karte_folgen", "kurs_oben")},
        }

    @staticmethod
    def _warning(w: Warning, now: float) -> dict:
        return {"titel": w.title(), "hinweis": tr(w.rule.hint_you if w.me else w.rule.hint),
                "rest": w.rest(now), "vorlauf": w.rule.lead, "farbe": w.rule.color,
                "lernhilfe": w.rule.group == TRAINER_GROUP}  # Lernhilfe: echter Vorlauf unbekannt, keine Sekunden

    def _status(self) -> str:
        world = self.world
        if self.error:
            return f"Fehler: {self.error}"
        if not self.source.packets:
            return "warte auf Spieldaten …"
        if world.own_id is None:
            return "suche eigenen Charakter …"
        age = world.position_age()
        position = "keine Position" if age is None else ("Position aktuell" if age < 5 else f"Position vor {age:.0f} s")
        text = f"ID {world.own_id} ({'sicher' if world.own_id_sure else 'geschätzt'}) · {position}"
        if world.dungeon:
            rest = int(world.dungeon_ends_at - time.time()) if world.dungeon_ends_at else 0
            limit = f" {rest // 60}:{rest % 60:02}" if rest > 0 else ""
            text = f"{world.dungeon}{limit} · {text}"
        if self.cubes.keys_used:
            text += f" · {self.cubes.keys_used} Cube-Schlüssel benutzt"
        return ("● REC · " if self.recording else "") + text

    def map(self) -> dict:
        """Die eingestellte Karte (sonst die einzige vorhandene) mit Eichung, Fundorten, Teleportern und den
        gesehenen Spawnpunkten."""
        maps = GameMap.all()
        name = self.settings["karte_name"] or (maps[0].name if len(maps) == 1 else "")
        game_map = next((m for m in maps if m.name == name), None)
        if not game_map:
            return {"name": ""}
        return {"name": game_map.name, "m": game_map.calibration.m,
                "fundorte": game_map.listing("fundorte.json"), "teleporter": game_map.listing("teleporter.json"),
                "symbol": game_map.symbol.exists(),
                "punkte": [[p["x"], p["y"], p["quelle"]] for p in self.spawn_points.all()]}
