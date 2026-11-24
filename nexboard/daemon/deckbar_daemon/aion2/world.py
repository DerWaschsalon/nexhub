"""core.world: was mehrere Teile über die Spielwelt wissen müssen. Eigene Entity, Position und
Laufrichtung, Zone und Dungeon, Namen der Spieler und welche Entity welcher Boss ist."""
from __future__ import annotations

import math
import threading
import time
from collections import Counter

from ..core.packets import PacketSource
from ..core.packets.messages import (
    Cast,
    DungeonRun,
    Effect,
    NpcSeen,
    PlayerSeen,
    Position,
    PositionUpdate,
    Teleport,
    Vitals,
    WorldEntry,
    ZoneChange,
    ZonePosition,
    valid,
)
from .gamedata import BOSSES, ZONES
from .signal import Signal

MAX_JUMP_CM = 3000  # ungeprüfte Position: höchstens 30 m neben der letzten …
JUMP_AGE_S = 10  # … außer die letzte ist älter
HEADING_FROM_CM = 100  # Laufrichtung erst ab 1 m Weg neu bestimmen
GUESS_AFTER = 100  # so viele Vitals ohne sichere ID, dann gilt die häufigste Entity als eigene


class World:
    def __init__(self, character_name: str = "") -> None:
        self.lock = threading.Lock()
        self.character_name = character_name
        self._name_bytes = (character_name.encode(), character_name.encode("utf-16le")) if character_name else ()
        self.own_id: int | None = None
        self.own_id_sure = False
        self._vitals_seen: Counter[int] = Counter()
        self.position: Position | None = None
        self.position_time = 0.0
        self.heading: tuple[float, float] | None = None  # Laufrichtung als Einheitsvektor (Welt x, y)
        self._heading_from: tuple[float, float] | None = None
        self.look_until = 0.0  # bis dahin gilt die Blickrichtung aus der Minikarte, nicht die Laufrichtung
        self.zone: int | None = None
        self.dungeon: str | None = None  # beim Betreten (ZoneChange), sonst am ersten Boss
        self.dungeon_ends_at: float | None = None  # Zeitlimit des laufenden Dungeons (Sekunden seit 1970)
        self.players: dict[int, str] = {}  # Entity → Name
        self.bosses: dict[int, int] = {}  # Entity → Boss-NPC
        self.boss_since: dict[int, float] = {}  # Boss-Entity → seit wann er da ist
        self.own_hp = Signal[int]()  # eigene aktuelle HP, nur bei sicher erkanntem Charakter

    def attach(self, source: PacketSource) -> None:
        for message, handler in ((PlayerSeen, self._on_player), (Vitals, self._on_vitals),
                                 (Teleport, self._on_teleport), (ZoneChange, self._on_zone), (NpcSeen, self._on_npc),
                                 (Effect, self._on_own_position), (PositionUpdate, self._on_position),
                                 (WorldEntry, self._on_entry), (ZonePosition, self._on_zone_position),
                                 (Cast, self._on_cast), (DungeonRun, self._on_dungeon)):
            source.on(message, handler)

    def player_name(self, entity: int | None) -> str:
        return self.players.get(entity, "") if entity is not None else ""

    # ------------------------------------------------------------ wer bin ich
    def _on_player(self, m: PlayerSeen) -> None:
        self.players[m.entity] = m.name
        if m.character and any(name in m.head for name in self._name_bytes):
            self.own_id, self.own_id_sure = m.entity, True

    def _on_vitals(self, m: Vitals) -> None:
        """MP oder SP gibt es nur für den eigenen Charakter: dann ist die ID sicher. Bis dahin gilt die
        häufigste Entity (im Massen-PvP oft falsch, dort tragen alle Spieler HP)."""
        if m.own_points:
            self.own_id, self.own_id_sure = m.entity, True
        elif not self.own_id_sure:
            self._vitals_seen[m.entity] += 1
            if sum(self._vitals_seen.values()) >= GUESS_AFTER:
                self.own_id = self._vitals_seen.most_common(1)[0][0]
                self._vitals_seen.clear()
        # nur bei sicher erkanntem Charakter (sonst evtl. der Boss)
        if self.own_id_sure and m.entity == self.own_id and m.hp is not None:
            self.own_hp.emit(m.hp)

    def _on_entry(self, m: WorldEntry) -> None:
        if self.own_id is None:
            self.own_id = m.entity  # nur geschätzt; Name oder MP/SP machen sie sicher
        if m.entity == self.own_id:
            self._set_checked(m.position)

    def _on_teleport(self, m: Teleport) -> None:
        """Entity-IDs gelten nur bis zum nächsten Teleport oder Zonenwechsel."""
        self.own_id, self.own_id_sure = None, False
        if m.position:
            self._set(m.position)

    # ------------------------------------------------------------ wo bin ich
    def _on_zone(self, m: ZoneChange) -> None:
        self.zone = m.zone
        self.dungeon = ZONES.get(m.zone)  # None = kein Dungeon

    def _on_dungeon(self, m: DungeonRun) -> None:
        self.dungeon_ends_at = m.ends_at

    def _on_npc(self, m: NpcSeen) -> None:
        if m.npc in BOSSES:
            self.dungeon, self.bosses[m.entity] = BOSSES[m.npc], m.npc
            self.boss_since[m.entity] = time.time()

    def _on_own_position(self, m: Effect) -> None:
        if m.entity == self.own_id and m.position:
            self._set(m.position)

    def _on_position(self, m: PositionUpdate) -> None:
        if m.entity == self.own_id:
            (self._set_checked if m.checked else self._set)(m.position)

    def _on_zone_position(self, m: ZonePosition) -> None:
        self._set_checked(m.position)

    def _on_cast(self, m: Cast) -> None:
        if m.entity == self.own_id and m.position:
            self._set_checked(m.position)

    def _set(self, position: Position) -> None:
        if valid(*position):
            with self.lock:
                self.position, self.position_time = position, time.time()
                self._note_heading(position[0], position[1])

    def _set_checked(self, position: Position) -> None:
        """Position aus einer ungeprüften Quelle: nur nah an der letzten (oder wenn die alt ist)."""
        last = self.position
        if last and time.time() - self.position_time < JUMP_AGE_S \
                and math.hypot(position[0] - last[0], position[1] - last[1]) > MAX_JUMP_CM:
            return
        self._set(position)

    def _note_heading(self, x: float, y: float) -> None:
        """Laufrichtung aus den letzten Metern. Sprünge (Teleport) setzen nur den Startpunkt neu."""
        if self._heading_from is None:
            self._heading_from = (x, y)
            return
        dx, dy = x - self._heading_from[0], y - self._heading_from[1]
        way = math.hypot(dx, dy)
        if way >= MAX_JUMP_CM:
            self._heading_from = (x, y)
        elif way >= HEADING_FROM_CM:
            self._heading_from = (x, y)
            if time.time() >= self.look_until:
                self.heading = (dx / way, dy / way)

    def position_age(self) -> float | None:
        return time.time() - self.position_time if self.position else None
