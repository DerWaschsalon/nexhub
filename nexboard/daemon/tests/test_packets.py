"""core.packets: Pakete gehen nur an die Abnehmer ihres Opcodes; ein Strom wird je Verbindung zusammengesetzt."""
import struct

from deckbar_daemon.core.packets import PacketSource, PcapSource

FLOW = (b"\x01\x02\x03\x04", 13328, b"\x0a\x00\x00\x02", 50000)


def frame(opcode: int, payload: bytes) -> bytes:
    content = struct.pack("<H", opcode) + payload
    return bytes([len(content) + 4]) + content


def test_abnehmer_bekommen_nur_ihre_opcodes():
    source = PacketSource()
    cubes, everything = [], []
    source.subscribe((0x3634, 0x3635), lambda op, p: cubes.append(op))
    source.subscribe(None, lambda op, p: everything.append((op, p)))
    for opcode in (0x3634, 0x8D00, 0x3635):
        source.publish(opcode, b"x")
    assert cubes == [0x3634, 0x3635]
    assert everything == [(0x3634, b"x"), (0x8D00, b"x"), (0x3635, b"x")]


def test_segmente_in_falscher_reihenfolge_und_frame_ueber_die_grenze():
    source = PcapSource()
    seen = []
    source.subscribe(None, lambda op, p: seen.append((op, p)))
    data = frame(0x1111, b"a" * 40) + frame(0x2222, b"b")
    source.feed(FLOW, 1000, 0x02, b"")  # SYN
    source.feed(FLOW, 1021, 0, data[20:])  # zu früh
    assert seen == []
    source.feed(FLOW, 1001, 0, data[:20])
    assert seen == [(0x1111, b"a" * 40), (0x2222, b"b")]
    assert (source.streams, source.gaps, source.dropped) == (1, 0, 0)


def test_zweite_verbindung_hat_ihren_eigenen_strom():
    source = PcapSource()
    seen = []
    source.subscribe((0x2222,), lambda op, p: seen.append(p))
    other = (FLOW[0], 13320, FLOW[2], 50001)
    half = frame(0x2222, b"eins")
    source.feed(FLOW, 1, 0, half[:3])
    source.feed(other, 1, 0, frame(0x2222, b"zwei"))
    source.feed(FLOW, 4, 0, half[3:])
    assert seen == [b"zwei", b"eins"] and source.streams == 2
