"""Mitschnitt ueber tcpdump und Zusammensetzen der TCP-Stroeme (Server -> Client)."""
from __future__ import annotations

import struct
import subprocess
from typing import BinaryIO, Callable, Iterator

SERVER_PORTS = (13328, 13320)
BPF = "tcp and (src port 13328 or src port 13320)"

# Linktypen, die tcpdump liefern kann
LINK_ETHERNET = 1
LINK_RAW = 101
LINK_SLL = 113
LINK_SLL2 = 276


def pcap_pakete(datei: BinaryIO) -> Iterator[tuple[float, bytes]]:
    """Liest klassisches pcap und liefert (zeit, ip_paket)."""
    kopf = datei.read(24)
    if len(kopf) < 24:
        return
    magic = kopf[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        e = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        e = ">"
    else:
        raise ValueError("kein pcap (pcapng nicht unterstuetzt)")
    nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    linktyp = struct.unpack(e + "I", kopf[20:24])[0] & 0x0FFFFFFF
    while True:
        rk = datei.read(16)
        if len(rk) < 16:
            return
        sek, teil, laenge, _ = struct.unpack(e + "IIII", rk)
        roh = datei.read(laenge)
        if len(roh) < laenge:
            return
        zeit = sek + teil / (1e9 if nano else 1e6)
        ip = _ip_aus_link(linktyp, roh)
        if ip is not None:
            yield zeit, ip


def _ip_aus_link(linktyp: int, roh: bytes) -> bytes | None:
    if linktyp == LINK_SLL2:
        proto, versatz = struct.unpack_from(">H", roh, 0)[0], 20
    elif linktyp == LINK_SLL:
        proto, versatz = struct.unpack_from(">H", roh, 14)[0], 16
    elif linktyp == LINK_ETHERNET:
        proto, versatz = struct.unpack_from(">H", roh, 12)[0], 14
    elif linktyp == LINK_RAW:
        return roh
    else:
        return None
    return roh[versatz:] if proto == 0x0800 else None


def tcp_segment(ip: bytes) -> tuple[tuple, int, int, bytes] | None:
    """(fluss, seq, flags, nutzdaten) aus einem IPv4-Paket."""
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
        return None
    ihl = (ip[0] & 0x0F) * 4
    gesamt = struct.unpack_from(">H", ip, 2)[0]
    tcp = ip[ihl:gesamt]
    if len(tcp) < 20:
        return None
    sport, dport, seq = struct.unpack_from(">HHI", tcp, 0)
    doff = (tcp[12] >> 4) * 4
    flags = tcp[13]
    fluss = (ip[12:16], sport, ip[16:20], dport)
    return fluss, seq, flags, tcp[doff:]


class TcpStrom:
    """Setzt einen TCP-Strom in Reihenfolge zusammen. Bei Luecken: neu einsteigen."""

    MAX_WARTEND = 64

    def __init__(self, ausgabe: Callable[[bytes], None], luecke: Callable[[], None]) -> None:
        self.ausgabe = ausgabe
        self.luecke = luecke
        self.naechste: int | None = None
        self.wartend: dict[int, bytes] = {}

    def segment(self, seq: int, flags: int, daten: bytes) -> None:
        if flags & 0x02:  # SYN
            self.naechste = (seq + 1) & 0xFFFFFFFF
            self.wartend.clear()
            return
        if not daten:
            return
        if self.naechste is None:
            self.naechste = seq
        diff = (seq - self.naechste) & 0xFFFFFFFF
        if diff >= 0x80000000:  # liegt (teilweise) vor dem Erwarteten
            ueberlapp = (self.naechste - seq) & 0xFFFFFFFF
            if ueberlapp >= len(daten):
                return  # Wiederholung
            daten = daten[ueberlapp:]
            seq = self.naechste
            diff = 0
        if diff:
            self.wartend[seq] = daten
            if len(self.wartend) > self.MAX_WARTEND:
                # Paket verloren: ab dem fruehesten wartenden Segment neu einsteigen
                self.luecke()
                self.naechste = min(self.wartend, key=lambda s: (s - self.naechste) & 0xFFFFFFFF)
                self._abarbeiten()
            return
        self.ausgabe(daten)
        self.naechste = (seq + len(daten)) & 0xFFFFFFFF
        self._abarbeiten()

    def _abarbeiten(self) -> None:
        while self.naechste in self.wartend:
            d = self.wartend.pop(self.naechste)
            self.ausgabe(d)
            self.naechste = (self.naechste + len(d)) & 0xFFFFFFFF


def tcpdump_starten(schnittstelle: str = "any", datei: str = "-") -> subprocess.Popen:
    """Ohne Datei: Mitschnitt nach stdout (fuers Radar), mit Datei: Aufnahme."""
    return subprocess.Popen(
        ["tcpdump", "-i", schnittstelle, "-U", "-n", "-s", "0", "-w", datei, BPF],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
