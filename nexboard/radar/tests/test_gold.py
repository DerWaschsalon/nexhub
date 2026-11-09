"""Goldtest: jeder Mitschnitt liefert dieselben Ergebnisse wie beim Schreiben der Referenz.

Läuft nur, wo Mitschnitte und Referenzen liegen (python -m werkzeuge.gold --schreiben <spur>), sonst
übersprungen. Eine gewollte Änderung: Referenzen neu schreiben und den Unterschied begründen.
"""
import unittest

from werkzeuge.gold import CAPTURE, MITSCHNITTE, alle, referenz, referenz_lesen


class GoldTest(unittest.TestCase):
    def test_radar(self):
        self.spur_pruefen("radar")

    def test_capture(self):
        if not CAPTURE.exists():
            self.skipTest("deckbar-capture ist nicht gebaut (cargo build --release in capture/)")
        self.spur_pruefen("capture")

    def spur_pruefen(self, spur: str) -> None:
        pcaps = [p for p in sorted(MITSCHNITTE.glob("*.pcap")) if referenz(spur, p).exists()]
        if not pcaps:
            self.skipTest(f"keine Mitschnitte mit Referenz der Spur {spur} auf diesem Rechner")
        for pcap, zeilen in zip(pcaps, alle(spur, pcaps)):
            with self.subTest(pcap.name):
                self.assertEqual(erste_abweichung(zeilen, referenz_lesen(spur, pcap)), None)


def erste_abweichung(ist: list[str], soll: list[str]) -> tuple[int, str, str] | None:
    """Zeilennummer und beide Zeilen der ersten Abweichung; die Listen haben bis zu einer Million Zeilen."""
    if ist == soll:
        return None
    for nummer, (a, b) in enumerate(zip(ist, soll), 1):
        if a != b:
            return nummer, a[:500], b[:500]
    nummer = min(len(ist), len(soll)) + 1
    return nummer, f"{len(ist)} Zeilen", f"{len(soll)} Zeilen"
