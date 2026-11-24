"""Hidden Cubes: welche gerade stehen, seit wann, wer sie öffnet, und wie viele Schlüssel verbraucht sind."""
from __future__ import annotations

import json
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..core.packets import PacketSource
from ..core.packets.messages import ObjectGone, ObjectOpened, ObjectOpening, ObjectSpawn, Teleport
from .signal import Signal
from .world import World

# Objekt-IDs der Hidden Cubes. 1301199 am echten Cube bestätigt, Rest vom Vorläufer.
CUBE_IDS = {
    1000295, 1000548, 1000556, 1000566, 1000567, 1000568, 1100056, 1100094,
    1200018, 1200036, 1200037, 1200039, 1200040, 1200041, 1200667, 1200707,
    1201054, 1201055, 1300754, 1301199, 1301200, 1401335, 1401336, 3682560,
    # ungeprüft, aus benhighlanderr/Aion2-Hidden-Cube-Radar: Varianten 01_V01-V19 und 1300081/82
    *range(1000549, 1000566), 1300081, 1300082,
}
CUBE_KEY = 630900003  # Item, das beim Öffnen eines Cubes verbraucht wird (aion2-cube-radar, AsseylumVA)
PLAUSIBLE_AGE_S = 86400  # Serverzeit eines Cubes nur glauben, wenn sie in den letzten 24 h liegt
UNKNOWN_OPENER = "?"


@dataclass
class Cube:
    entity: int
    object_id: int
    x: float
    y: float
    z: float
    since: float = field(default_factory=time.time)  # seit wann er steht (Serverzeit, sonst gesehen)
    opener: str = ""  # wer ihn gerade öffnet


class CubeTracker:
    def __init__(self, world: World, spawn_log: Path | None = None, extra_ids: frozenset[int] = frozenset()) -> None:
        self.world = world
        self.lock = threading.Lock()
        self.cube_ids = CUBE_IDS | extra_ids
        self.spawn_log = spawn_log  # jedes erschienene Objekt als JSON-Zeile, für die Werkzeuge
        self.cubes: dict[int, Cube] = {}
        self.keys_used = 0  # verbrauchte Schlüssel seit dem Start
        self.appeared = Signal[Cube]()

    def attach(self, source: PacketSource) -> None:
        source.on(ObjectSpawn, self._on_spawn)
        source.on(ObjectGone, self._on_gone)
        source.on(ObjectOpening, self._on_opening)
        source.on(ObjectOpened, self._on_opened)
        source.on(Teleport, self._on_teleport)

    def current(self) -> list[Cube]:
        with self.lock:
            return list(self.cubes.values())

    def _on_spawn(self, m: ObjectSpawn) -> None:
        is_cube = m.object_id in self.cube_ids
        if self.spawn_log:
            self._log(m, is_cube)
        if not is_cube:
            return
        cube = Cube(m.entity, m.object_id, *m.position)
        if m.since is not None and 0 < time.time() - m.since < PLAUSIBLE_AGE_S:
            cube.since = m.since
        with self.lock:
            new = m.entity not in self.cubes
            self.cubes[m.entity] = cube
        if new:
            self.appeared.emit(cube)

    def _on_gone(self, m: ObjectGone) -> None:
        with self.lock:
            self.cubes.pop(m.entity, None)

    def _on_opening(self, m: ObjectOpening) -> None:
        if m.entity in self.cubes:
            self.cubes[m.entity].opener = self.world.players.get(m.opener, UNKNOWN_OPENER)

    def _on_opened(self, m: ObjectOpened) -> None:
        if struct.pack("<I", CUBE_KEY) in m.tail:
            self.keys_used += 1

    def _on_teleport(self, _: Teleport) -> None:
        """Entity-IDs gelten nur bis zum nächsten Teleport oder Zonenwechsel."""
        with self.lock:
            self.cubes.clear()

    def _log(self, m: ObjectSpawn, is_cube: bool) -> None:
        x, y, z = (round(v, 1) for v in m.position)
        line = {"t": round(time.time(), 2), "eid": m.entity, "objekt_id": m.object_id, "x": x, "y": y, "z": z,
                "cube": is_cube}
        try:
            with open(self.spawn_log, "a") as f:
                f.write(json.dumps(line) + "\n")
        except OSError:
            pass
