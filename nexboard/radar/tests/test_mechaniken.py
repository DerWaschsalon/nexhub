"""Boss-Mechaniken aus mechaniken.json, Treffer, Stagger-Pruefung, Berserker, Gruppen-LP, Cube-Schluessel."""
import json
import struct
import time
import unittest
from pathlib import Path

from radar.warnung import DUNGEONS, ENGLISCH, FARBEN, STAGGER_REGELN, WarnZentrale
from radar.zustand import BOSSE, CUBE_SCHLUESSEL, MECHANIKEN, RadarZustand

from tests.test_radar import varint

RAUR, THAMON, BERK = 2300206, 2300811, 2300171


class DatenTest(unittest.TestCase):
    def test_jede_mechanik_hat_schalter_farbe_und_boss(self):
        for m in MECHANIKEN:
            self.assertIn(m["gruppe"], DUNGEONS[m["dungeon"]], m["gruppe"])
            self.assertIn(m["farbe"], FARBEN)
            self.assertTrue(all(BOSSE[npc] == m["dungeon"] for npc in m["bosse"]), m["gruppe"])
            for text in (m["titel"], m["hinweis"], m["meldung"]):  # alles hat eine englische Fassung
                self.assertIn(text, ENGLISCH, f"{m['gruppe']}: {text}")

    def test_meldungen_ist_gueltiges_json(self):
        json.loads((Path(__file__).parents[1] / "radar" / "meldungen.json").read_text())


class WarnungTest(unittest.TestCase):
    def setUp(self):
        self.t = [100.0]
        self.zustand = RadarZustand()
        self.zustand.eigene_eid = 5
        self.zustand.spieler.update({5: "Ich", 9: "Anna"})
        self.zustand.bosse.update({70: RAUR, 71: THAMON, 72: BERK})
        self.z = WarnZentrale(self.zustand, uhr=lambda: self.t[0])
        self.z.an = True
        self.z.k = {"meldung_aus": [], "warnton": {}}

    def warnungen(self):
        return [(w.titel(), w.regel.hinweis_ich if w.ich else w.regel.hinweis) for w in self.z.schnappschuss()]

    def test_effekt_auf_dem_boss_und_danach(self):
        self.z.status(9, 15044501)  # Konter auf einem Spieler zaehlt nicht
        self.assertEqual(self.warnungen(), [])
        self.z.status(70, 15044501)
        self.assertEqual(self.warnungen(), [("Konter-Haltung", "Nicht angreifen, zurückgehen")])
        self.t[0] += 4.9  # nach dem Einschlag: Folge-Hinweis derselben Gruppe
        self.assertEqual(self.warnungen(), [("Konter-Haltung", "Abstand halten")])

    def test_effekt_auf_mitspieler_nennt_ihn(self):
        self.z.status(5, 16047201)  # auf mir: diese Regel gilt nur fuer Mitspieler
        self.assertEqual(self.warnungen(), [])
        self.z.status(9, 16047201)
        self.assertEqual(self.warnungen(), [("Versteinert auf Anna", "Befreien")])

    def test_effekt_auf_jedem_spieler(self):
        self.z.status(9, 16056701)  # Nazmun-Bombe beim anderen: Abstand halten
        self.assertEqual(self.warnungen(), [("Bombe auf Anna", "Abstand halten")])
        self.t[0] += 10
        self.z.status(5, 16056701)  # bei mir: weg von der Gruppe
        self.assertEqual(self.warnungen(), [("Bombe  –  DU!", "Weg von der Gruppe!")])
        self.t[0] += 20
        self.z.status(5, 16010302)  # Auldor: auch bei mir zusammenstellen
        self.assertEqual(self.warnungen(), [("Sturmstreich  –  DU!", "Zusammenstellen")])

    def test_treffer_und_cast(self):
        self.z.treffer(1605144)
        self.z.cast(1, 1604532, None)
        self.assertEqual(sorted(t for t, _ in self.warnungen()), ["Giftpfütze", "Rotation"])

    def test_pfuetze_meldet_nicht_im_sekundentakt(self):
        for _ in range(5):
            self.z.treffer(1605144)
            self.t[0] += 0.3
        self.assertEqual(len(self.z.laut), 1)
        self.t[0] += 2
        self.z.treffer(1605144)  # Warnung abgelaufen, immer noch drin: wieder melden
        self.assertEqual(len(self.z.laut), 2)

    def test_staggern_endet_mit_groggy(self):
        self.z.staggern(70)  # Raur hat keine Stagger-Pruefung
        self.assertEqual(self.warnungen(), [])
        self.z.staggern(72)
        self.assertEqual(self.warnungen(), [("Jetzt staggern", "Leiste brechen")])
        self.z.groggy(72)
        self.assertEqual([t for t, _ in self.warnungen()], ["Boss groggy"])

    def test_wenig_lp_einmal_bis_zur_erholung(self):
        self.z.gruppe_lp(9, 0.2)
        self.z.gruppe_lp(9, 0.1)
        self.assertEqual(self.warnungen(), [("Wenig LP auf Anna", "Unter 25 %")])
        self.assertEqual(len(self.z.laut), 1)
        self.z.gruppe_lp(9, 0.8)
        self.t[0] += 10
        self.z.gruppe_lp(9, 0.2)
        self.assertEqual(len(self.z.laut), 2)

    def test_berserker_in_der_vorschau(self):
        self.zustand.berserker[72] = self.t[0] + 90
        self.assertEqual(self.z.vorschau(), [("Berserker", 90.0)])

    def test_lernhilfe_pro_boss(self):
        self.zustand.dungeon = "Ferocious Horn Den"
        self.zustand.bosse.update({80: 2300908, 81: 2300910})  # Kwapo mit Cast-Warnung, Nuakum noch ohne
        self.z.cast(81, 1910261, 1)  # Nuakum: grau zeigen, damit man ihn auswerten kann
        self.assertEqual([w.regel.gruppe for w in self.z.schnappschuss()], ["casts"])
        self.t[0] += 10
        self.z.cast(80, 1606999, 1)  # unbekannter Cast von Kwapo: keine Lernhilfe mehr
        self.assertEqual([w.regel.gruppe for w in self.z.schnappschuss()], [])
        self.z.cast(80, 1606910, 1)  # bekannte Mechanik
        self.assertEqual([w.titel() for w in self.z.schnappschuss()], ["Donnergrollen"])


class PaketeTest(unittest.TestCase):
    def setUp(self):
        self.z = RadarZustand()
        self.z.eigene_eid = 37109

    def test_treffer_auf_mir(self):
        treffer = []
        self.z.bei_treffer.append(treffer.append)
        self.z.treffer_ids = {18010340}
        # echte Nachricht aus glass-cannon (damage.rs): Ziel 37109, Angreifer 3199, Skill 18010340
        p = bytes.fromhex("f5 a1 02 04 00 ff 18 e4 d0 12 01 62 03 0d 20 59 6b 02 00 00 00 96 56 f2 14 02 00")
        self.z.verarbeiten(0x3804, p)
        self.z.eigene_eid = 1  # trifft einen anderen: nichts
        self.z.verarbeiten(0x3804, p)
        self.assertEqual(treffer, [18010340])

    def leiste(self, eid: int, bereit: bool) -> bytes:
        return varint(eid) + b"\x03\x01" + struct.pack("<II", 557, 300) + bytes([0x02 if bereit else 0])

    def test_stagger_pruefung(self):
        staggern = []
        self.z.bei_staggern.append(staggern.append)
        self.z.bosse.update({72: BERK, 70: RAUR})
        self.z.boss_seit.update({72: time.time() - 60, 70: time.time() - 60})
        self.z.verarbeiten(0xE005, self.leiste(70, True))  # Raur: keine Pruefung
        self.z.verarbeiten(0xE005, self.leiste(72, True))  # spaet erschienen und brechbar
        self.z.verarbeiten(0xE005, self.leiste(72, True))  # weiter brechbar: nicht nochmal
        self.z.verarbeiten(0xE005, self.leiste(72, False))  # Pause
        self.z.verarbeiten(0xE005, self.leiste(72, True))  # wieder brechbar
        self.assertEqual(staggern, [72, 72])
        self.assertIn(BERK, STAGGER_REGELN)

    def test_leiste_von_anfang_an_ist_keine_pruefung(self):
        staggern = []
        self.z.bei_staggern.append(staggern.append)
        self.z.bosse[72] = BERK
        self.z.boss_seit[72] = time.time()
        self.z.verarbeiten(0xE005, self.leiste(72, True))
        self.assertEqual(staggern, [])

    def test_berserker_zeit(self):
        self.z.bosse[72] = BERK
        self.z.verarbeiten(0x8D21, varint(72) + b"\x01\x01" + struct.pack("<Q", 1792745600000))
        self.assertEqual(self.z.berserker, {72: 1792745600.0})
        self.z.verarbeiten(0x8D21, varint(72) + b"\x00\x00")  # Kampf vorbei
        self.assertEqual(self.z.berserker, {})

    def test_gruppen_lp(self):
        lp = []
        self.z.bei_gruppe_lp.append(lambda eid, anteil: lp.append((eid, anteil)))
        self.z.verarbeiten(0x921B, varint(9) + varint(250) + varint(1000) + bytes(25))
        self.z.verarbeiten(0x921B, varint(37109) + varint(1) + varint(1000) + bytes(25))  # ich: nicht
        self.assertEqual(lp, [(9, 0.25)])

    def test_cube_schluessel(self):
        self.z.verarbeiten(0x363A, varint(400) + b"\x01" + struct.pack("<I", CUBE_SCHLUESSEL))
        self.z.verarbeiten(0x363A, varint(401) + b"\x01" + struct.pack("<I", 12345))
        self.assertEqual(self.z.schluessel, 1)


class FlaecheTest(unittest.TestCase):
    def setUp(self):
        self.t = [100.0]
        self.z = RadarZustand()
        self.z.eigene_eid = 5
        self.z.spieler[9] = "Anna"
        self.z.position = (1000.0, 2000.0, 0.0)
        self.zentrale = WarnZentrale(self.z, uhr=lambda: self.t[0])
        self.zentrale.an = True
        self.zentrale.k = {"meldung_aus": [], "warnton": {}}
        self.z.bei_flaeche.append(self.zentrale.flaeche)

    def markierung(self, caster: int, x: float, y: float, ms: int = 2850) -> None:
        # Aufbau wie in glass-cannon (cast.rs): Caster, Skill, Cast-ID, u32, u16, x/y/z, Richtung, ms
        p = varint(caster) + struct.pack("<IBIH", 1226350, 2, 1, 0) + struct.pack("<ffff", x, y, 0.0, 0.0) \
            + struct.pack("<H", ms)
        self.z.verarbeiten(0x3848, p)

    def test_flaeche_unter_mir(self):
        self.markierung(70, 1000.0 + 900, 2000.0)  # 9 m daneben: nichts
        self.assertEqual(self.zentrale.schnappschuss(), [])
        self.markierung(70, 1000.0 + 300, 2000.0)  # 3 m: Warnung mit Countdown
        w = self.zentrale.schnappschuss()
        self.assertEqual([(x.titel(), x.ich, x.regel.vorlauf) for x in w], [("Fläche unter dir  –  DU!", True, 2.85)])
        for _ in range(5):  # weitere Markierungen derselben Welle: keine neue Ansage
            self.markierung(70, 1000.0, 2000.0)
        self.assertEqual(len(self.zentrale.laut), 1)

    def test_eigene_und_spieler_markierungen_zaehlen_nicht(self):
        self.markierung(5, 1000.0, 2000.0)
        self.markierung(9, 1000.0, 2000.0)
        self.assertEqual(self.zentrale.schnappschuss(), [])

    def test_ohne_position_nichts(self):
        self.z.position = None
        self.markierung(70, 1000.0, 2000.0)
        self.assertEqual(self.zentrale.schnappschuss(), [])
