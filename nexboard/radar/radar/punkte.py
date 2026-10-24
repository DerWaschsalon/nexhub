"""Gesehene Cube-Spawnpunkte und die Eichung Welt <-> Kartenbild."""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

DATEN = Path.home() / ".local" / "share" / "aion2-radar"
PUNKTE = DATEN / "cubepunkte.json"
KARTEN = DATEN / "karten"
GLEICH_CM = 300.0  # naeher als 3 m = derselbe Spawnpunkt


class PunkteDB:
    """Spawnpunkte als Liste von dicts: x, y, z, objekt_id, quelle, anzahl, zuletzt."""

    def __init__(self, datei: Path = PUNKTE) -> None:
        self.datei = datei
        self.lock = threading.Lock()
        try:
            self.punkte: list[dict] = json.loads(datei.read_text())
        except (OSError, ValueError):
            self.punkte = []

    def speichern(self) -> None:
        with self.lock:
            daten = json.dumps(self.punkte, indent=1)
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.datei.with_suffix(".tmp")
        tmp.write_text(daten)
        tmp.replace(self.datei)

    def eintragen(self, x: float, y: float, z: float, objekt_id: int | None = None,
                  quelle: str = "radar") -> None:
        with self.lock:
            p = self._naechster(x, y, GLEICH_CM)
            if p:
                p["anzahl"] += 1
                if quelle == "radar":
                    p["quelle"] = "radar"
            else:
                p = {"x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                     "objekt_id": objekt_id, "quelle": quelle, "anzahl": 1}
                self.punkte.append(p)
            p["zuletzt"] = round(time.time())
        self.speichern()

    def entfernen(self, x: float, y: float, max_cm: float) -> bool:
        with self.lock:
            p = self._naechster(x, y, max_cm)
            if p:
                self.punkte.remove(p)
        if p:
            self.speichern()
        return p is not None

    def alle(self) -> list[dict]:
        with self.lock:
            return [dict(p) for p in self.punkte]

    def _naechster(self, x: float, y: float, max_cm: float) -> dict | None:
        nah = [(math.dist((p["x"], p["y"]), (x, y)), i) for i, p in enumerate(self.punkte)]
        nah = [(d, i) for d, i in nah if d < max_cm]
        return self.punkte[min(nah)[1]] if nah else None


class Eichung:
    """Abbildung Welt (x, y in cm) -> Kartenbild (u, v in Pixeln).

    Zwei Punkte: Drehen, Skalieren, Verschieben. Ab drei Punkten zusaetzlich
    Spiegeln und Scheren (affin, nach kleinsten Quadraten).
    """

    def __init__(self, paare: list[tuple[float, float, float, float]] | None = None) -> None:
        self.paare = list(paare or [])
        self.m: tuple[float, ...] | None = None  # u = a x + b y + c,  v = d x + e y + f
        self._berechnen()

    @property
    def fertig(self) -> bool:
        return self.m is not None

    def hinzufuegen(self, x: float, y: float, u: float, v: float) -> None:
        self.paare.append((x, y, u, v))
        self._berechnen()

    def zuruecksetzen(self) -> None:
        self.paare.clear()
        self.m = None

    def _berechnen(self) -> None:
        if len(self.paare) == 2:
            (x1, y1, u1, v1), (x2, y2, u2, v2) = self.paare
            # Unreal ist linkshaendig (+y rechts von +x) und im Bild zeigt v nach unten.
            # Als komplexe Zahlen x - iy und u - iv ist es dann eine reine Drehstreckung.
            w = complex(x2 - x1, y1 - y2)
            if abs(w) < 1e-6:
                self.m = None
                return
            k = complex(u2 - u1, v1 - v2) / w
            t = complex(u1, -v1) - k * complex(x1, -y1)
            self.m = (k.real, k.imag, t.real, -k.imag, k.real, -t.imag)
        elif len(self.paare) >= 3:
            self.m = _affin(self.paare)
        else:
            self.m = None

    def welt_zu_bild(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.m
        return a * x + b * y + c, d * x + e * y + f

    def bild_zu_welt(self, u: float, v: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.m
        det = a * e - b * d
        u, v = u - c, v - f
        return (e * u - b * v) / det, (a * v - d * u) / det

    def fehler_px(self) -> float:
        """Mittlerer Abstand der Eichpunkte zur berechneten Abbildung."""
        if not self.fertig:
            return 0.0
        return sum(math.dist(self.welt_zu_bild(x, y), (u, v))
                   for x, y, u, v in self.paare) / len(self.paare)


def _affin(paare) -> tuple[float, ...]:
    """Kleinste Quadrate fuer u = a x + b y + c (und v genauso) ueber die Normalgleichungen."""
    s = [[0.0] * 3 for _ in range(3)]
    ru, rv = [0.0] * 3, [0.0] * 3
    for x, y, u, v in paare:
        r = (x, y, 1.0)
        for i in range(3):
            for j in range(3):
                s[i][j] += r[i] * r[j]
            ru[i] += r[i] * u
            rv[i] += r[i] * v
    return (*_loesen(s, ru), *_loesen(s, rv))


def _loesen(m: list[list[float]], r: list[float]) -> list[float]:
    """3x3-Gleichungssystem mit Gauss-Verfahren."""
    a = [zeile[:] + [r[i]] for i, zeile in enumerate(m)]
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


class Karte:
    """Ein Kartenbild mit Eichung, gespeichert unter karten/<name>/."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.ordner = KARTEN / name
        self.bild = self.ordner / "bild.png"
        try:
            paare = json.loads((self.ordner / "eichung.json").read_text()).get("paare", [])
        except (OSError, ValueError):
            paare = []
        self.eichung = Eichung([tuple(p) for p in paare])

    def speichern(self) -> None:
        self.ordner.mkdir(parents=True, exist_ok=True)
        (self.ordner / "eichung.json").write_text(json.dumps({"paare": self.eichung.paare}))

    @staticmethod
    def alle() -> list["Karte"]:
        if not KARTEN.exists():
            return []
        return [Karte(o.name) for o in sorted(KARTEN.iterdir()) if (o / "bild.png").exists()]
