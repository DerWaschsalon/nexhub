"""Gesehene Spawnpunkte der Hidden Cubes (cubepunkte.json) für die Karte.

Ein Punkt ist ein dict mit x, y, z, objekt_id, quelle („radar“ = selbst gesehen), anzahl und zuletzt.
"""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

from .gamedata import STORE

FILE = STORE / "cubepunkte.json"
SAME_CM = 300.0  # näher als 3 m = derselbe Spawnpunkt
SEEN = "radar"


class SpawnPoints:
    def __init__(self, file: Path = FILE) -> None:
        self.file = file
        self.lock = threading.Lock()
        try:
            self.points: list[dict] = json.loads(file.read_text())
        except (OSError, ValueError):
            self.points = []

    def save(self) -> None:
        with self.lock:
            data = json.dumps(self.points, indent=1)
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(data)
        tmp.replace(self.file)

    def add(self, x: float, y: float, z: float, object_id: int | None = None, source: str = SEEN) -> None:
        with self.lock:
            point = self._nearest(x, y, SAME_CM)
            if point:
                point["anzahl"] += 1
                if source == SEEN:
                    point["quelle"] = SEEN
            else:
                point = {"x": round(x, 1), "y": round(y, 1), "z": round(z, 1), "objekt_id": object_id,
                         "quelle": source, "anzahl": 1}
                self.points.append(point)
            point["zuletzt"] = round(time.time())
        self.save()

    def remove(self, x: float, y: float, max_cm: float) -> bool:
        with self.lock:
            point = self._nearest(x, y, max_cm)
            if point:
                self.points.remove(point)
        if point:
            self.save()
        return point is not None

    def all(self) -> list[dict]:
        with self.lock:
            return [dict(p) for p in self.points]

    def _nearest(self, x: float, y: float, max_cm: float) -> dict | None:
        near = [(math.dist((p["x"], p["y"]), (x, y)), i) for i, p in enumerate(self.points)]
        near = [(d, i) for d, i in near if d < max_cm]
        return self.points[min(near)[1]] if near else None
