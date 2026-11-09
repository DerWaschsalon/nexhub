import json
import struct
import unittest

from tests.test_radar import varint

from radar.pvp import OP_SAISON, OP_TOD, grad_name
from radar.zustand import RadarZustand


def text(s: str) -> bytes:
    roh = s.encode() + b"\0"
    return varint(len(roh)) + roh


def tod(opfer: int, taeter: int = 0, name: str = "") -> bytes:
    """CharDie_NT wie im Mitschnitt: Opfer, Skill, Taeter, Server, Name, Gilde, Wappen, NPC, Aktion, Grund, Art."""
    return (varint(opfer) + struct.pack("<i", 1234) + varint(taeter) + struct.pack("<H", 2302) + text(name)
            + text("") + struct.pack("<H", 0) + varint(0) + struct.pack("<i", 0) + b"\x01\x02")


def saison(rang: int, punkte: int, kills: int, tode: int, assists: int, art: int = 1) -> bytes:
    zusatz = json.dumps({"kill_count": kills, "death_count": tode, "assist_count": assists})
    return (struct.pack("<HBBiq", 0, art, 0, rang, 1) + text("Navonex") + text("Gilde")
            + struct.pack("<Hiib", 2, 45, 0, 9) + struct.pack("<q", punkte) + text(zusatz)
            + struct.pack("<iiiiiq", 5, 0, 18, 12, 10000, 0))


class Sitzung(unittest.TestCase):
    def setUp(self):
        self.z = RadarZustand("Navonex")
        self.z.eigene_eid, self.z.eid_sicher = 100, True
        self.z.spieler = {100: "Navonex", 200: "Feind", 300: "Freund"}

    def test_kills_und_tode_nur_gegen_spieler(self):
        z = self.z
        z.verarbeiten(OP_TOD, tod(200, 100, "Navonex"))   # eigener Kill
        z.verarbeiten(OP_TOD, tod(300, 555, "Navonex"))   # Kill eines Begleiters: zaehlt ueber den Namen
        z.verarbeiten(OP_TOD, tod(200, 777, "Andere"))    # fremder Kill
        z.verarbeiten(OP_TOD, tod(100, 777, "Feind"))     # von einem Spieler getoetet
        z.verarbeiten(OP_TOD, tod(100))                   # von einem Monster: kein PvP
        z.verarbeiten(OP_TOD, tod(999, 100, "Navonex"))   # Monster getoetet
        s = z.pvp.stand()
        self.assertEqual((s["kills"], s["tode"], s["assists"]), (2, 1, None))
        self.assertEqual(s["letzte"], [("tod", "Feind"), ("kill", "Freund"), ("kill", "Feind")])

    def test_geschaetzte_eigene_id_zaehlt_keine_tode(self):
        self.z.eid_sicher = False
        self.z.verarbeiten(OP_TOD, tod(100, 777, "Feind"))
        self.assertEqual(self.z.pvp.stand()["tode"], 0)

    def test_saisonwertung_liefert_zuwachs(self):
        z = self.z
        z.verarbeiten(OP_SAISON, saison(1102, 586688, 184, 73, 354))
        z.verarbeiten(OP_TOD, tod(200, 100, "Navonex"))
        z.verarbeiten(OP_SAISON, saison(1090, 588000, 187, 73, 360))
        s = z.pvp.stand()
        self.assertEqual((s["kills"], s["tode"], s["assists"]), (3, 0, 6))
        self.assertEqual((s["punkte"], s["rang"], s["rang_plus"], s["grad"]), (1312, 1090, 12, "Soldat Rang 9"))
        z.pvp.zuruecksetzen()
        self.assertEqual((z.pvp.stand()["kills"], z.pvp.stand()["punkte"]), (0, 0))

    def test_andere_wertung_und_kaputte_daten_aendern_nichts(self):
        self.z.verarbeiten(OP_SAISON, saison(1, 1, 1, 1, 1, art=2))
        self.z.verarbeiten(OP_SAISON, b"\x00\x00\x01")
        self.z.verarbeiten(OP_TOD, b"\x80")
        self.assertIsNone(self.z.pvp.saison)

    def test_grad_namen(self):
        self.assertEqual([grad_name(g) for g in (1, 5, 9, 10, 18, 19, 0)],
                         ["Oberbefehlshaber", "5-Sterne-Offizier", "1-Sterne-Offizier", "Soldat Rang 1",
                          "Soldat Rang 9", "Rekrut", ""])


class TodesursacheTest(unittest.TestCase):
    def setUp(self):
        from radar.warnung import TODESMAL, WarnZentrale
        self.t = [1000.0]
        self.z = RadarZustand("Ich")
        self.z.eigene_eid, self.z.eid_sicher = 100, True
        self.z.spieler[300] = "Anna"
        self.zentrale = WarnZentrale(self.z, uhr=lambda: self.t[0])
        self.zentrale.an = True
        self.zentrale.k = {"meldung_aus": [], "warnton": {}}
        self.zentrale.cast(1, TODESMAL, 300)
        self.t[0] += 4.1

    def tode(self, *nachrichten: bytes) -> list[dict]:
        from collections import deque
        from types import SimpleNamespace

        from radar.dienst import RadarDienst
        dienst = SimpleNamespace(zustand=self.z, zentrale=self.zentrale, tode=deque())
        self.z.bei_tod.append(lambda *a: RadarDienst._tod(dienst, *a))
        for p in nachrichten:
            self.z.verarbeiten(OP_TOD, p)
        return list(dienst.tode)

    def test_tod_durch_monster_mit_warnung(self):
        tode = self.tode(tod(300), tod(100), tod(999), tod(300, 555, "Spieler"))
        # Anna und ich durch ein Monster; ein totes Monster (999) und PvP zaehlen nicht
        self.assertEqual([(d["name"], d["skill"], d["warning"], d["lead_ms"]) for d in tode],
                         [("Anna", 1234, "Todesmal", 4100), ("Ich", 1234, "Todesmal", 4100)])
        self.assertEqual(tode[0]["t_ms"], 1_004_100)

    def test_ohne_laufende_warnung(self):
        self.t[0] += 30
        self.assertEqual(self.tode(tod(300))[0]["warning"], None)


class KampfAbfrageTest(unittest.TestCase):
    setUp = TodesursacheTest.setUp  # dieselbe Lage: Todesmal auf Anna

    def test_laufende_warnungen_und_groggy(self):
        from types import SimpleNamespace

        from radar.dienst import RadarDienst
        self.t[0] -= 4.0  # Todesmal auf Anna laeuft noch 4 s
        self.zentrale.status(100, 16008401)  # Ignus-Bombe auf mir
        dienst = SimpleNamespace(zustand=self.z, zentrale=self.zentrale)
        k = RadarDienst.kampf(dienst)
        self.assertFalse(k["groggy"])
        self.assertEqual([(w["gruppe"], w["ich"]) for w in k["warnungen"]], [("flamme", False), ("bombe", True)])
        self.assertTrue(all(w["rest"] > 0 for w in k["warnungen"]))
