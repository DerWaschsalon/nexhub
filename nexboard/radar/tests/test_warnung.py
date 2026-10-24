import unittest

from radar.warnung import FLAECHEN, REGEN, TODESMAL, WarnZentrale
from radar.zustand import RadarZustand


class WarnungTest(unittest.TestCase):
    def setUp(self):
        self.t = [100.0]
        self.zustand = RadarZustand()
        self.zustand.eigene_eid = 5
        self.z = WarnZentrale(self.zustand, uhr=lambda: self.t[0])
        self.z.an = True
        self.z.k = {"meldung_aus": [], "warnton": {"schwert": "aus"}}  # Standard, nicht die eigenen

    def titel(self):
        return sorted(w.regel.titel for w in self.z.schnappschuss())

    def test_regen_kuendigt_flamme_an_und_todesmal_ersetzt_sie(self):
        self.z.cast(1, REGEN, 1)
        self.assertEqual(self.titel(), ["Regen des Hasses", "Teufelsflamme erwartet"])
        self.t[0] += 3.65
        self.z.cast(1, TODESMAL, 9)
        w = [w for w in self.z.schnappschuss() if w.regel.gruppe == "flamme"]
        self.assertEqual([x.regel.titel for x in w], ["Todesmal"])
        self.assertAlmostEqual(self.t[0] - w[0].seit, 3.65)  # Kette laeuft seit dem Regen
        self.assertFalse(w[0].ich)

    def test_abgeschaltete_meldung_kommt_nicht(self):
        self.z.k["meldung_aus"] = ["flamme"]
        self.z.cast(1, REGEN, 1)
        self.assertEqual(self.titel(), ["Regen des Hasses"])

    def test_warnung_aus_anderem_dungeon_kommt_nicht(self):
        self.zustand.dungeon = "Ferocious Horn Den"
        self.z.cast(1, REGEN, 1)
        self.assertEqual(self.titel(), [])

    def test_verzoegerte_explosion_nur_auf_mir(self):
        self.z.status(9, 16008401)  # anderer Spieler: nichts
        self.assertEqual(self.titel(), [])
        self.z.status(5, 16008401)
        self.assertEqual(self.z.laut, [("ansage", "Verzögerte Explosion auf dir")])

    def test_groggy(self):
        self.z.groggy(7)
        self.assertEqual(self.titel(), ["Boss groggy"])

    def test_todesmal_auf_mir(self):
        self.z.cast(1, TODESMAL, 5)
        self.assertTrue(self.z.schnappschuss()[0].ich)

    def test_flaechenphase_plant_regen_und_flamme(self):
        self.z.cast(1, FLAECHEN, 1)
        self.assertEqual([round(r) for _, r in self.z.vorschau()], [22, 30])
        self.t[0] += 12.3
        self.assertEqual(self.titel(), ["Regen des Hasses kommt", "Teufelsflamme erwartet"])

    def test_klon_phase_und_heulende_flamme(self):
        self.z.cast(1, 1801109, 1)
        self.z.cast(1, 1801130, 1)
        self.assertEqual(self.titel(), ["Heulende Flamme", "Klon-Phase"])

    def test_schwert_ohne_ton(self):
        self.z.cast(1, 1801050, 1)
        self.assertEqual(self.titel(), ["Schwert"])
        self.assertEqual(self.z.laut, [])
        self.z.cast(1, 1600720, 1)
        self.assertEqual(self.z.laut, [("ansage", "Gigantisches Beben")])

    def test_todesmal_nennt_den_markierten(self):
        self.zustand.spieler[9] = "Testspieler"
        self.z.cast(1, TODESMAL, 9)
        self.assertEqual(self.z.schnappschuss()[0].titel(), "Todesmal auf Testspieler")
        self.assertEqual(self.z.laut[0], ("ansage", "Todesmal auf Testspieler"))

    def test_lernhilfe_zeigt_boss_casts_in_dungeon_ohne_warnungen(self):
        self.zustand.dungeon = "Ferocious Horn Den"
        self.zustand.bosse[7] = 2300910
        self.z.cast(7, 1910261, 1)
        self.z.cast(8, 1910261, 1)  # kein Boss: nichts
        self.assertEqual([w.regel.gruppe for w in self.z.schnappschuss()], ["casts"])

    def test_regen_zeitfenster(self):
        self.z.cast(1, REGEN, 1)
        self.t[0] += 10
        self.assertEqual(self.z.vorschau()[0][0], "Regen des Hasses frühestens")
        self.t[0] += 40
        self.assertEqual(self.z.vorschau(), [("Regen des Hasses jederzeit möglich", 0.0)])


if __name__ == "__main__":
    unittest.main()
