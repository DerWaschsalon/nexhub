"""Vom Mitschnitt zum Datenstrom: klassisches pcap lesen, TCP-Segmente des Spielservers herausholen und
je Verbindung in Reihenfolge zusammensetzen (Server → Client)."""
from __future__ import annotations

import struct
import subprocess
from collections.abc import Callable, Iterator
from typing import BinaryIO

SERVER_PORTS = (13328, 13320)
BPF = "tcp and (src port 13328 or src port 13320)"

# Linktypen, die tcpdump liefern kann
LINK_ETHERNET = 1
LINK_RAW = 101
LINK_SLL = 113
LINK_SLL2 = 276
ETHERTYPE_IPV4 = 0x0800
SYN = 0x02
SEQ_MASK = 0xFFFFFFFF

Flow = tuple[bytes, int, bytes, int]  # Quelladresse, Quellport, Zieladresse, Zielport
Segment = tuple[Flow, int, int, bytes]  # Verbindung, Sequenznummer, Flags, Nutzdaten


def pcap_packets(file: BinaryIO) -> Iterator[tuple[float, bytes]]:
    """Liest klassisches pcap und liefert (Zeit, IP-Paket)."""
    head = file.read(24)
    if len(head) < 24:
        return
    magic = head[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        e = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        e = ">"
    else:
        raise ValueError("kein pcap (pcapng nicht unterstützt)")
    nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    link_type = struct.unpack(e + "I", head[20:24])[0] & 0x0FFFFFFF
    while True:
        record = file.read(16)
        if len(record) < 16:
            return
        seconds, fraction, length, _ = struct.unpack(e + "IIII", record)
        raw = file.read(length)
        if len(raw) < length:
            return
        ip = _ip_from_link(link_type, raw)
        if ip is not None:
            yield seconds + fraction / (1e9 if nano else 1e6), ip


def _ip_from_link(link_type: int, raw: bytes) -> bytes | None:
    if link_type == LINK_SLL2:
        proto, offset = struct.unpack_from(">H", raw, 0)[0], 20
    elif link_type == LINK_SLL:
        proto, offset = struct.unpack_from(">H", raw, 14)[0], 16
    elif link_type == LINK_ETHERNET:
        proto, offset = struct.unpack_from(">H", raw, 12)[0], 14
    elif link_type == LINK_RAW:
        return raw
    else:
        return None
    return raw[offset:] if proto == ETHERTYPE_IPV4 else None


def tcp_segment(ip: bytes) -> Segment | None:
    """(Verbindung, seq, Flags, Nutzdaten) aus einem IPv4-Paket."""
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
        return None
    header = (ip[0] & 0x0F) * 4
    total = struct.unpack_from(">H", ip, 2)[0]
    tcp = ip[header:total]
    if len(tcp) < 20:
        return None
    sport, dport, seq = struct.unpack_from(">HHI", tcp, 0)
    data_offset = (tcp[12] >> 4) * 4
    return (ip[12:16], sport, ip[16:20], dport), seq, tcp[13], tcp[data_offset:]


def server_segments(file: BinaryIO) -> Iterator[tuple[float, Segment]]:
    """(Zeit, Segment) jedes TCP-Segments vom Spielserver in einem pcap."""
    for at, ip in pcap_packets(file):
        segment = tcp_segment(ip)
        if segment and segment[0][1] in SERVER_PORTS:
            yield at, segment


class TcpStream:
    """Setzt einen TCP-Strom in Reihenfolge zusammen. Bei Lücken: neu einsteigen."""

    MAX_WAITING = 64

    def __init__(self, output: Callable[[bytes], None], on_gap: Callable[[], None]) -> None:
        self.output = output
        self.on_gap = on_gap
        self.next: int | None = None
        self.waiting: dict[int, bytes] = {}

    def segment(self, seq: int, flags: int, data: bytes) -> None:
        if flags & SYN:
            self.next = (seq + 1) & SEQ_MASK
            self.waiting.clear()
            return
        if not data:
            return
        if self.next is None:
            self.next = seq
        diff = (seq - self.next) & SEQ_MASK
        if diff >= 0x80000000:  # liegt (teilweise) vor dem Erwarteten
            overlap = (self.next - seq) & SEQ_MASK
            if overlap >= len(data):
                return  # Wiederholung
            data = data[overlap:]
            seq = self.next
            diff = 0
        if diff:
            self.waiting[seq] = data
            if len(self.waiting) > self.MAX_WAITING:
                # Paket verloren: ab dem frühesten wartenden Segment neu einsteigen
                self.on_gap()
                expected = self.next
                self.next = min(self.waiting, key=lambda s: (s - expected) & SEQ_MASK)
                self._drain()
            return
        self.output(data)
        self.next = (seq + len(data)) & SEQ_MASK
        self._drain()

    def _drain(self) -> None:
        while self.next in self.waiting:
            data = self.waiting.pop(self.next)
            self.output(data)
            self.next = (self.next + len(data)) & SEQ_MASK


def start_tcpdump(interface: str = "any", file: str = "-") -> subprocess.Popen:
    """Ohne Datei: Mitschnitt nach stdout (fürs Radar), mit Datei: Aufnahme."""
    return subprocess.Popen(
        ["tcpdump", "-i", interface, "-U", "-n", "-s", "0", "-w", file, BPF],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
