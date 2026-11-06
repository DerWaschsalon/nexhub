"""Boss-Ansagen nach dem A2Tools-Plugin: Pakete, Bosserkennung, Phasen, Wellen, Reihenfolge, Stil, Sprecher."""
import json
import struct
import threading
import unittest
from pathlib import Path

from radar.ansagen import Ansagen
from radar.warnung import DUNGEONS, Sprecher, WarnZentrale
from radar.zustand import BOSS_ANSAGEN, RadarZustand

from test_feldbosse_vertraute import varint  # Testordner ist beim Aufruf die Wurzel


def text(de: str, en: str = "") -> dict:
    return {"de": de, "en": en or de}


# Kleine Liste im Format von ansagen.json (Werte wie im Plugin)
DATEN = {
    "sicher": text("Wieder angreifen", "Safe to attack"),
    "bosse": {
        "thamon": {"name": text("Thamon"), "dungeon": "Vakron Sky Island", "skills": [1604600]},
        "vakron": {"name": text("Vakron"), "dungeon": "Vakron Sky Island", "skills": [1604370]},
        "talisra": {"name": text("Talisra"), "dungeon": "Shattered Arkanis", "skills": []},
    },
    "rufe": [
        {"schluessel": "thamon-violet", "art": "leiste", "id": 1604670, "boss": "thamon", "gruppe": "ansage_thamon", "vorlauf": 1.79,
         "zeile": text("Violettes Licht schießt empor!"), "anweisung": text("Lila — keine Magieangriffe"),
         "phase": {"effekt": 16046701, "sekunden": 10.0, "anzeige": text("Keine Magie"),
                   "name": text("Mystisches Gebrüll")}},
        {"schluessel": "vakron-jump", "art": "skill", "id": 1604390, "boss": "vakron", "gruppe": "ansage_vakron",
         "zeile": text("Die Wut der Erde …"), "anweisung": text("Springen!"), "wellen": True},
        {"schluessel": "abnormal:10000008:vakron", "art": "effekt", "id": 10000008, "boss": "vakron", "gruppe": "ansage_vakron",
         "zeile": text("Ich werde jene bestrafen …"), "buff": text("Raserei"), "braucht_boss": True},
        {"schluessel": "talisra-dark", "art": "skill", "id": 1801730, "boss": "talisra", "gruppe": "ansage_talisra",
         "anweisung": text("Dunkel"), "reihe": "speere"},
        {"schluessel": "talisra-light", "art": "skill", "id": 1801735, "boss": "talisra", "gruppe": "ansage_talisra",
         "anweisung": text("Licht"), "reihe": "speere"},
    ],
}


class AnsagenTest(unittest.TestCase):
    def setUp(self):
        self.t = [100.0]
        self.zustand = RadarZustand()
        self.z = WarnZentrale(self.zustand, uhr=lambda: self.t[0])
        self.z.an = True
        self.z.k = {"meldung_aus": [], "warnton": {}, "sprache": "de", "ansage_stil": "beides",
                    "wellen_ton": True, "eigene_worte": {}, "ruf_aus": []}
        self.a = Ansagen(self.z, DATEN)

    def anzeige(self):
        return [(w.regel.titel, w.regel.hinweis, round(w.rest(self.t[0]), 2)) for w in self.z.schnappschuss()]

    def test_leiste_mit_anweisung_und_zeile(self):
        self.a.leiste(70, 1604670)
        self.assertEqual(self.anzeige(), [("Lila — keine Magieangriffe", "Violettes Licht schießt empor!", 1.79)])
        self.assertEqual(self.z.laut, [("ansage", "Lila — keine Magieangriffe"),
                                       ("zeile", "Violettes Licht schießt empor!")])

    def test_stil_nur_zeile_und_nur_anweisung(self):
        self.z.k["ansage_stil"] = "zeile"
        self.a.leiste(70, 1604670)
        self.assertEqual(self.z.laut, [("ansage", "Violettes Licht schießt empor!")])
        self.z.laut.clear()
        self.t[0] += 5
        self.z.k["ansage_stil"] = "anweisung"
        self.a.leiste(70, 1604670)
        self.assertEqual(self.z.laut, [("ansage", "Lila — keine Magieangriffe")])

    def test_phase_mit_echter_dauer_und_wieder_angreifen(self):
        self.a.leiste(70, 1604670)
        self.t[0] += 1.8
        self.z.laut.clear()
        self.a.effekt(70, 3, 16046701, 8.5)  # Buff liegt 8,5 s (nicht die 10 s aus der Liste)
        self.assertEqual(self.anzeige(), [("Keine Magie", "Mystisches Gebrüll", 8.5)])
        self.assertEqual(self.z.laut, [])  # Anweisung kam eben schon
        self.t[0] += 8.5
        self.a.takt()
        self.assertEqual(self.anzeige()[0][:2], ("Wieder angreifen", "Thamon"))
        self.assertEqual(self.z.laut, [("ansage", "Wieder angreifen")])

    def test_phase_endet_frueher(self):
        self.a.effekt(70, 3, 16046701, 10.0)
        self.assertEqual(self.z.laut, [("ansage", "Keine Magie")])  # ohne Leiste davor: jetzt sagen
        self.t[0] += 2
        self.a.effekt_weg(70, 3)
        self.assertEqual(self.anzeige()[0][0], "Wieder angreifen")

    def test_piep_je_welle(self):
        self.a.skill(80, 1604390)
        self.z.laut.clear()
        for nach in (1.7, 1.8, 3.4, 5.1, 9.5):  # 1,8 = zweites Geschoss derselben Welle, 9,5 zu spät
            self.t[0] = 100 + nach
            self.a.welle(80, 1604390)
        self.assertEqual(self.z.laut, [("welle", "")] * 3)

    def test_wellen_ton_aus(self):
        self.z.k["wellen_ton"] = False
        self.a.skill(80, 1604390)
        self.t[0] += 1.7
        self.z.laut.clear()
        self.a.welle(80, 1604390)
        self.assertEqual(self.z.laut, [])

    def test_raserei_nur_bei_erkanntem_boss(self):
        self.a.effekt(80, 1, 10000008, 30)  # Wesen unbekannt: jedes Monster kann Raserei bekommen
        self.assertEqual(self.anzeige(), [])
        self.a.skill(80, 1604370)  # eigener Skill von Vakron: jetzt ist das Wesen bekannt
        self.t[0] += 5
        self.a.effekt(80, 2, 10000008, 30)
        self.assertEqual(self.anzeige(), [("Ich werde jene bestrafen …", "Raserei", 4.0)])

    def test_reihenfolge_der_speere(self):
        for skill in (1801730, 1801730, 1801735):
            self.a.skill(90, skill)
            self.t[0] += 2
        self.assertEqual(self.anzeige()[0][0], "Dunkel → Dunkel → Licht")
        self.t[0] += 7
        self.a.skill(90, 1801735)  # lange danach: neue Reihe
        self.assertEqual(self.anzeige()[0][0], "Licht")

    def test_doppelter_ausloeser_einmal(self):
        self.a.leiste(70, 1604670)
        self.t[0] += 0.5
        self.a.leiste(70, 1604670)
        self.assertEqual(len(self.z.laut), 2)  # Anweisung und Zeile, nicht doppelt

    def test_englisch(self):
        self.z.k["sprache"] = "en"
        self.a.skill(80, 1604390)
        self.assertEqual(self.anzeige()[0][0], "Springen!")  # Testdaten: englisch = deutsch

    def test_abgeschalteter_boss_und_anderer_dungeon(self):
        self.z.k["meldung_aus"] = ["ansage_thamon"]
        self.a.leiste(70, 1604670)
        self.assertEqual(self.anzeige(), [])
        self.z.k["meldung_aus"] = []
        self.zustand.dungeon = "Draupnir"
        self.a.leiste(70, 1604670)
        self.assertEqual(self.anzeige(), [])

    def test_eigene_worte_statt_des_rufs(self):
        self.z.k["eigene_worte"] = {"thamon-violet": "Lila, Magie stopp"}
        self.a.leiste(70, 1604670)
        self.assertEqual(self.anzeige(), [("Lila, Magie stopp", "Thamon", 1.79)])
        self.assertEqual(self.z.laut, [("ansage", "Lila, Magie stopp")])

    def test_abgehakter_ruf_ganz_aus(self):
        self.z.k["ruf_aus"] = ["thamon-violet"]
        self.a.leiste(70, 1604670)
        self.a.effekt(70, 3, 16046701, 10)  # auch sein Countdown
        self.assertEqual(self.anzeige(), [])

    def test_vorschau_mit_phase_und_wieder_angreifen(self):
        self.z.k["ruf_aus"] = ["thamon-violet"]  # gilt auch für einen abgehakten Ruf
        self.a.testen("thamon-violet")
        self.assertEqual(self.anzeige()[0][0], "Lila — keine Magieangriffe")
        self.t[0] += 1.79
        self.a.takt()
        self.assertEqual(self.anzeige(), [("Keine Magie", "Mystisches Gebrüll", 5.0)])
        self.t[0] += 5
        self.a.takt()
        self.assertEqual(self.anzeige()[0][0], "Wieder angreifen")


class DatenTest(unittest.TestCase):
    def test_jeder_ruf_hat_boss_schalter_und_text(self):
        for ruf in BOSS_ANSAGEN["rufe"]:
            boss = BOSS_ANSAGEN["bosse"][ruf["boss"]]
            self.assertIn(ruf["gruppe"], DUNGEONS[boss["dungeon"]], ruf)
            self.assertTrue(ruf.get("zeile") or ruf.get("anweisung") or ruf.get("buff"), ruf)

    def test_seitenliste(self):
        from radar.ansagen import seitenliste
        liste = seitenliste()
        self.assertEqual(sum(len(r) for r in liste.values()), len({r["schluessel"] for r in BOSS_ANSAGEN["rufe"]}))
        self.assertIn({"schluessel": "vakron-jump", "art": "Fertigkeit", "vorgabe": "Springen!",
                       "zeile": "Die Wut der Erde wird alle Hochmütigen strafen, die es wagen, ihren Fuß auf "
                                "diesen Boden zu setzen!"}, liste["ansage_vakron"])

    def test_ansage_ersetzt_eigene_regel(self):
        mechaniken = json.loads((Path(__file__).parents[1] / "radar" / "mechaniken.json").read_text())
        eigene = {s for m in mechaniken["mechaniken"] for s in m["wann"].get("skills", [m["wann"].get("id")])}
        ansagen = {r["id"] for r in BOSS_ANSAGEN["rufe"]}
        self.assertFalse(eigene & ansagen)


class PaketeTest(unittest.TestCase):
    def setUp(self):
        self.z = RadarZustand()
        self.gesehen = []

    def test_leiste_und_welle(self):
        self.z.bei_leiste.append(lambda *a: self.gesehen.append(("leiste", *a)))
        self.z.bei_welle.append(lambda *a: self.gesehen.append(("welle", *a)))
        self.z.verarbeiten(0x3809, varint(3199) + b"\x02" + struct.pack("<I", 1604670) + b"\x01\x02")
        self.z.verarbeiten(0x3803, varint(3199) + b"\x00" + varint(5000) + struct.pack("<I", 1604390))
        self.assertEqual(self.gesehen, [("leiste", 3199, 1604670), ("welle", 3199, 1604390)])

    def test_effekt_mit_dauer_und_ende(self):
        self.z.bei_effekt.append(lambda *a: self.gesehen.append(("an", *a)))
        self.z.bei_effekt_weg.append(lambda *a: self.gesehen.append(("weg", *a)))
        self.z.effekt_ids = {16046701}
        # Entity, 01, Flags, Instanz, Effekt-ID, Dauer i64 ms, Ende i64 ms (A2Tools capture/abnormal.rs)
        an = varint(70) + b"\x01\x00" + varint(300) + struct.pack("<Iqq", 16046701, 8500, 0)
        self.z.verarbeiten(0x382A, an)
        self.z.verarbeiten(0x382C, varint(70) + b"\x01\x01" + varint(300) + b"\x01")
        self.assertEqual(self.gesehen, [("an", 70, 300, 16046701, 8.5), ("weg", 70, 300)])


class Prozess:
    """Ein abspielender Satz, den der Test selbst beendet."""

    def __init__(self, text, log):
        self.text, self.log, self.fertig = text, log, threading.Event()

    def wait(self):
        self.fertig.wait(2)

    def terminate(self):
        self.log.append(("abgebrochen", self.text))
        self.fertig.set()


class SprecherTest(unittest.TestCase):
    def test_wichtig_bricht_boss_zeile_ab(self):
        log, laeuft = [], []
        gestartet = threading.Semaphore(0)

        def spielen(datei):
            p = Prozess(str(datei), log)
            laeuft.append(p)
            gestartet.release()
            return p
        s = Sprecher(spielen)
        s.sagen("eins", wichtig=False)
        gestartet.acquire(timeout=2)
        s.sagen("zwei", wichtig=False)
        s.sagen("drei", wichtig=False)  # zwei warten schon: fällt weg
        self.assertEqual([t for t, _ in s.warten], ["zwei"])
        s.sagen("jetzt", wichtig=True)  # bricht die Boss-Zeile ab und verwirft den Stau
        self.assertEqual([t for t, _ in s.warten], ["jetzt"])
        self.assertEqual(len(log), 1)
        for p in laeuft:
            p.fertig.set()


if __name__ == "__main__":
    unittest.main()
