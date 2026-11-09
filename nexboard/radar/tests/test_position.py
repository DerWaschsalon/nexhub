"""Ungepruefte Positionsquellen (nach benhighlanderr/Aion2-Hidden-Cube-Radar), Sprungpruefung und Laufrichtung."""
import math
import struct
import time
import unittest

from radar.zustand import CUBE_IDS, RadarZustand
from tests.test_radar import varint


def pos(x: float, y: float, z: float = 0.0) -> bytes:
    return struct.pack("<fff", x, y, z)


class PositionTest(unittest.TestCase):
    def setUp(self):
        self.z = RadarZustand()
        self.z.eigene_eid = 300

    def test_eigener_cast_gibt_position(self):
        p = varint(300) + bytes(15) + pos(1000.0, 2000.0, 50.0)  # x/y/z ab Byte 17
        self.z.verarbeiten(0x3802, p)
        self.assertEqual(self.z.position, (1000.0, 2000.0, 50.0))
        self.z.verarbeiten(0x3802, varint(301) + bytes(15) + pos(1.0, 1.0))  # fremder Cast: nicht
        self.assertEqual(self.z.position, (1000.0, 2000.0, 50.0))

    def test_sprung_aus_ungepruefter_quelle_wird_verworfen(self):
        self.z.verarbeiten(0x371A, varint(300) + b"\0\0" + pos(0.0, 0.0))
        self.z.verarbeiten(0x3712, varint(300) + b"\0\0" + pos(500.0, 0.0))  # 5 m: ok
        self.assertEqual(self.z.position[0], 500.0)
        self.z.verarbeiten(0x3712, varint(300) + b"\0\0" + pos(90000.0, 0.0))  # 900 m: Unsinn
        self.assertEqual(self.z.position[0], 500.0)
        self.z.position_zeit = time.time() - 11  # letzte Position alt: dann gilt auch ein Sprung
        self.z.verarbeiten(0x3712, varint(300) + b"\0\0" + pos(90000.0, 0.0))
        self.assertEqual(self.z.position[0], 90000.0)

    def test_eintritt_und_zonenwechsel(self):
        self.z.eigene_eid = None
        p = varint(300) + bytes(14) + pos(10.0, 20.0, 30.0)  # x/y/z ab Byte 16
        self.z.verarbeiten(0x3621, p)
        self.assertEqual((self.z.eigene_eid, self.z.eid_sicher), (300, False))
        self.assertEqual(self.z.position, (10.0, 20.0, 30.0))
        self.z.verarbeiten(0x561E, bytes(17) + pos(15.0, 25.0, 35.0))
        self.assertEqual(self.z.position, (15.0, 25.0, 35.0))

    def test_laufrichtung(self):
        bewegen = lambda x, y: self.z.verarbeiten(0x371A, varint(300) + b"\0\0" + pos(x, y))  # noqa: E731
        bewegen(0, 0)
        bewegen(50, 0)  # unter 1 m: noch kein Kurs
        self.assertIsNone(self.z.kurs)
        bewegen(200, 0)  # nach Osten
        self.assertEqual(self.z.kurs, (1.0, 0.0))
        bewegen(200, -300)  # nach Norden (Welt -y)
        self.assertTrue(math.isclose(self.z.kurs[1], -1.0))
        bewegen(200, -300 + 5000)  # Teleport: Kurs bleibt, nur der Startpunkt springt
        self.assertTrue(math.isclose(self.z.kurs[1], -1.0))

    def test_neue_cube_ids(self):
        self.assertTrue({1000549, 1000565, 1300081, 1300082} <= CUBE_IDS)
        self.assertNotIn(1000567 + 100, CUBE_IDS)
