"""Die Warn-Anzeige: hält die laufenden Warnungen und geplanten Vorhersagen aller Auslöser und was davon
gesprochen oder gepiept wird. Auslöser rufen `trigger()`; das Widget „Boss-Warnungen“ zeigt `snapshot()`."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .rules import DUNGEON_GROUPS, ON_YOU, TO, TRAINER_GROUP, YOU_SUFFIX, Rule, tr
from .settings import Settings
from .world import World

KEEP_S = 1.2  # so lange bleibt eine abgelaufene Warnung noch stehen
SAME_S = 1.0  # dieselbe Regel so kurz danach: nur einmal warnen
SPEAK, LINE, WAVE = "ansage", "zeile", "welle"  # Arten in `sounds`; alles andere ist der Alarmton
SILENT = "aus"
Preview = Callable[[float], list[tuple[str, float]]]  # jetzt → [(Text, Sekunden)]


@dataclass
class Warning:
    rule: Rule
    start: float
    me: bool = False  # der eigene Charakter ist das Ziel
    since: float = 0.0  # Beginn der Warnkette, für die Auswertung
    target: str = ""  # Name des Ziels, falls ein anderer Spieler

    def title(self) -> str:
        if self.me:
            return tr(self.rule.title) + tr(YOU_SUFFIX)
        return tr(self.rule.title) + (tr(TO) + self.target if self.target else "")

    def rest(self, now: float) -> float:
        return self.rule.lead - (now - self.start)


class WarningBoard:
    def __init__(self, world: World, settings: Settings | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.world = world
        self.clock = clock
        self.lock = threading.Lock()
        self.active: list[Warning] = []
        self.planned: list[tuple[float, Rule]] = []  # (fällig um, Regel)
        self.sounds: list[tuple[str, str]] = []  # (Art, Text): spielt der Dienst in seinem Takt ab
        self.settings = settings or Settings()
        self.enabled: bool = self.settings.warnings.enabled
        self.previews: list[Preview] = []  # weitere Zeilen der Vorschau (Zeitfenster, Berserker)

    # ------------------------------------------------------------ Fragen der Auslöser
    def foreign(self, target: int | None) -> bool:
        """Einstellung „Nur was mich betrifft“ und das Ziel ist ein anderer Spieler. Kein Ziel, der Boss
        selbst oder ein unbekanntes Wesen zählen nicht als fremd (Flächen, Angriffe auf alle)."""
        return self.settings.warnings.only_me and target is not None and target != self.world.own_id \
            and target in self.world.players

    def group_on(self, group: str) -> bool:
        """Warnungen an und die Gruppe gehört zum erkannten Dungeon (sonst Skill-ID aus einem anderen)."""
        dungeon = self.world.dungeon
        return self.enabled and not (dungeon and group not in {*DUNGEON_GROUPS[dungeon], TRAINER_GROUP})

    def running(self, match: Callable[[Warning], bool], now: float) -> bool:
        """Läuft gerade eine Warnung, auf die `match` zutrifft? Aufruf unter self.lock."""
        return any(match(w) and w.rest(now) > 0 for w in self.active)

    # ------------------------------------------------------------ auslösen
    def trigger(self, rule: Rule, now: float | None = None, me: bool = False, name: str = "") -> None:
        """Warnung zeigen, ihre gleichzeitigen Vorhersagen dazu und die geplanten Folgen einreihen. Ein
        neuer Auslöser ersetzt geplante Vorhersagen derselben Gruppen."""
        with self.lock:
            self._trigger(rule, self.clock() if now is None else now, me, name)

    def trigger_unless(self, running: Callable[[Warning], bool], rule: Rule, me: bool = False) -> None:
        """Wie trigger(), aber nur, wenn keine passende Warnung läuft (Pfützen treffen mehrmals pro Sekunde)."""
        now = self.clock()
        with self.lock:
            if not self.running(running, now):
                self._trigger(rule, now, me)

    def trigger_cast(self, rule: Rule, target: int | None) -> bool:
        """Warnung zu einem Cast: nicht, wenn ihr Schalter aus ist oder sie einen anderen betrifft."""
        if not self.group_on(rule.group) or self.foreign(target):
            return False
        own = self.world.own_id
        me = rule.on_you and target is not None and target == own
        self.trigger(rule, me=me, name="" if me or target == own else self.world.player_name(target))
        return True

    def add(self, rule: Rule, target: str = "") -> None:
        """Nur diese Warnung, ohne ihre Vorhersagen und ohne Geplantes zu ersetzen."""
        with self.lock:
            self._add(rule, self.clock(), target=target)

    def drop(self, rules: set[Rule]) -> None:
        with self.lock:
            self.active = [w for w in self.active if w.rule not in rules]

    def _trigger(self, rule: Rule, now: float, me: bool = False, name: str = "") -> None:
        groups = {r.group for r in (rule, *rule.together)}
        self.planned = [(t, r) for t, r in self.planned if r.group not in groups]
        self.planned += [(now + after, r) for after, r in rule.plan]
        self._add(rule, now, me, name)
        for r in rule.together:
            self._add(r, now)

    def _add(self, rule: Rule, start: float, me: bool = False, target: str = "") -> None:
        if rule.group in self.settings.warnings.off:
            return  # auf der NexBoard-Seite abgeschaltet
        old = [w for w in self.active if w.rule.group == rule.group and w.rest(start) > -KEEP_S]
        if any(w.rule == rule and start - w.start < SAME_S for w in old):
            return  # derselbe Skill doppelt: nur einmal warnen
        since = min([w.since for w in old] + [start])
        self.active = [w for w in self.active if w.rule.group != rule.group]
        warning = Warning(rule, start, me, since, target)
        self.active.append(warning)
        kind = self.settings.warnings.sounds.get(rule.group, SPEAK)
        if kind == SPEAK and rule.speak is not None:
            # erster Text wichtig, die weiteren dürfen abgebrochen werden
            self.sounds += [(SPEAK if i == 0 else LINE, text) for i, text in enumerate(rule.speak) if text]
        elif kind != SILENT:
            self.sounds.append((kind, warning.title().replace(tr(YOU_SUFFIX), tr(ON_YOU))))

    # ------------------------------------------------------------ zeigen
    def snapshot(self) -> list[Warning]:
        """Die laufenden Warnungen; holt fällige Vorhersagen nach vorn."""
        now = self.clock()
        with self.lock:
            for due, rule in [p for p in self.planned if p[0] <= now]:
                self.planned.remove((due, rule))
                self._add(rule, due)
            self.active = [w for w in self.active if w.rest(now) > -KEEP_S]
            return list(self.active)

    def latest(self, now: float) -> Warning | None:
        """Die zuletzt erschienene Warnung, die gerade läuft (für die Todesursache). Lernhilfe zählt nicht."""
        with self.lock:
            current = [w for w in self.active if w.rule.group != TRAINER_GROUP and w.start <= now
                       and w.rest(now) > -KEEP_S]
        return max(current, key=lambda w: w.start, default=None)

    def planned_groups(self) -> set[str]:
        return {rule.group for _, rule in self.planned}

    def preview(self) -> list[tuple[str, float]]:
        """Kleine Zeile oben: (Text, Sekunden). 0 Sekunden = jetzt möglich."""
        now = self.clock()
        with self.lock:
            lines = [(r.title.replace(" kommt", "").replace(" erwartet", ""), due + r.lead - now)
                     for due, r in self.planned if r.group not in self.settings.warnings.off]
        for source in self.previews:
            lines += source(now)
        return sorted(lines, key=lambda line: line[1])
