"""Auslöser der Boss-Mechaniken aus mechanics.json: ein Boss beginnt einen Skill, ein Status landet auf
dir, einem Mitspieler oder dem Boss, oder ein Skill vom Boden trifft dich."""
from __future__ import annotations

from .fight import FightEvents
from .rules import CAST_RULES, HIT_RULES, STATUS_RULES, WINDOWS
from .warning_board import WarningBoard


class MechanicWarnings:
    def __init__(self, board: WarningBoard, fight: FightEvents) -> None:
        self.board = board
        self.world = board.world
        self.window_since: dict[int, float] = {}  # Skill mit Zeitfenster → zuletzt gesehen
        fight.status_ids.update(STATUS_RULES)
        fight.hit_ids.update(HIT_RULES)
        fight.cast.connect(self.cast)
        fight.status.connect(self.status)
        fight.hit.connect(self.hit)
        board.previews.append(self.windows)

    def cast(self, caster: int, skill: int, target: int | None) -> None:
        rule = CAST_RULES.get(skill)
        if rule and self.board.trigger_cast(rule, target) and skill in WINDOWS:
            self.window_since[skill] = self.board.clock()

    def status(self, target: int, status: int) -> None:
        """Status-Effekt auf dir, einem Mitspieler, irgendeinem Spieler oder dem Boss (Rule.on)."""
        rule = STATUS_RULES[status]
        me = target == self.world.own_id
        player = target in self.world.players and not me
        fits = {"du": me, "mitspieler": player, "spieler": me or player, "boss": target in self.world.bosses}[rule.on]
        if rule.on != "boss" and self.board.foreign(target):
            return
        if self.board.enabled and fits:
            name = self.world.players.get(target, "") if player else ""
            self.board.trigger(rule, me=me and rule.on != "boss", name=name)

    def hit(self, skill: int) -> None:
        """Ein Skill vom Boden trifft dich (Pfütze, Zone): raus da. Solange die Warnung läuft, zählt jeder
        weitere Treffer als derselbe (keine Ansage im Sekundentakt)."""
        rule = HIT_RULES[skill]
        if self.board.enabled:
            self.board.trigger_unless(lambda w: w.rule == rule, rule)

    def windows(self, now: float) -> list[tuple[str, float]]:
        """Vorschau für Skills mit Zeitfenster: frühestens in … bzw. jederzeit möglich."""
        lines = []
        planned, off = self.board.planned_groups(), self.board.settings.warnings.off
        for skill, window in WINDOWS.items():
            group = CAST_RULES[skill].group
            if group in off:
                self.window_since.pop(skill, None)
            if skill not in self.window_since or group in planned:
                continue  # nie gesehen, oder die Vorhersage steht schon in der Zeile
            since = now - self.window_since[skill]
            if since < window["pause"]:
                lines.append((window["frueh"], window["pause"] - since))
            elif since < window["pause"] + window["offen"]:
                lines.append((window["moeglich"], 0.0))
            else:
                del self.window_since[skill]  # Kampf vermutlich vorbei
        return lines
