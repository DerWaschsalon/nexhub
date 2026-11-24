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

WINDOW_TITLE = re.compile(r"^AION2 *$")  # Overlays heißen „AION2 Radar“ usw.
STEP = 2  # Grad zwischen zwei abgetasteten Richtungen
RING = (0.55, 0.95)  # außerhalb des hellen Innenkreises, dort sind nur noch die Linien weiß
MIN_SHARE = 0.45  # so viel des Strahls muss weiß sein, Quest-Punkte erreichen das nicht
CONE = (95, 130)  # erlaubter Abstand der beiden Linien in Grad, alles andere ist keine Minikarte
NEIGHBOURS = ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1))  # die Linien sind nur 1-2 Pixel breit


def _white(rgb: tuple[int, int, int]) -> bool:
    return min(rgb) > 175 and max(rgb) - min(rgb) < 75


def white_by_direction(image) -> list[float]:
    """Anteil weißer Punkte je Richtung, im Uhrzeigersinn ab Norden, alle STEP Grad."""
    image = image.convert("RGB")
    w, h = image.size
    pixels = image.load()
    cx, cy = w / 2, h / 2
    radius = min(w, h) / 2
    profile = []
    for degrees in range(0, 360, STEP):
        rad = math.radians(degrees)
        sin, cos = math.sin(rad), math.cos(rad)
        hits = count = 0
        r = radius * RING[0]
        while r < radius * RING[1]:
            x, y = int(cx + r * sin), int(cy - r * cos)
            count += 1
            hits += any(_white(pixels[min(max(x + dx, 0), w - 1), min(max(y + dy, 0), h - 1)])
                        for dx, dy in NEIGHBOURS)
            r += 2
        profile.append(hits / count if count else 0.0)
    return profile


def view_direction(image) -> float | None:
    """Mitte zwischen den beiden Linien in Grad (0 = Nord, 90 = Ost) oder None, wenn sie nicht zu sehen
    sind (Menü offen, Ladebildschirm). Dann bleibt die letzte Richtung stehen."""
    profile = white_by_direction(image)
    n = len(profile)
    peaks = [i for i in range(n)
             if profile[i] >= MIN_SHARE and profile[i] == max(profile[(i + d) % n] for d in range(-3, 4))]
    best = None
    for a in peaks:
        for b in peaks:
            gap = (b - a) % n * STEP
            if CONE[0] <= gap <= CONE[1]:
                value = profile[a] + profile[b]
                if best is None or value > best[0]:
                    best = (value, (a * STEP + gap / 2) % 360)
    return best[1] if best else None


def heading(degrees: float) -> tuple[float, float]:
    """Richtung als Einheitsvektor in Weltkoordinaten wie World.heading (Norden = Welt -y, Osten = +x)."""
    rad = math.radians(degrees)
    return (math.sin(rad), -math.cos(rad))


class _GameWindow:
    """Das Spielfenster über X11. Pillows ImageGrab taugt hier nicht: Das Stammfenster von XWayland lässt
    sich nicht lesen, und dann startet Pillow bei jedem Aufruf ein Screenshot-Programm."""

    SEARCH_S = 2.0  # das Fenster höchstens so oft neu suchen, die Suche durch den Baum dauert einige ms

    def __init__(self) -> None:
        self.display = None
        self.window = None
        self._searched = 0.0

    def _find(self, window):
        try:
            name = window.get_wm_name()
            if isinstance(name, str) and WINDOW_TITLE.match(name):
                return window
            children = window.query_tree().children
        except Exception:  # Fenster kann zwischendurch verschwinden
            return None
        for child in children:
            found = self._find(child)
            if found is not None:
                return found
        return None

    def grab(self, x: int, y: int, w: int, h: int):
        from PIL import Image
        from Xlib import X, display  # erst hier: Tests und Mitschnitt-Auswertung brauchen keinen Bildschirm

        try:
            if self.display is None:
                self.display = display.Display()
            if self.window is None:
                if time.monotonic() - self._searched < self.SEARCH_S:
                    return None
                self._searched = time.monotonic()
                self.window = self._find(self.display.screen().root)
                if self.window is None:
                    return None
            raw = self.window.get_image(x, y, w, h, X.ZPixmap, 0xFFFFFFFF)
            return Image.frombuffer("RGB", (w, h), bytes(raw.data), "raw", "BGRX", 0, 1)
        except Exception:  # Spiel beendet, Fenster neu oder X weg: beim nächsten Mal neu verbinden
            self.display = self.window = None
            return None


_game = _GameWindow()


def grab(area: list[int]):
    """Ausschnitt [x, y, Breite, Höhe] in Pixeln des Spielfensters. None, wenn es nicht lesbar ist."""
    return _game.grab(*area)
