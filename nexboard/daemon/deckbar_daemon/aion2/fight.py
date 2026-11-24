"""Was im Kampf passiert, als Signale für Warnungen und Ansagen: Casts, Cast-Leisten, Wellen, Effekte,
Treffer auf dich, Flächen am Boden und Tode. Hier wird nur gefiltert, was niemanden betrifft."""
from __future__ import annotations

from ..core.packets import PacketSource
from ..core.packets.messages import Cast, CastBar, Death, Effect, EffectGone, GroundMarker, Hit, Wave
from .signal import Signal
from .world import World


class FightEvents:
    def __init__(self, world: World) -> None:
        self.world = world
        self.cast = Signal[int, int, int | None]()  # (Caster, Skill, Ziel)
        self.cast_bar = Signal[int, int, int | None]()  # (Caster, Skill, Ziel), kommt vor dem Cast
        self.wave = Signal[int, int]()  # (Caster, Skill), späterer Treffer eines Skills
        self.effect = Signal[int, int, int, float]()  # (Entity, Instanz, Effekt, Dauer s), nur effect_ids
        self.effect_gone = Signal[int, int]()  # (Entity, Instanz)
        self.status = Signal[int, int]()  # (Ziel, Status), nur status_ids
        self.hit = Signal[int]()  # Skill, der dich trifft, nur hit_ids
        self.death = Signal[int, int, str]()  # (Opfer, Skill, Name des Täters oder "")
        self.area = Signal[int, float, float, float]()  # (Skill, x, y, Sekunden bis zum Einschlag)
        # wofür sich die Abnehmer interessieren; alles andere wird nicht gemeldet
        self.effect_ids: set[int] = set()
        self.status_ids: set[int] = set()
        self.hit_ids: set[int] = set()

    def attach(self, source: PacketSource) -> None:
        source.on(Effect, self._on_effect)
        source.on(EffectGone, lambda m: self.effect_gone.emit(m.entity, m.instance))
        source.on(Cast, self._on_cast)
        source.on(CastBar, lambda m: self.cast_bar.emit(m.entity, m.skill, m.target))
        source.on(Wave, lambda m: self.wave.emit(m.entity, m.skill))
        source.on(Hit, self._on_hit)
        source.on(Death, lambda m: self.death.emit(m.victim, m.skill, m.killer_name))
        source.on(GroundMarker, self._on_marker)

    def _on_effect(self, m: Effect) -> None:
        if m.applied and m.applied[1] in self.effect_ids:
            self.effect.emit(m.entity, *m.applied)
        for status in self.status_ids:
            if m.has_status(status):
                self.status.emit(m.entity, status)

    def _on_cast(self, m: Cast) -> None:
        if m.skill is not None:
            self.cast.emit(m.entity, m.skill, m.target)

    def _on_hit(self, m: Hit) -> None:
        if m.entity == self.world.own_id and m.skill in self.hit_ids:
            self.hit.emit(m.skill)

    def _on_marker(self, m: GroundMarker) -> None:
        """Flächen von Monstern; die eigenen und die anderer Spieler zählen nicht."""
        if m.entity != self.world.own_id and m.entity not in self.world.players:
            self.area.emit(m.skill, m.x, m.y, m.seconds)
