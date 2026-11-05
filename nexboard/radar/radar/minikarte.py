"""Blickrichtung aus der Minikarte im Spielbild, nur vom Bildschirm gelesen (nichts aus dem Speicher).

Die Minikarte ist nach Norden ausgerichtet. Von ihrer Mitte zeigt ein heller Sichtkegel in die
Blickrichtung (Bild vom 05.11.2026: Kegel nach Nordost, hellste Richtungen 40-55 Grad). Der Server
schickt die eigene Blickrichtung nicht, und die Laufrichtung kommt nur bei Sprint, Sprung oder Kampf.
"""
from __future__ import annotations

import math
import statistics

SCHRITT = 5  # Grad zwischen zwei abgetasteten Richtungen
KEGEL = 50  # Breite des Sichtkegels in Grad
RING = (0.3, 0.9)  # abgetastet wird zwischen 30 und 90 % des Radius, die Mitte (Pfeil) bleibt frei
MIN_KONTRAST = 20  # so viel heller als der Rest muss der Kegel sein, sonst keine Richtung


def _punkt(rgb: tuple[int, int, int]) -> bool:
    """Weiße Markierungen (Quest-Punkte): sehr hell und fast ohne Farbe. Sie würden den Kegel vortäuschen."""
    return min(rgb) > 215 and max(rgb) - min(rgb) < 30


def helligkeit_je_richtung(bild) -> list[float]:
    """Mittlere Helligkeit (Median) je Richtung, im Uhrzeigersinn ab Norden, alle SCHRITT Grad."""
    bild = bild.convert("RGB")
    w, h = bild.size
    cx, cy = w / 2, h / 2
    radius = min(w, h) / 2
    profil = []
    for grad in range(0, 360, SCHRITT):
        rad = math.radians(grad)
        werte = []
        r = radius * RING[0]
        while r < radius * RING[1]:
            rgb = bild.getpixel((int(cx + r * math.sin(rad)), int(cy - r * math.cos(rad))))
            if not _punkt(rgb):
                werte.append(sum(rgb) / 3)
            r += 2
        profil.append(statistics.median(werte) if werte else 0.0)
    return profil


def blickrichtung(bild) -> float | None:
    """Richtung des Sichtkegels in Grad (0 = Nord, 90 = Ost) oder None, wenn kein Kegel zu sehen ist.
    Bewertet wird ein ganzes Kegelfenster statt einzelner Richtungen, damit helle Flecken nicht stören."""
    profil = helligkeit_je_richtung(bild)
    n, breite = len(profil), KEGEL // SCHRITT
    fenster = [sum(profil[(i + j) % n] for j in range(breite)) / breite for i in range(n)]
    best = max(range(n), key=lambda i: fenster[i])
    if fenster[best] - statistics.median(profil) < MIN_KONTRAST:
        return None
    return (best * SCHRITT + KEGEL / 2 - SCHRITT / 2) % 360


def kurs(grad: float) -> tuple[float, float]:
    """Richtung als Einheitsvektor in Weltkoordinaten wie RadarZustand.kurs (Norden = Welt -y, Osten = +x)."""
    rad = math.radians(grad)
    return (math.sin(rad), -math.cos(rad))


def lesen(bereich: list[int]):
    """Bildschirmausschnitt [x, y, Breite, Höhe] (Bildschirm-Pixel). None, wenn kein X-Bildschirm da ist."""
    from PIL import ImageGrab  # erst hier: Tests und Mitschnitt-Auswertung brauchen keinen Bildschirm

    x, y, w, h = bereich
    try:
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=None)
    except OSError:
        return None
