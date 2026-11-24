"""„Jetzt staggern“ und „Boss groggy“: Bei Bossen mit Stagger-Prüfung (Berk, Bakarma, Atiel) kommt die
Ansage, sobald die Leiste brechbar wird; bricht sie, ist der Boss etwa 5 s groggy."""
from __future__ import annotations

from .rules import EVERYWHERE, STAGGER_RULES
from .stagger import StaggerTracker
from .warning_board import WarningBoard


class StaggerCalls:
    def __init__(self, board: WarningBoard, stagger: StaggerTracker) -> None:
        self.board = board
        stagger.ready.connect(self.ready)
        stagger.broken.connect(self.broken)

    def ready(self, boss: int) -> None:
        rule = STAGGER_RULES.get(self.board.world.bosses.get(boss, 0))
        if self.board.enabled and rule:
            self.board.trigger(rule)

    def broken(self, boss: int) -> None:
        if self.board.enabled:
            self.board.drop(set(STAGGER_RULES.values()))  # gebrochen: „Jetzt staggern“ ist erledigt
            self.board.add(EVERYWHERE["groggy"])
