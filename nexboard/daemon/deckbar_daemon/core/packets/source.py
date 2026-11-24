"""Paketquellen: verteilen Spielpakete als (Opcode, Nutzdaten) an Abnehmer, die sich dafür anmelden.

`PcapSource` liest rohe TCP-Segmente aus einem pcap (Tests, Werkzeuge, Goldtest). Live gibt es zwei Wege:
`TcpdumpSource` über ein eigenes tcpdump und `CaptureSource` über den Rust-Mitschnitt, der die Pakete ohnehin
liest (dann entfällt das zweite Mitlesen).
"""
from __future__ import annotations

import asyncio
import logging
import struct
import subprocess
import threading
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from typing import Any, BinaryIO, Protocol

from .frames import StreamParser
from .messages import Message
from .tcp import Flow, TcpStream, server_segments, start_tcpdump

log = logging.getLogger(__name__)

Handler = Callable[[int, bytes], None]  # (Opcode, Nutzdaten)
UNREADABLE = (ValueError, struct.error, IndexError)  # Nutzdaten passen nicht zur Nachricht


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

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()


class Capture(Protocol):
    """Was die CaptureSource vom Mitschnitt braucht (capture.Capture)."""
    running: bool
    data_listeners: list[Callable[[str, Any], Awaitable[None]]]

    async def request(self, cmd: str, timeout: float = 5, **args: Any) -> Any: ...


class CaptureSource(PacketSource):
    """Pakete aus `deckbar-capture`: Der Mitschnitt schickt die abonnierten Opcodes roh als Meldung `frame`
    (capture/src/frames.rs). Abonniert wird, was hier Abnehmer hat; ohne laufenden Mitschnitt kommt nichts."""

    NOT_RUNNING = "Mitschnitt läuft nicht (Modul AION 2 · Kampfdaten mit eigenem Mitschnitt einschalten)"

    def __init__(self, capture: Capture) -> None:
        super().__init__()
        self.capture = capture
        self.active = False
        self._tasks: set[asyncio.Task] = set()  # Referenzen, sonst räumt asyncio laufende Aufgaben weg

    @property
    def error(self) -> str | None:
        return None if self.capture.running or not self.active else self.NOT_RUNNING

    def opcodes(self) -> list[int]:
        return sorted({*self._by_opcode, *self._typed})

    def start(self) -> None:
        self.active = True
        self.capture.data_listeners.append(self._on_capture)
        if self.capture.running:
            self._spawn(self._subscribe(self.opcodes()))

    def stop(self) -> None:
        self.active = False
        if self._on_capture in self.capture.data_listeners:
            self.capture.data_listeners.remove(self._on_capture)
        if self.capture.running:
            self._spawn(self._subscribe([]))

    async def _on_capture(self, event: str, payload: Any) -> None:
        if event == "hello":  # Mitschnitt neu gestartet: er weiß von nichts mehr
            await self._subscribe(self.opcodes())
        elif event == "frame":
            self.publish(payload["op"], bytes.fromhex(payload["data"]))

    async def _subscribe(self, opcodes: list[int]) -> None:
        try:
            await self.capture.request("subscribe_frames", opcodes=opcodes)
        except (RuntimeError, TimeoutError, OSError) as e:
            log.warning("Pakete nicht beim Mitschnitt abonniert: %s", e)

    def _spawn(self, job: Coroutine) -> None:
        task = asyncio.get_running_loop().create_task(job)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
