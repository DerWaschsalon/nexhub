import json
import math
import tempfile
import unittest
from pathlib import Path

from radar.route import Route, rundweg

# Vier Ecken eines Quadrats (100 m Kantenlaenge, in cm) und ein Punkt in der Mitte der Unterkante
ECKEN = [(0, 0), (10000, 0), (10000, 10000), (0, 10000)]


def laenge(punkte, reihenfolge):
    wege = zip(reihenfolge, reihenfolge[1:] + reihenfolge[:1])
    return sum(math.dist(punkte[a], punkte[b]) for a, b in wege)


class RundwegTest(unittest.TestCase):
    def test_quadrat_ohne_kreuzung(self):
        punkte = [ECKEN[0], ECKEN[2], ECKEN[1], ECKEN[3]]  # absichtlich ueber Kreuz
        r = rundweg(punkte)
        self.assertEqual(sorted(r), [0, 1, 2, 3])
        self.assertAlmostEqual(laenge(punkte, r), 40000)

    def test_ein_punkt(self):
        self.assertEqual(rundweg([(5, 5)]), [0])


class RouteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.datei = Path(self.tmp.name) / "route.json"
        Route.anlegen(self.datei, ECKEN)

    def tearDown(self):
        self.tmp.cleanup()

    def test_anlegen_speichert_rundweg(self):
        daten = json.loads(self.datei.read_text())
        self.assertEqual(len(daten["punkte"]), 4)
        self.assertIsNone(daten["offen"])

    def test_start_am_naechsten_punkt(self):
        r = Route(self.datei)
        self.assertEqual(r.naechste(), [])  # ohne Position noch kein Start
        r.position((9000, 9500), 500)
        self.assertEqual(r.naechste(1), [(10000, 10000)])
        self.assertEqual(len(r.naechste()), 3)

    def test_abhaken_in_reichweite(self):
        r = Route(self.datei)
        r.position((-20000, -20000), 6000)  # weit weg: startet, hakt aber nichts ab
        self.assertEqual(r.naechste(1), [(0, 0)])
        r.position((500, 500), 6000)
        self.assertNotIn((0, 0), r.naechste(4))
        self.assertEqual(r.uebrig, 3)

    def test_fortschritt_bleibt_erhalten(self):
        r = Route(self.datei)
        r.position((0, 0), 6000)
        self.assertEqual(Route(self.datei).uebrig, 3)

    def test_ueberspringen_und_neu_starten(self):
        r = Route(self.datei)
        r.position((-20000, -20000), 6000)
        r.ueberspringen()
        self.assertEqual(r.uebrig, 3)
        r.neu_starten()
        self.assertEqual(r.naechste(), [])
        r.position((-20000, -20000), 6000)
        self.assertEqual(r.uebrig, 4)

    def test_offene_vor_und_nach_dem_start(self):
        r = Route(self.datei)
        self.assertEqual(len(r.offene()), 4)
        r.position((0, 0), 6000)
        self.assertEqual(len(r.offene()), 3)
        self.assertEqual(r.offene()[:3], r.naechste())

    def test_runde_fertig(self):
        r = Route(self.datei)
        for p in ECKEN:
            r.position(p, 6000)
        self.assertEqual(r.uebrig, 0)
        self.assertEqual(r.naechste(), [])

    def test_ohne_datei(self):
        r = Route(Path(self.tmp.name) / "fehlt.json")
        self.assertFalse(r.da)
        r.position((0, 0), 6000)
        self.assertEqual(r.naechste(), [])


if __name__ == "__main__":
    unittest.main()
