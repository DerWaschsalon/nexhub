"""Blickrichtung aus der Minikarte im Spielbild, nur vom Bildschirm gelesen (nichts aus dem Speicher).

Die Minikarte ist nach Norden ausgerichtet. Von ihrer Mitte gehen zwei weiße Linien aus, zwischen denen
das Sichtfeld liegt (gemessen 111-114 Grad, Bilder vom 05.11.2026). Die Blickrichtung ist die Mitte
zwischen den Linien. Die Helligkeit der Fläche taugt nicht: Je nach Gelände ist der Kegel heller oder
dunkler als der Rest. Der Server schickt die eigene Blickrichtung nicht, und die Laufrichtung kommt nur
bei Sprint, Sprung oder Kampf.
"""
from __future__ import annotations

import math
import re
import time

TITEL = re.compile(r"^AION2 *$")  # Overlays heißen „AION2 Radar“ usw.
SCHRITT = 2 # Grad zwischen zwei abgetasteten Richtungen
RING = (0.55, 0.95)  # außerhalb des hellen Innenkreises, dort sind nur noch die Linien weiß
MIN_ANTEIL = 0.45  # so viel des Strahls muss weiß sein, Quest-Punkte erreichen das nicht
KEGEL = (95, 130)  # erlaubter Abstand der beiden Linien in Grad, alles andere ist keine Minikarte
NACHBARN = ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1))  # die Linien sind nur 1-2 Pixel breit


def _weiss(rgb: tuple[int, int, int]) -> bool:
    return min(rgb) > 175 and max(rgb) - min(rgb) < 75


def weiss_je_richtung(bild) -> list[float]:
    """Anteil weißer Punkte je Richtung, im Uhrzeigersinn ab Norden, alle SCHRITT Grad."""
    bild = bild.convert("RGB")
    w, h = bild.size
    punkte = bild.load()
    cx, cy = w / 2, h / 2
    radius = min(w, h) / 2
    profil = []
    for grad in range(0, 360, SCHRITT):
        rad = math.radians(grad)
        sin, cos = math.sin(rad), math.cos(rad)
        treffer = anzahl = 0
        r = radius * RING[0]
        while r < radius * RING[1]:
            x, y = int(cx + r * sin), int(cy - r * cos)
            anzahl += 1
            treffer += any(_weiss(punkte[min(max(x + dx, 0), w - 1), min(max(y + dy, 0), h - 1)])
                           for dx, dy in NACHBARN)
            r += 2
        profil.append(treffer / anzahl if anzahl else 0.0)
    return profil


def blickrichtung(bild) -> float | None:
    """Mitte zwischen den beiden Linien in Grad (0 = Nord, 90 = Ost) oder None, wenn sie nicht zu sehen
    sind (Menü offen, Ladebildschirm). Dann bleibt der letzte Kurs stehen."""
    profil = weiss_je_richtung(bild)
    n = len(profil)
    spitzen = [i for i in range(n)
               if profil[i] >= MIN_ANTEIL and profil[i] == max(profil[(i + d) % n] for d in range(-3, 4))]
    beste = None
    for a in spitzen:
        for b in spitzen:
            abstand = (b - a) % n * SCHRITT
            if KEGEL[0] <= abstand <= KEGEL[1]:
                wert = profil[a] + profil[b]
                if beste is None or wert > beste[0]:
                    beste = (wert, (a * SCHRITT + abstand / 2) % 360)
    return beste[1] if beste else None


def kurs(grad: float) -> tuple[float, float]:
    """Richtung als Einheitsvektor in Weltkoordinaten wie RadarZustand.kurs (Norden = Welt -y, Osten = +x)."""
    rad = math.radians(grad)
    return (math.sin(rad), -math.cos(rad))


class _Spielfenster:
    """Das Spielfenster über X11. Pillows ImageGrab taugt hier nicht: Das Stammfenster von XWayland lässt
    sich nicht lesen, und dann startet Pillow bei jedem Aufruf ein Screenshot-Programm."""

    SUCHE_S = 2.0  # das Fenster höchstens so oft neu suchen, die Suche durch den Baum dauert einige ms

    def __init__(self) -> None:
        self.anzeige = None
        self.fenster = None
        self._gesucht = 0.0

    def _suchen(self, fenster):
        try:
            name = fenster.get_wm_name()
            if isinstance(name, str) and TITEL.match(name):
                return fenster
            kinder = fenster.query_tree().children
        except Exception:  # Fenster kann zwischendurch verschwinden
            return None
        for kind in kinder:
            treffer = self._suchen(kind)
            if treffer is not None:
                return treffer
        return None

    def lesen(self, x: int, y: int, w: int, h: int):
        from PIL import Image
        from Xlib import X, display  # erst hier: Tests und Mitschnitt-Auswertung brauchen keinen Bildschirm

        try:
            if self.anzeige is None:
                self.anzeige = display.Display()
            if self.fenster is None:
                if time.monotonic() - self._gesucht < self.SUCHE_S:
                    return None
                self._gesucht = time.monotonic()
                self.fenster = self._suchen(self.anzeige.screen().root)
                if self.fenster is None:
                    return None
            roh = self.fenster.get_image(x, y, w, h, X.ZPixmap, 0xFFFFFFFF)
            return Image.frombuffer("RGB", (w, h), bytes(roh.data), "raw", "BGRX", 0, 1)
        except Exception:  # Spiel beendet, Fenster neu oder X weg: beim nächsten Mal neu verbinden
            self.anzeige = self.fenster = None
            return None


_spiel = _Spielfenster()


def lesen(bereich: list[int]):
    """Ausschnitt [x, y, Breite, Höhe] in Pixeln des Spielfensters. None, wenn es nicht lesbar ist."""
    return _spiel.lesen(*bereich)
