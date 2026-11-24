"""Kartenbilder mit ihrer Eichung Welt ↔ Bild, gespeichert unter karten/<Name>/ im Datenordner."""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from .gamedata import STORE

MAPS = STORE / "karten"
BUNDLED = Path(__file__).resolve().parents[3] / "radar" / "karten"  # fertige Karten im Repo (aion2hub)
Pair = tuple[float, float, float, float]  # Welt x, y → Bild u, v


class Calibration:
    """Abbildung Welt (x, y in cm) → Kartenbild (u, v in Pixeln).

    Zwei Punkte: Drehen, Skalieren, Verschieben. Ab drei Punkten zusätzlich Spiegeln und Scheren (affin,
    nach kleinsten Quadraten).
    """

    def __init__(self, pairs: list[Pair] | None = None) -> None:
        self.pairs = list(pairs or [])
        self.m: tuple[float, ...] | None = None  # u = a x + b y + c,  v = d x + e y + f
        self._solve()

    @property
    def ready(self) -> bool:
        return self.m is not None

    def add(self, x: float, y: float, u: float, v: float) -> None:
        self.pairs.append((x, y, u, v))
        self._solve()

    def reset(self) -> None:
        self.pairs.clear()
        self.m = None

    def _solve(self) -> None:
        if len(self.pairs) == 2:
            (x1, y1, u1, v1), (x2, y2, u2, v2) = self.pairs
            # Unreal ist linkshändig (+y rechts von +x) und im Bild zeigt v nach unten.
            # Als komplexe Zahlen x - iy und u - iv ist es dann eine reine Drehstreckung.
            w = complex(x2 - x1, y1 - y2)
            if abs(w) < 1e-6:
                self.m = None
                return
            k = complex(u2 - u1, v1 - v2) / w
            t = complex(u1, -v1) - k * complex(x1, -y1)
            self.m = (k.real, k.imag, t.real, -k.imag, k.real, -t.imag)
        elif len(self.pairs) >= 3:
            self.m = _affine(self.pairs)
        else:
            self.m = None

    def to_image(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.m
        return a * x + b * y + c, d * x + e * y + f

    def to_world(self, u: float, v: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.m
        det = a * e - b * d
        u, v = u - c, v - f
        return (e * u - b * v) / det, (a * v - d * u) / det

    def error_px(self) -> float:
        """Mittlerer Abstand der Eichpunkte zur berechneten Abbildung."""
        if not self.ready:
            return 0.0
        return sum(math.dist(self.to_image(x, y), (u, v)) for x, y, u, v in self.pairs) / len(self.pairs)


def _affine(pairs: list[Pair]) -> tuple[float, ...]:
    """Kleinste Quadrate für u = a x + b y + c (und v genauso) über die Normalgleichungen."""
    s = [[0.0] * 3 for _ in range(3)]
    ru, rv = [0.0] * 3, [0.0] * 3
    for x, y, u, v in pairs:
        r = (x, y, 1.0)
        for i in range(3):
            for j in range(3):
                s[i][j] += r[i] * r[j]
            ru[i] += r[i] * u
            rv[i] += r[i] * v
    return (*_gauss(s, ru), *_gauss(s, rv))


def _gauss(m: list[list[float]], r: list[float]) -> list[float]:
    """3×3-Gleichungssystem mit Gauß-Verfahren."""
    a = [row[:] + [r[i]] for i, row in enumerate(m)]
    for i in range(3):
        p = max(range(i, 3), key=lambda k: abs(a[k][i]))
        if abs(a[p][i]) < 1e-12:
            raise ValueError("Eichpunkte liegen auf einer Linie")
        a[i], a[p] = a[p], a[i]
        for k in range(i + 1, 3):
            f = a[k][i] / a[i][i]
            for j in range(i, 4):
                a[k][j] -= f * a[i][j]
    x = [0.0] * 3
    for i in (2, 1, 0):
        x[i] = (a[i][3] - sum(a[i][j] * x[j] for j in range(i + 1, 3))) / a[i][i]
    return x


class GameMap:
    """Ein Kartenbild mit Eichung, Fundorten und Teleportern."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.folder = MAPS / name
        # bild.png (eigener Screenshot, werkzeuge.cubekarte) oder bild.webp (mitgeliefert, kleiner)
        images = (self.folder / "bild.png", self.folder / "bild.webp")
        self.image = next((image for image in images if image.exists()), images[0])
        try:
            pairs = json.loads((self.folder / "eichung.json").read_text()).get("paare", [])
        except (OSError, ValueError):
            pairs = []
        self.calibration = Calibration([tuple(p) for p in pairs])

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "eichung.json").write_text(json.dumps({"paare": self.calibration.pairs}))

    def listing(self, file: str) -> list:
        """JSON-Liste aus dem Kartenordner (fundorte.json, teleporter.json), leer, wenn es sie nicht gibt."""
        try:
            return json.loads((self.folder / file).read_text())
        except (OSError, ValueError):
            return []

    @property
    def symbol(self) -> Path:
        """Teleporter-Symbol aus dem Spiel (werkzeuge.cubekarte)."""
        return self.folder / "teleporter.png"

    @staticmethod
    def all() -> list[GameMap]:
        _copy_bundled()
        if not MAPS.exists():
            return []
        return [m for m in (GameMap(folder.name) for folder in sorted(MAPS.iterdir())) if m.image.exists()]


def _copy_bundled() -> None:
    """Karten aus dem Repo einmalig in den eigenen Kartenordner kopieren, vorhandene bleiben."""
    if not BUNDLED.is_dir():
        return
    for folder in BUNDLED.iterdir():
        if folder.is_dir() and not (MAPS / folder.name).exists():
            shutil.copytree(folder, MAPS / folder.name)
