import tempfile
import unittest
from pathlib import Path

from radar.punkte import Eichung, PunkteDB


def nord_oben(x, y):
    """Testkarte: +x = Nord (oben), +y = Ost (rechts), 1 px = 10 m, Ursprung bei (500, 400)."""
    return 500 + y / 1000, 400 - x / 1000


class EichungTest(unittest.TestCase):
    def test_zwei_punkte_ohne_spiegelung(self):
        e = Eichung()
        for x, y in ((0, 0), (50000, 20000)):
            e.hinzufuegen(x, y, *nord_oben(x, y))
        for x, y in ((-30000, 70000), (12345, -6789)):
            u, v = e.welt_zu_bild(x, y)
            eu, ev = nord_oben(x, y)
            self.assertAlmostEqual(u, eu, places=6)
            self.assertAlmostEqual(v, ev, places=6)
            wx, wy = e.bild_zu_welt(u, v)
            self.assertAlmostEqual(wx, x, places=3)
            self.assertAlmostEqual(wy, y, places=3)

    def test_drei_punkte_affin_mit_spiegelung(self):
        gespiegelt = lambda x, y: (500 - y / 1000, 400 - x / 1000)
        e = Eichung()
        for x, y in ((0, 0), (50000, 20000), (-10000, 40000)):
            e.hinzufuegen(x, y, *gespiegelt(x, y))
        u, v = e.welt_zu_bild(30000, -5000)
        self.assertAlmostEqual(u, gespiegelt(30000, -5000)[0], places=6)
        self.assertAlmostEqual(v, gespiegelt(30000, -5000)[1], places=6)
        self.assertLess(e.fehler_px(), 1e-6)

    def test_ein_punkt_reicht_nicht(self):
        e = Eichung([(0, 0, 1, 1)])
        self.assertFalse(e.fertig)


class PunkteTest(unittest.TestCase):
    def test_gleicher_punkt_wird_zusammengefasst(self):
        with tempfile.TemporaryDirectory() as d:
            db = PunkteDB(Path(d) / "p.json")
            db.eintragen(1000, 1000, 0, 1000295)
            db.eintragen(1100, 1050, 0, 1000295)   # 1,1 m daneben
            db.eintragen(9000, 1000, 0, 1000295)   # 80 m weg
            self.assertEqual([p["anzahl"] for p in db.alle()], [2, 1])
            self.assertEqual(len(PunkteDB(Path(d) / "p.json").alle()), 2)  # gespeichert
            self.assertTrue(db.entfernen(1200, 1000, 500))
            self.assertFalse(db.entfernen(1200, 1000, 500))
            self.assertEqual(len(db.alle()), 1)


if __name__ == "__main__":
    unittest.main()
