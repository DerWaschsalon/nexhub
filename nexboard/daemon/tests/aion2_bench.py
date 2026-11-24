"""Prüfstand für die AION-2-Teile: Welt, Tracker, Warn-Anzeige und Auslöser verdrahtet wie im RadarService,
aber ohne Mitschnitt und Ton. Die Uhr steht, bis der Test sie stellt."""
from __future__ import annotations

import struct

from deckbar_daemon.aion2.callouts import Callouts
from deckbar_daemon.aion2.cast_trainer import CastTrainer
from deckbar_daemon.aion2.combat_aids import CombatAids
from deckbar_daemon.aion2.cubes import CubeTracker
from deckbar_daemon.aion2.field_bosses import FieldBossTracker
from deckbar_daemon.aion2.fight import FightEvents
from deckbar_daemon.aion2.mechanic_warnings import MechanicWarnings
from deckbar_daemon.aion2.party import PartyTracker
from deckbar_daemon.aion2.rules import STAGGER_RULES
from deckbar_daemon.aion2.stagger import StaggerTracker
from deckbar_daemon.aion2.stagger_calls import StaggerCalls
from deckbar_daemon.aion2.warning_board import WarningBoard
from deckbar_daemon.aion2.world import World
from deckbar_daemon.core.packets import PacketSource

ME = 5


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def frame(opcode: int, payload: bytes) -> bytes:
    content = struct.pack("<H", opcode) + payload
    return varint(len(content) + 4) + content


def xyz(x: float, y: float, z: float = 0.0) -> bytes:
    return struct.pack("<fff", x, y, z)


class Bench:
    def __init__(self, own_id: int | None = ME, callouts: dict | None = None, **settings) -> None:
        self.now = 100.0
        self.source = PacketSource()
        self.world = World()
        self.world.own_id = own_id
        self.cubes = CubeTracker(self.world)
        self.party = PartyTracker(self.world)
        self.field_bosses = FieldBossTracker(self.world)  # speichert nichts
        self.fight = FightEvents(self.world)
        self.stagger = StaggerTracker(self.world, set(STAGGER_RULES))
        self.board = WarningBoard(self.world, clock=lambda: self.now)
        self.board.enabled = True
        # Standard der Tests, nicht die eigenen Einstellungen
        self.board.settings = {"meldung_aus": [], "warnton": {}, "sprache": "de", "ansage_stil": "beides",
                               "wellen_ton": True, "eigene_worte": {}, "ruf_aus": [], **settings}
        self.mechanics = MechanicWarnings(self.board, self.fight)
        self.trainer = CastTrainer(self.board, self.fight)
        self.callouts = Callouts(self.board, self.fight, callouts) if callouts else None
        self.stagger_calls = StaggerCalls(self.board, self.stagger)
        self.aids = CombatAids(self.board, self.fight, self.party)
        for part in (self.world, self.cubes, self.party, self.field_bosses, self.fight, self.stagger, self.aids):
            part.attach(self.source)

    @property
    def settings(self) -> dict:
        return self.board.settings

    @property
    def sounds(self) -> list[tuple[str, str]]:
        return self.board.sounds

    def packet(self, opcode: int, payload: bytes) -> None:
        self.source.publish(opcode, payload)

    def cast(self, caster: int, skill: int, target: int | None) -> None:
        self.fight.cast.emit(caster, skill, target)

    def status(self, target: int, status: int) -> None:
        self.fight.status.emit(target, status)

    def titles(self) -> list[str]:
        """Titel der laufenden Warnungen ohne Ziel, sortiert."""
        return sorted(w.rule.title for w in self.board.snapshot())

    def shown(self) -> list[tuple[str, str]]:
        """(Titel mit Ziel, Hinweis) der laufenden Warnungen, wie das Widget sie zeigt."""
        return [(w.title(), w.rule.hint_you if w.me else w.rule.hint) for w in self.board.snapshot()]

    def groups(self) -> list[str]:
        return [w.rule.group for w in self.board.snapshot()]
