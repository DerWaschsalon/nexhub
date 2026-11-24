"""AION-2-Netzprotokoll: Varint, LZ4-Block, Frames.

Ein Frame ist `uvarint(Länge + 4)` gefolgt vom Inhalt. Der Inhalt ist entweder ein LZ4-Container
(`ff ff <u32 Größe> <lz4>` oder `<f0..fe> ff ff <u32> <lz4>`), der wieder Frames enthält, oder
`<u16 Opcode LE> <Nutzdaten>`.
"""
from __future__ import annotations

import struct
from collections.abc import Callable, Iterator

MAX_UNPACKED = 262144
MAX_NESTING = 4

try:  # schneller, falls vorhanden
    import lz4.block as _lz4

    def lz4_decompress(data: bytes, size: int) -> bytes:
        return _lz4.decompress(data, uncompressed_size=size)
except ImportError:
    def lz4_decompress(data: bytes, size: int) -> bytes:
        out = bytearray()
        i, n = 0, len(data)
        while i < n:
            token = data[i]
            i += 1
            literals = token >> 4
            if literals == 15:
                while True:
                    b = data[i]
                    i += 1
                    literals += b
                    if b != 255:
                        break
            out += data[i:i + literals]
            i += literals
            if i >= n:
                break
            offset = data[i] | (data[i + 1] << 8)
            i += 2
            if offset == 0 or offset > len(out):
                raise ValueError("LZ4: ungültiger Versatz")
            length = token & 15
            if length == 15:
                while True:
                    b = data[i]
                    i += 1
                    length += b
                    if b != 255:
                        break
            length += 4
            start = len(out) - offset
            if offset >= length:
                out += out[start:start + length]
            else:
                for k in range(length):
                    out.append(out[start + k])
        if len(out) != size:
            raise ValueError("LZ4: falsche Größe")
        return bytes(out)


class Incomplete(ValueError):
    """Die Daten enden mitten in einem Varint: auf mehr warten."""


def uvarint(data: bytes | bytearray, pos: int = 0) -> tuple[int, int]:
    """Gibt (Wert, Anzahl Bytes) zurück."""
    value = 0
    for i in range(5):
        if pos + i >= len(data):
            raise Incomplete("uvarint unvollständig")
        b = data[pos + i]
        value |= (b & 0x7F) << (7 * i)
        if not b & 0x80:
            return value, i + 1
    raise ValueError("uvarint zu lang")


class Reader:
    """Liest Nutzdaten der Reihe nach: Zahlen little-endian, Texte als uvarint-Länge + UTF-8 (oft mit 0 am
    Ende). Zu kurze Daten werfen struct.error bzw. ValueError wie die übrige Auswertung."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def _number(self, fmt: str) -> int:
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += struct.calcsize(fmt)
        return value

    def u8(self) -> int:
        return self._number("<B")

    def u16(self) -> int:
        return self._number("<H")

    def i32(self) -> int:
        return self._number("<i")

    def i64(self) -> int:
        return self._number("<q")

    def varint(self) -> int:
        value, n = uvarint(self.data, self.pos)
        self.pos += n
        return value

    def text(self) -> str:
        length = self.varint()
        if self.pos + length > len(self.data):
            raise ValueError("Text unvollständig")
        raw = self.data[self.pos:self.pos + length]
        self.pos += length
        return raw.rstrip(b"\0").decode("utf-8", "replace")


def frame_span(buffer: bytes | bytearray, pos: int) -> tuple[int, int] | None:
    """(Länge des Varints, Gesamtlänge) des Frames an `pos`; None, wenn er noch unvollständig ist.
    ValueError, wenn an `pos` kein gültiger Frame-Anfang steht."""
    try:
        coded, varint_len = uvarint(buffer, pos)
    except Incomplete:
        return None
    content = coded - 4
    if content < 2:
        raise ValueError("Frame zu kurz")
    return varint_len, varint_len + content


def _lz4_container(content: bytes) -> bytes | None:
    if content[:2] == b"\xff\xff" and len(content) >= 6:
        head = 6
    elif len(content) >= 7 and 0xF0 <= content[0] < 0xFF and content[1:3] == b"\xff\xff":
        head = 7
    else:
        return None
    size = struct.unpack_from("<I", content, head - 4)[0]
    if not 0 < size <= MAX_UNPACKED:
        return None
    try:
        return lz4_decompress(content[head:], size)
    except Exception:
        return None


def _scan(buffer: bytes | bytearray,
          on_garbage: Callable[[], None] | None = None) -> Iterator[tuple[int, bytes | None]]:
    """(Position danach, Inhalt) jedes vollständigen Frames; Nullbytes und Unlesbares überspringt es byteweise.
    Zuletzt (Position, None): so weit ist der Puffer verbraucht."""
    pos, n = 0, len(buffer)
    while pos < n:
        if buffer[pos] == 0:
            pos += 1
            continue
        try:
            span = frame_span(buffer, pos)
        except ValueError:
            pos += 1
            if on_garbage:
                on_garbage()
            continue
        if span is None or pos + span[1] > n:
            break
        content = bytes(buffer[pos + span[0]:pos + span[1]])
        pos += span[1]
        yield pos, content
    yield pos, None


def frames_in_block(data: bytes) -> Iterator[bytes]:
    """Zerlegt einen vollständigen Block (z. B. entpackten LZ4-Inhalt) in Frame-Inhalte."""
    return (content for _, content in _scan(data) if content is not None)


def messages(content: bytes, depth: int = 0) -> Iterator[tuple[int, bytes]]:
    """Liefert (Opcode, Nutzdaten) aus einem Frame-Inhalt, LZ4 rekursiv entpackt."""
    if len(content) < 2 or depth > MAX_NESTING:
        return
    unpacked = _lz4_container(content)
    if unpacked is not None:
        for frame in frames_in_block(unpacked):
            yield from messages(frame, depth + 1)
        return
    yield struct.unpack_from("<H", content)[0], content[2:]


class StreamParser:
    """Nimmt den zusammengesetzten Server→Client-Strom stückweise an."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.dropped = 0  # Bytes, an denen kein Frame begann

    def _count(self) -> None:
        self.dropped += 1

    def feed(self, data: bytes) -> Iterator[tuple[int, bytes]]:
        self.buffer += data
        used = 0
        for used, content in _scan(self.buffer, self._count):
            if content is not None:
                yield from messages(content)
        del self.buffer[:used]
        if len(self.buffer) > 4 * MAX_UNPACKED:  # aus dem Takt geraten
            self.buffer.clear()

    def reset(self) -> None:
        self.buffer.clear()
