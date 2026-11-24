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


def test_varint_lz4_und_container():
    from deckbar_daemon.core.packets import frame_packets, lz4_decompress, uvarint
    assert uvarint(b"\xfc\x45") == (8956, 2)
    assert lz4_decompress(bytes([0x22]) + b"ab" + b"\x02\x00", 8) == b"abababab"  # 2 Literale, dann 6 kopiert
    inner = frame(0x1234, b"xyz")
    block = bytes([len(inner) << 4]) + inner  # nur Literale
    assert list(frame_packets(b"\xff\xff" + struct.pack("<I", len(inner)) + block)) == [(0x1234, b"xyz")]


def test_wiederholtes_segment_zaehlt_einmal():
    from deckbar_daemon.core.packets import TcpStream
    out = []
    stream = TcpStream(out.append, lambda: None)
    stream.segment(1000, 0x02, b"")  # SYN
    stream.segment(1005, 0, b"world")  # zu früh
    stream.segment(1001, 0, b"hall")
    stream.segment(1001, 0, b"hall")  # Wiederholung
    assert b"".join(out) == b"hallworld"


def test_typisierte_nachricht_wird_einmal_dekodiert_und_kaputte_faellt_weg():
    from deckbar_daemon.core.packets.messages import CastBar
    source = PacketSource()
    first, second = [], []
    source.on(CastBar, first.append)
    source.on(CastBar, second.append)
    source.publish(0x3809, b"\x7f\x02" + struct.pack("<I", 1604670) + b"\x01\x02")
    source.publish(0x3809, b"\x7f\x02\x01")  # zu kurz für den Skill
    source.publish(0x3809, b"")  # nicht einmal eine Entity
    assert first == [CastBar(127, 1604670, None)] and first[0] is second[0]
    assert source.packets == 3
