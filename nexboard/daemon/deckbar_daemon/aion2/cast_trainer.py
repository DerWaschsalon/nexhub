"""Lernhilfe: jeder Cast eines Bosses, zu dem es noch keine Cast-Warnung und keine Ansage gibt, erscheint
grau mit dem Namen aus den A2Tools-Daten. So sieht man, was ein neuer Boss tut."""
from __future__ import annotations

from .fight import FightEvents
from .gamedata import npc_name, skill_name
from .rules import BOSSES_WITH_CAST_RULES, CALLOUT_SKILLS, CAST_RULES, COLORS, TRAINER_GROUP, Rule, language
from .warning_board import WarningBoard

SHOW_S = 3.0  # der echte Vorlauf ist unbekannt


def trainer_rule(skill: int, npc: int, language: str) -> Rule:
    boss = npc_name(npc, language) or "Boss"
    return Rule(skill_name(skill, language), f"{boss} · {skill}", SHOW_S, COLORS["GRAU"], TRAINER_GROUP)


class CastTrainer:
    def __init__(self, board: WarningBoard, fight: FightEvents) -> None:
        self.board = board
        self.world = board.world
        fight.cast.connect(self.cast)

    def cast(self, caster: int, skill: int, target: int | None) -> None:
        npc = self.world.bosses.get(caster, 0)
        if skill in CAST_RULES or skill in CALLOUT_SKILLS or not npc or npc in BOSSES_WITH_CAST_RULES:
            return
        if self.world.dungeon:
            self.board.trigger_cast(trainer_rule(skill, npc, language()), target)
