import math
import random
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from radar.minikarte import blickrichtung, kurs

DATEN = Path(__file__).parent / "daten"


def karte(blick: float | None) -> Image.Image:
    """Minikarte wie im Spiel: fleckige Landschaft, heller Innenkreis, zwei weiße Linien um die
    Blickrichtung (112 Grad auseinander) und weiße Quest-Punkte, die nichts verfälschen dürfen."""
    zufall = random.Random(1)
    bild = Image.new("RGB", (238, 238), (120, 110, 80))
    malen = ImageDraw.Draw(bild)
    for _ in range(300):  # Gelände
        x, y = zufall.randrange(238), zufall.randrange(238)
        malen.ellipse((x, y, x + 12, y + 12), fill=(zufall.randrange(70, 150), zufall.randrange(70, 140), 60))
    malen.ellipse((62, 62, 176, 176), fill=(190, 170, 130))
    if blick is not None:
        for grad in (blick - 56, blick + 56):
            rad = math.radians(grad)
            malen.line((119 + 57 * math.sin(rad), 119 - 57 * math.cos(rad),
                        119 + 170 * math.sin(rad), 119 - 170 * math.cos(rad)), fill=(250, 245, 230), width=2)
    for _ in range(25):  # Quest-Punkte überall
        x, y = zufall.randrange(10, 220), zufall.randrange(10, 220)
        malen.ellipse((x, y, x + 8, y + 8), fill=(250, 250, 250))
    return bild


def winkelabstand(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


class BlickrichtungTest(unittest.TestCase):
    def test_mitte_zwischen_den_linien(self):
        for soll in (0, 55, 140, 270, 330):
            ist = blickrichtung(karte(soll))
            self.assertIsNotNone(ist, soll)
            self.assertLessEqual(winkelabstand(ist, soll), 5, soll)

    def test_ohne_linien_keine_richtung(self):
        self.assertIsNone(blickrichtung(karte(None)))

    def test_echtes_bild_mit_dunklem_kegel(self):
        # Bild vom 05.11.2026: Pfeil nach Südwest, die Fläche im Kegel ist dunkler als der Rest
        ist = blickrichtung(Image.open(DATEN / "minikarte-suedwest.png"))
        self.assertIsNotNone(ist)
        self.assertLessEqual(winkelabstand(ist, 228), 6)

    def test_kurs_als_weltvektor(self):
        # Norden = Welt -y, Osten = +x (wie RadarZustand.kurs)
        x, y = kurs(0)
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, -1)
        x, y = kurs(90)
        self.assertAlmostEqual(x, 1)
        self.assertAlmostEqual(y, 0)


if __name__ == "__main__":
    unittest.main()
