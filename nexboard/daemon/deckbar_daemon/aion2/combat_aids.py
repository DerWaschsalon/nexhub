"""Kampfhilfen in jedem Dungeon: Fläche unter dir, wenig eigene HP, Mitspieler mit wenig LP und die
Berserker-Zeit des Bosses in der Vorschauzeile."""
from __future__ import annotations

import math
from dataclasses import replace

from ..core.packets import PacketSource
from ..core.packets.messages import FightState
from .fight import FightEvents
from .party import PartyTracker
from .rules import EVERYWHERE
from .warning_board import WarningBoard

# Eigene HP unter die Hälfte gefallen (nur im Dungeon); erneut erst nach über 65 %. Bei Zikel kamen fast
# alle Tode als zweiter Treffer wenige Sekunden nach dem ersten.
HP_LOW, HP_AGAIN = 0.5, 0.65
PARTY_LOW, PARTY_AGAIN = 0.25, 0.5  # Mitspieler: melden unter 25 % LP, erneut erst nach über 50 %
AREA_GROUP = "flaeche"


class CombatAids:
    def __init__(self, board: WarningBoard, fight: FightEvents, party: PartyTracker) -> None:
        self.board = board
        self.world = board.world
        self.hp_max = 0
        self.hp_low = False
        self._low_members: set[int] = set()  # Mitspieler, die schon als „wenig LP“ gemeldet sind
        self.berserk: dict[int, float] = {}  # Boss-Entity → Berserker-Zeit (Sekunden seit 1970)
        self.world.own_hp.connect(self.own_hp)
        fight.area.connect(self.area)
        party.hp.connect(self.party_hp)
        board.previews.append(self.berserk_preview)

    def attach(self, source: PacketSource) -> None:
        source.on(FightState, self._on_fight_state)

    def own_hp(self, value: int) -> None:
        """Einmal warnen, wenn die eigenen HP unter die Hälfte fallen."""
        self.hp_max = max(self.hp_max, value)
        if value == 0 or value > self.hp_max * HP_AGAIN:
            self.hp_low = False
        elif value < self.hp_max * HP_LOW and not self.hp_low:
            self.hp_low = True
            if self.board.enabled and self.world.dungeon:
                self.board.add(EVERYWHERE["hp"])

    def area(self, skill: int, x: float, y: float, seconds: float) -> None:
        """Ein Monster markiert eine Fläche am Boden. Liegt ihr Mittelpunkt nah an dir, warnen, mit Countdown
        bis zum Einschlag. Mehrere Markierungen auf einmal (Nazmun: sechs) sind eine Warnung."""
        position = self.world.position
        if not self.board.enabled or position is None or seconds <= 0:
            return
        if math.hypot(x - position[0], y - position[1]) > self.board.settings.warnings.area_m * 100:
            return  # Welt in cm
        rule = replace(EVERYWHERE[AREA_GROUP], lead=seconds)
        self.board.trigger_unless(lambda w: w.rule.group == AREA_GROUP, rule, me=True)

    def party_hp(self, entity: int, share: float) -> None:
        """Mitspieler unter 25 % LP einmal melden, erst nach Erholung über 50 % wieder."""
        if share > PARTY_AGAIN:
            self._low_members.discard(entity)
            return
        if not self.board.enabled or share >= PARTY_LOW or entity in self._low_members:
            return
        self._low_members.add(entity)
        if not self.board.settings.warnings.only_me:  # sonst: betrifft einen anderen
            self.board.add(EVERYWHERE["gruppe_lp"], target=self.world.players.get(entity, ""))

    def _on_fight_state(self, m: FightState) -> None:
        """Berserker-Zeit eines Bosses merken; Kampf vorbei = weg."""
        if m.entity not in self.world.bosses:
            return
        if not m.active:
            self.berserk.pop(m.entity, None)
        elif m.berserk_at is not None:
            self.berserk[m.entity] = m.berserk_at

    def berserk_preview(self, now: float) -> list[tuple[str, float]]:
        return [("Berserker", end - now) for end in list(self.berserk.values()) if end > now]
