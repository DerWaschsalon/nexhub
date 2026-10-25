import struct
import unittest

from radar.zustand import OP_FELDBOSSE, OP_SEELE, OP_STUFE, OP_VERTRAUTE, RadarZustand


def varint(wert: int) -> bytes:
    roh = bytearray()
    while True:
        roh.append(wert & 0x7F | (0x80 if wert > 0x7F else 0))
        wert >>= 7
        if not wert:
            return bytes(roh)


class FeldbosseVertrauteTest(unittest.TestCase):
    def setUp(self):
        self.z = RadarZustand()  # speichert nichts

    def test_karte_offen(self):
        self.assertFalse(self.z.schnappschuss()["karte_offen"])
        self.z.verarbeiten(OP_FELDBOSSE, b"\0\0" + struct.pack("<IB", 1110, 0))
        self.assertTrue(self.z.schnappschuss()["karte_offen"])
        self.z.karte_offen_zeit -= 3  # keine Abfrage mehr: Karte zu
        self.assertFalse(self.z.schnappschuss()["karte_offen"])

    def test_feldboss_liste(self):
        p = (b"\0\0" + struct.pack("<IB", 1110, 2)
             + b"\x01" + varint(111001) + struct.pack("<fffQ", 100.0, 200.0, 300.0, 1792745536509)
             + b"\x00" + varint(111007) + struct.pack("<Q", 1792755404209))
        self.z.verarbeiten(OP_FELDBOSSE, p)
        self.assertEqual(self.z.feldbosse["111001"]["pos"], (100.0, 200.0, 300.0))
        self.assertTrue(self.z.feldbosse["111001"]["lebt"])
        self.assertFalse(self.z.feldbosse["111007"]["lebt"])
        self.assertAlmostEqual(self.z.feldbosse["111007"]["zeit"], 1792755404.209)

    def test_status_groggy_und_dungeon_zeit(self):
        status, groggy = [], []
        self.z.bei_status.append(lambda ziel, sid: status.append((ziel, sid)))
        self.z.bei_groggy.append(groggy.append)
        self.z.status_ids = {16008401}
        self.z.bosse[1000] = 2300311
        # echte Nachricht aus dem Mitschnitt (Ziel 2489, Status 16008401, 3000 ms)
        self.z.verarbeiten(0x382A, bytes.fromhex("b9 13 01 13 6f d1 44 f4 00 b8 0b 00 00") + bytes(24))
        self.z.verarbeiten(0xE005, varint(1000) + b"\x00\x03\x02")
        self.z.verarbeiten(0x6100, struct.pack("<IBQQ", 600022, 2, 1792742000000, 1792745600000))
        self.assertEqual(status, [(2489, 16008401)])
        self.assertEqual(groggy, [1000])
        self.assertEqual(self.z.dungeon_ende, 1792745600.0)

    def test_cube_alter(self):
        import time
        seit = int((time.time() - 125) * 1000)
        p = (varint(4711) + b"\x04\x00" + struct.pack("<Ifff", 1301199, 1.0, 2.0, 3.0) + bytes(8)
             + b"\x01\x01\x01" + struct.pack("<Q", seit) + bytes(20))
        self.z.verarbeiten(0x3634, p)
        self.assertAlmostEqual(self.z.cubes[4711].seit, seit / 1000)

    def test_cube_wird_geoeffnet_und_mehr_positionen(self):
        import time
        p = (varint(4711) + b"\x04\x00" + struct.pack("<Ifff", 1301199, 1.0, 2.0, 3.0) + bytes(8)
             + b"\x01\x01\x01" + struct.pack("<Q", int(time.time() * 1000)) + bytes(20))
        self.z.verarbeiten(0x3634, p)
        self.z.spieler[9001] = "Defiance"
        self.z.verarbeiten(0x3638, varint(4711) + varint(9001))
        self.assertEqual(self.z.cubes[4711].oeffner, "Defiance")
        self.z.eigene_eid = 77
        self.z.verarbeiten(0x382B, varint(77) + bytes(20) + struct.pack("<fff", 100.0, 200.0, 300.0))
        self.assertEqual(self.z.position, (100.0, 200.0, 300.0))

    def test_vertraute_stand_seele_und_stufe(self):
        p = (struct.pack("<I", 1044) + varint(1) + struct.pack("<III", 1002, 1002, 1)
             + varint(1) + struct.pack("<II", 1002, 7))
        self.z.verarbeiten(OP_VERTRAUTE, p)
        self.assertEqual(self.z.vertraute["1002"], [1, 7])
        self.z.verarbeiten(OP_SEELE, b"\x01" + struct.pack("<II", 1002, 1))
        self.z.verarbeiten(OP_STUFE, b"\0\0" + struct.pack("<II", 1002, 2))
        self.assertEqual(self.z.vertraute["1002"], [2, 8])


class RissUndSeelenTest(unittest.TestCase):
    def test_riss_zeitplan(self):
        from datetime import datetime, timezone
        from radar.uebersicht import riss
        def zeit(h, m):  # UTC
            return datetime(2026, 10, 24, h, m, tzinfo=timezone.utc).timestamp()
        self.assertEqual(riss(zeit(2, 59)), (zeit(3, 0), False))
        self.assertEqual(riss(zeit(3, 5)), (zeit(3, 0), True))   # 10 min offen
        self.assertEqual(riss(zeit(3, 11)), (zeit(6, 0), False))
        self.assertEqual(riss(zeit(22, 30))[0], zeit(21, 0) + 3 * 3600)  # 00:00 UTC am naechsten Tag

    def test_fehlende_seelen(self):
        from radar.uebersicht import fehlende_seelen
        self.assertEqual(fehlende_seelen(0, 0), (5, 105))
        self.assertEqual(fehlende_seelen(2, 47), (28, 28))
        self.assertEqual(fehlende_seelen(3, 0), (0, 0))

if __name__ == "__main__":
    unittest.main()
