import json
import struct
import unittest

from test_radar import varint

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
        self.z.eigene_eid = 100
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
