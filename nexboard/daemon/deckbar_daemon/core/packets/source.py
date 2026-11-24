"""Paketquellen: verteilen Spielpakete als (Opcode, Nutzdaten) an Abnehmer, die sich dafür anmelden.

`PcapSource` liest rohe TCP-Segmente aus einem pcap (Tests, Werkzeuge, Goldtest). `TcpdumpSource` ist der
Live-Weg des Radars über ein eigenes tcpdump, bis das Radar am Rust-Mitschnitt hängt (Umbauschritt 7).
"""
from __future__ import annotations

import logging
import struct
import subprocess
import threading
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from .frames import StreamParser
from .messages import Message
from .tcp import Flow, TcpStream, server_segments, start_tcpdump

log = logging.getLogger(__name__)

Handler = Callable[[int, bytes], None]  # (Opcode, Nutzdaten)
UNREADABLE = (ValueError, struct.error, IndexError)  # Nutzdaten passen nicht zur Nachricht
RECORDINGS = Path.home() / ".local" / "share" / "aion2-radar" / "mitschnitte"  # nie ins Repo


class PacketSource:
    def __init__(self) -> None:
        self._for_all: list[Handler] = []
        self._by_opcode: dict[int, list[Handler]] = {}
        self._typed: dict[int, dict[type[Message], list[Callable]]] = {}
        self.packets = 0  # alle gesehenen Pakete, auch die ohne Abnehmer

    def subscribe(self, opcodes: Iterable[int] | None, handler: Handler) -> None:
        """Pakete dieser Opcodes an `handler`; None = jedes Paket (Werkzeuge, Lernmodus)."""
        if opcodes is None:
            self._for_all.append(handler)
        for opcode in opcodes or ():
            self._by_opcode.setdefault(opcode, []).append(handler)

    def on[M: Message](self, message: type[M], handler: Callable[[M], None]) -> None:
        """Pakete als dekodierte Nachricht dieser Klasse an `handler`. Je Paket wird einmal je Klasse dekodiert,
        gleich wie viele Abnehmer sie hat; Klassen und ihre Abnehmer kommen in der Reihenfolge der Anmeldung."""
        for opcode in message.OPCODES:
            readers = self._typed.setdefault(opcode, {})
            readers.setdefault(message, []).append(handler)

    def publish(self, opcode: int, payload: bytes) -> None:
        self.packets += 1
        for handler in self._for_all:
            handler(opcode, payload)
        for handler in self._by_opcode.get(opcode, ()):
            handler(opcode, payload)
        for message, handlers in self._typed.get(opcode, {}).items():
            try:
                decoded = message.read(opcode, payload)
            except UNREADABLE:
                continue  # kaputte oder unbekannte Nachricht
            if decoded is not None:
                for typed_handler in handlers:
                    typed_handler(decoded)


class PcapSource(PacketSource):
    """Setzt je Verbindung den TCP-Strom zusammen, zerlegt ihn in Frames und verteilt die Pakete."""

    def __init__(self) -> None:
        super().__init__()
        self._streams: dict[Flow, TcpStream] = {}
        self._parsers: list[StreamParser] = []
        self.gaps = 0  # verlorene Segmente, nach denen ein Strom neu eingestiegen ist

    @property
    def dropped(self) -> int:
        """Bytes, an denen kein Frame begann (Werkzeug analyse)."""
        return sum(parser.dropped for parser in self._parsers)

    @property
    def streams(self) -> int:
        return len(self._streams)

    def feed(self, flow: Flow, seq: int, flags: int, data: bytes) -> None:
        """Ein TCP-Segment vom Spielserver."""
        stream = self._streams.get(flow)
        if stream is None:
            stream = self._streams[flow] = self._new_stream()
        stream.segment(seq, flags, data)

    def _new_stream(self) -> TcpStream:
        parser = StreamParser()
        self._parsers.append(parser)

        def output(data: bytes) -> None:
            for opcode, payload in parser.feed(data):
                self.publish(opcode, payload)

        def on_gap() -> None:
            self.gaps += 1
            parser.reset()

        return TcpStream(output, on_gap)

    def read(self, file: BinaryIO) -> None:
        """Ein ganzes pcap (Datei oder die Ausgabe von tcpdump) bis zum Ende."""
        for _, segment in server_segments(file):
            self.feed(*segment)


class TcpdumpSource(PcapSource):
    def __init__(self) -> None:
        super().__init__()
        self.error: str | None = None  # warum der Mitschnitt nicht läuft, für die Anzeige
        self._process: subprocess.Popen | None = None
        self._recording: subprocess.Popen | None = None  # zweites tcpdump, schreibt für den Lernmodus eine Datei

    def start(self, interface: str = "any") -> threading.Thread:
        def run() -> None:
            try:
                self._process = start_tcpdump(interface)
                assert self._process.stdout
                self.read(self._process.stdout)
                if self._process.wait() != 0:
                    self.error = "tcpdump beendet (Rechte? getcap /usr/bin/tcpdump)"
            except FileNotFoundError:
                self.error = "tcpdump fehlt (pacman -S tcpdump, dann setcap cap_net_raw,cap_net_admin=eip)"
            except Exception as e:  # die Anzeige soll den Fehler zeigen
                self.error = str(e)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    @property
    def recording(self) -> bool:
        return self._recording is not None

    def start_recording(self, name: str = "dungeon") -> None:
        self.stop_recording()
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        file = RECORDINGS / f"{name.replace(' ', '_')}-{datetime.now():%Y%m%d-%H%M}.pcap"
        self._recording = start_tcpdump(file=str(file))
        log.info("Aufnahme läuft: %s", file.name)

    def stop_recording(self) -> None:
        if self._recording:
            self._recording.terminate()
            self._recording = None
            log.info("Aufnahme beendet")

    def stop(self) -> None:
        self.stop_recording()
        if self._process and self._process.poll() is None:
            self._process.terminate()
