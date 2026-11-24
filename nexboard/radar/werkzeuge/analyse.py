"""Wertet einen pcap-Mitschnitt aus: Opcode-Statistik und Pruefung der Radar-Opcodes.

Aufruf: python -m werkzeuge.analyse mitschnitte/datei.pcap [--opcode 0x3634] [--hex 5]
"""
from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter, defaultdict

from deckbar_daemon.core.packets import PcapSource, server_segments, uvarint


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--opcode", type=lambda s: int(s, 0), action="append", default=[])
    ap.add_argument("--hex", type=int, default=3, help="Beispiele je --opcode")
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()

    zaehler: Counter[int] = Counter()
    beispiele: dict[int, list[tuple[float, bytes]]] = defaultdict(list)
    spawn_ids: Counter[int] = Counter()
    zeit = 0.0

    def zaehlen(op: int, p: bytes) -> None:
        zaehler[op] += 1
        if op in a.opcode and len(beispiele[op]) < a.hex:
            beispiele[op].append((zeit, p))
        if op == 0x3634:
            try:
                _, n = uvarint(p)
                spawn_ids[struct.unpack_from("<I", p, n + 2)[0]] += 1
            except Exception:
                pass

    quelle = PcapSource()
    quelle.subscribe(None, zaehlen)
    with open(a.pcap, "rb") as f:
        for zeit, segment in server_segments(f):
            quelle.feed(*segment)

    print(f"Stroeme: {quelle.streams}  Luecken: {quelle.gaps}  verworfene Bytes: {quelle.dropped}")
    print(f"Nachrichten: {sum(zaehler.values())}")
    for op, n in zaehler.most_common(a.top):
        print(f"  0x{op:04x} ({op:5d}): {n}")
    print("Objekt-IDs in 0x3634 (haeufigste):")
    for oid, n in spawn_ids.most_common(25):
        print(f"  {oid}: {n}")
    for op, liste in beispiele.items():
        print(f"\nBeispiele 0x{op:04x}:")
        for t, p in liste:
            print(f"  t={t:.3f} len={len(p)} {p[:64].hex(' ')}")


if __name__ == "__main__":
    sys.exit(main())
