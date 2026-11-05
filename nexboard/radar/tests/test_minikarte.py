import math
import random
import unittest

from PIL import Image, ImageDraw

from radar.minikarte import blickrichtung, kurs


def karte(kegel_mitte: float | None) -> Image.Image:
    """Minikarte wie im Spiel: dunkle, fleckige Landschaft, heller Sichtkegel (50 Grad) von der Mitte aus,
    darauf weiße Quest-Punkte, die den Kegel nicht verfälschen dürfen."""
    zufall = random.Random(1)
    bild = Image.new("RGB", (310, 214), (55, 75, 45))
    malen = ImageDraw.Draw(bild)
    for _ in range(300):  # Gelände
        x, y = zufall.randrange(310), zufall.randrange(214)
        malen.ellipse((x, y, x + 12, y + 12), fill=(zufall.randrange(40, 90), zufall.randrange(60, 100), 40))
    if kegel_mitte is not None:
        cx, cy, r = 155, 107, 200
        ecken = [(cx, cy)]
        for grad in (kegel_mitte - 25, kegel_mitte + 25):
            rad = math.radians(grad)
            ecken.append((cx + r * math.sin(rad), cy - r * math.cos(rad)))
        malen.polygon(ecken, fill=(170, 175, 150))
    for _ in range(25):  # Quest-Punkte überall
        x, y = zufall.randrange(20, 290), zufall.randrange(20, 194)
        malen.ellipse((x, y, x + 8, y + 8), fill=(250, 250, 250))
    return bild


def winkelabstand(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


class BlickrichtungTest(unittest.TestCase):
    def test_richtung_des_kegels(self):
        for soll in (0, 55, 140, 270, 330):
            ist = blickrichtung(karte(soll))
            self.assertIsNotNone(ist, soll)
            self.assertLessEqual(winkelabstand(ist, soll), 5, soll)

    def test_ohne_kegel_keine_richtung(self):
        self.assertIsNone(blickrichtung(karte(None)))

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
