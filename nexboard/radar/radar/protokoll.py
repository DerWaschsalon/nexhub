"""AION-2-Netzprotokoll: Varint, LZ4-Block, Frames.

Ein Frame ist `uvarint(laenge + 4)` gefolgt vom Inhalt. Der Inhalt ist entweder
ein LZ4-Container (`ff ff <u32 groesse> <lz4>` oder `<f0..fe> ff ff <u32> <lz4>`),
der wieder Frames enthaelt, oder `<u16 opcode LE> <nutzdaten>`.
"""
from __future__ import annotations

import struct
from typing import Iterator

MAX_ENTPACKT = 262144

try:  # schneller, falls vorhanden
    import lz4.block as _lz4

    def lz4_entpacken(daten: bytes, groesse: int) -> bytes:
        return _lz4.decompress(daten, uncompressed_size=groesse)
except ImportError:
    def lz4_entpacken(daten: bytes, groesse: int) -> bytes:
        aus = bytearray()
        i, n = 0, len(daten)
        while i < n:
            token = daten[i]
            i += 1
            lit = token >> 4
            if lit == 15:
                while True:
                    b = daten[i]
                    i += 1
                    lit += b
                    if b != 255:
                        break
            aus += daten[i:i + lit]
            i += lit
            if i >= n:
                break
            versatz = daten[i] | (daten[i + 1] << 8)
            i += 2
            if versatz == 0 or versatz > len(aus):
                raise ValueError("LZ4: ungueltiger Versatz")
            laenge = token & 15
            if laenge == 15:
                while True:
                    b = daten[i]
                    i += 1
                    laenge += b
                    if b != 255:
                        break
            laenge += 4
            start = len(aus) - versatz
            if versatz >= laenge:
                aus += aus[start:start + laenge]
            else:
                for k in range(laenge):
                    aus.append(aus[start + k])
        if len(aus) != groesse:
            raise ValueError("LZ4: falsche Groesse")
        return bytes(aus)


def uvarint(daten: bytes, pos: int = 0) -> tuple[int, int]:
    """Gibt (wert, anzahl_bytes) zurueck."""
    wert = 0
    for i in range(5):
        if pos + i >= len(daten):
            raise ValueError("uvarint unvollstaendig")
        b = daten[pos + i]
        wert |= (b & 0x7F) << (7 * i)
        if not b & 0x80:
            return wert, i + 1
    raise ValueError("uvarint zu lang")


def frame_laenge(puffer: bytes | bytearray, pos: int) -> int | None:
    """Gesamtlaenge des Frames an `pos`, None wenn noch unvollstaendig.

    Wirft ValueError, wenn an `pos` kein gueltiger Frame-Anfang steht.
    """
    try:
        kodiert, vl = uvarint(puffer, pos)
    except ValueError as e:
        if "unvollstaendig" in str(e):
            return None
        raise
    inhalt = kodiert - 4
    if inhalt < 2:
        raise ValueError("Frame zu kurz")
    return vl + inhalt


def _lz4_container(inhalt: bytes) -> bytes | None:
    if inhalt[:2] == b"\xff\xff" and len(inhalt) >= 6:
        kopf = 6
    elif len(inhalt) >= 7 and 0xF0 <= inhalt[0] < 0xFF and inhalt[1:3] == b"\xff\xff":
        kopf = 7
    else:
        return None
    groesse = struct.unpack_from("<I", inhalt, kopf - 4)[0]
    if not 0 < groesse <= MAX_ENTPACKT:
        return None
    try:
        return lz4_entpacken(inhalt[kopf:], groesse)
    except Exception:
        return None


def frames_in_block(daten: bytes) -> Iterator[bytes]:
    """Zerlegt einen vollstaendigen Block (z.B. entpackten LZ4-Inhalt) in Frame-Inhalte."""
    pos, n = 0, len(daten)
    while pos < n:
        if daten[pos] == 0:
            pos += 1
            continue
        try:
            laenge = frame_laenge(daten, pos)
        except ValueError:
            pos += 1
            continue
        if laenge is None or pos + laenge > n:
            break
        _, vl = uvarint(daten, pos)
        yield daten[pos + vl:pos + laenge]
        pos += laenge


def nachrichten(inhalt: bytes, tiefe: int = 0) -> Iterator[tuple[int, bytes]]:
    """Liefert (opcode, nutzdaten) aus einem Frame-Inhalt, LZ4 rekursiv entpackt."""
    if len(inhalt) < 2 or tiefe > 4:
        return
    entpackt = _lz4_container(inhalt)
    if entpackt is not None:
        for f in frames_in_block(entpackt):
            yield from nachrichten(f, tiefe + 1)
        return
    yield struct.unpack_from("<H", inhalt)[0], inhalt[2:]


class StromZerleger:
    """Nimmt den zusammengesetzten Server->Client-Strom stueckweise an."""

    def __init__(self) -> None:
        self.puffer = bytearray()
        self.verworfen = 0

    def fuettern(self, daten: bytes) -> Iterator[tuple[int, bytes]]:
        self.puffer += daten
        pos = 0
        while pos < len(self.puffer):
            if self.puffer[pos] == 0:
                pos += 1
                continue
            try:
                laenge = frame_laenge(self.puffer, pos)
            except ValueError:
                pos += 1
                self.verworfen += 1
                continue
            if laenge is None or pos + laenge > len(self.puffer):
                break
            _, vl = uvarint(self.puffer, pos)
            inhalt = bytes(self.puffer[pos + vl:pos + laenge])
            pos += laenge
            yield from nachrichten(inhalt)
        del self.puffer[:pos]
        if len(self.puffer) > 4 * MAX_ENTPACKT:  # aus dem Takt geraten
            self.puffer.clear()

    def zuruecksetzen(self) -> None:
        self.puffer.clear()
