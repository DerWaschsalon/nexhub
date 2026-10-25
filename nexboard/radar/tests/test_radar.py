import struct
import unittest

from radar.mitschnitt import TcpStrom
from radar.protokoll import StromZerleger, lz4_entpacken, nachrichten, uvarint
from radar.zustand import RadarZustand


def varint(n: int) -> bytes:
    aus = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            aus.append(b | 0x80)
        else:
            aus.append(b)
            return bytes(aus)


def frame(op: int, nutz: bytes) -> bytes:
    inhalt = struct.pack("<H", op) + nutz
    return varint(len(inhalt) + 4) + inhalt


def spawn(eid: int, objekt_id: int, x: float, y: float, z: float) -> bytes:
    return frame(0x3634, varint(eid) + b"\x00\x00" + struct.pack("<Ifff", objekt_id, x, y, z))


def bewegung(eid: int, x: float, y: float, z: float) -> bytes:
    return frame(0x382A, varint(eid) + b"\x01\x11" + bytes(20) + struct.pack("<fff", x, y, z))


class Protokoll(unittest.TestCase):
    def test_uvarint(self):
        self.assertEqual(uvarint(b"\xfc\x45"), (8956, 2))
        self.assertEqual(uvarint(varint(300000)), (300000, 3))

    def test_lz4_mit_wiederholung(self):
        # Literal "ab", dann 6 Bytes ab Versatz 2 -> "abababab"
        block = bytes([0x22]) + b"ab" + b"\x02\x00"
        self.assertEqual(lz4_entpacken(block, 8), b"abababab")

    def test_lz4_container(self):
        innen = frame(0x1234, b"xyz")
        block = bytes([len(innen) << 4]) + innen  # nur Literale
        inhalt = b"\xff\xff" + struct.pack("<I", len(innen)) + block
        self.assertEqual(list(nachrichten(inhalt)), [(0x1234, b"xyz")])

    def test_frame_ueber_segmentgrenze(self):
        daten = frame(0x1111, b"a" * 50) + frame(0x2222, b"b")
        z = StromZerleger()
        erst = list(z.fuettern(daten[:20]))
        rest = list(z.fuettern(daten[20:]))
        self.assertEqual(erst, [])
        self.assertEqual([op for op, _ in rest], [0x1111, 0x2222])


class Tcp(unittest.TestCase):
    def test_reihenfolge_und_wiederholung(self):
        aus = []
        s = TcpStrom(aus.append, lambda: None)
        s.segment(1000, 0x02, b"")       # SYN
        s.segment(1005, 0, b"world")     # zu frueh
        s.segment(1001, 0, b"hall")
        s.segment(1001, 0, b"hall")      # Wiederholung
        self.assertEqual(b"".join(aus), b"hallworld")


class Zustand(unittest.TestCase):
    def test_cube_und_position(self):
        z = RadarZustand("Navonex")
        neu = []
        z.bei_neuem_cube.append(neu.append)
        char = frame(0x3633, varint(8956) + b"\x5f\x91\xe9\x28\x37\x07Navonex" + bytes(40))
        strom = StromZerleger()
        daten = (char + bewegung(8956, 1000.0, 2000.0, 50.0)
                 + spawn(77, 1000295, 3000.0, 2000.0, 450.0)   # Cube, 20 m noerdlich, 4 m hoeher
                 + spawn(78, 1100133, 0.0, 0.0, 0.0))          # kein Cube
        for op, p in strom.fuettern(daten):
            z.verarbeiten(op, p)
        s = z.schnappschuss()
        self.assertEqual(s["eid"], 8956)
        self.assertTrue(s["eid_ueber_name"])
        self.assertEqual(s["position"], (1000.0, 2000.0, 50.0))
        self.assertEqual([c.eid for c in s["cubes"]], [77])
        self.assertEqual(len(neu), 1)

        for op, p in strom.fuettern(frame(0x3635, varint(77))):
            z.verarbeiten(op, p)
        self.assertEqual(z.schnappschuss()["cubes"], [])

    def test_fremde_bewegung_ignoriert(self):
        z = RadarZustand()
        z.eigene_eid = 1
        for op, p in StromZerleger().fuettern(bewegung(2, 5.0, 5.0, 5.0)):
            z.verarbeiten(op, p)
        self.assertIsNone(z.schnappschuss()["position"])


if __name__ == "__main__":
    unittest.main()
