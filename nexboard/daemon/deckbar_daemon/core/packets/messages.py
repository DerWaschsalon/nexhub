"""Typisierte Spielpakete: je Opcode eine Klasse, die ihre Nutzdaten in `read()` genau einmal dekodiert.

Abnehmer melden sich bei der Paketquelle mit der Klasse an (`source.on(Cast, handler)`) und sehen keine
Bytes mehr. Koordinaten sind Zentimeter, Zeiten Sekunden. Was am eigenen Mitschnitt geprüft ist, steht
bei der Klasse; der Rest ist mit seiner Herkunft vermerkt. Jede Nachricht beginnt mit der Entity als
Varint, auch wo sie nichts bedeutet: Ist schon das unlesbar, fällt die Nachricht weg.
"""
from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from typing import ClassVar, Self

from .frames import Reader, uvarint

Position = tuple[float, float, float]
MAX_COORDINATE = 1_000_000
OWN_POINT_KINDS = {1, 3}  # MP und SP schickt der Server nur für den eigenen Charakter (geprüft)
PARTY_NAME = re.compile(rb"(?=(....)\x00\x00..([\x02-\x18]))", re.S)
PLAUSIBLE_MS = (1.6e12, 2.6e12)  # Zeitstempel einer Feldboss-Liste, sonst ist es die Variante mit einem Byte mehr


def valid(*values: float) -> bool:
    return all(math.isfinite(v) and abs(v) < MAX_COORDINATE for v in values)


def _position(p: bytes, at: int) -> Position:
    return struct.unpack_from("<fff", p, at)


def _position_or_none(p: bytes, at: int) -> Position | None:
    try:
        return _position(p, at)
    except struct.error:
        return None


def _u32(p: bytes, at: int) -> int:
    return struct.unpack_from("<I", p, at)[0]


class Message:
    """Basis aller Nachrichten. `read()` gibt None zurück oder wirft ValueError/struct.error/IndexError,
    wenn die Nutzdaten nicht passen; die Quelle verwirft die Nachricht dann."""

    OPCODES: ClassVar[tuple[int, ...]] = ()

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self | None:
        raise NotImplementedError


@dataclass(frozen=True)
class ObjectSpawn(Message):
    """Objekt erscheint: Entity, 2 Byte, Objekt-ID u32, x/y/z, 8 Byte, 01 01, Zustand u8, seit u64 ms
    (Format aus a2kit, am Cube geprüft)."""
    OPCODES = (0x3634,)
    entity: int
    object_id: int
    position: Position
    since: float | None  # Serverzeit, seit der das Objekt steht

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self | None:
        entity, n = uvarint(p)
        position = _position(p, n + 6)
        if not valid(*position):
            return None
        since = struct.unpack_from("<Q", p, n + 29)[0] / 1000 if p[n + 26:n + 28] == b"\x01\x01" else None
        return cls(entity, _u32(p, n + 2), position, since)


@dataclass(frozen=True)
class ObjectGone(Message):
    """Objekt verschwindet, auch nach dem Öffnen (geprüft)."""
    OPCODES = (0x3635,)
    entity: int

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        return cls(uvarint(p)[0])


@dataclass(frozen=True)
class ObjectOpening(Message):
    """Spieler beginnt ein Objekt zu öffnen: Objekt-Entity, Spieler-Entity (aus aion2cubedetector, am Cube
    geprüft: 4 s später 0x363A = fertig)."""
    OPCODES = (0x3638,)
    entity: int
    opener: int

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        return cls(entity, uvarint(p, n)[0])


@dataclass(frozen=True)
class ObjectOpened(Message):
    """Objekt fertig geöffnet; beim Cube steht am Ende der verbrauchte Schlüssel."""
    OPCODES = (0x363A,)
    entity: int
    tail: bytes  # die letzten 12 Byte

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        return cls(uvarint(p)[0], p[-12:])


@dataclass(frozen=True)
class PlayerSeen(Message):
    """Spieler erscheint. 0x3633 ist der eigene oder ein fremder Charakter mit Namen (geprüft), 0x3645 ein
    anderer Spieler: Entity, 4 Byte, Namenslänge, Name (geprüft)."""
    CHARACTER: ClassVar[int] = 0x3633
    OPCODES = (CHARACTER, 0x3645)
    entity: int
    name: str
    character: bool
    head: bytes  # Anfang der Nachricht: darin steht beim eigenen Charakter sein Name

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        name = p[n + 6:n + 6 + p[n + 5]].decode("utf-8", "replace")
        return cls(entity, name, opcode == cls.CHARACTER, p[:64])


@dataclass(frozen=True)
class Vitals(Message):
    """Punkte einer Entity (HP, MP …): Entity, Flags u8, bei Flag 1 Varint N, N × (Art u8, i32)."""
    OPCODES = (0x8D00,)
    entity: int
    own_points: bool  # trägt MP oder SP: nur der eigene Charakter
    hp: int | None  # aktuelle HP, falls die Nachricht sie trägt

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        r = Reader(p)
        r.pos = n
        kinds = set()
        if r.u8() & 1:
            for _ in range(r.varint()):
                kinds.add(r.u8())
                r.i32()
        has_hp = p[n:n + 3] == b"\x02\x01\x00" and len(p) >= n + 7
        return cls(entity, bool(OWN_POINT_KINDS & kinds), _u32(p, n + 3) if has_hp else None)


@dataclass(frozen=True)
class Teleport(Message):
    """Eigener Teleport oder Zonenwechsel mit der neuen Position (geprüft)."""
    OPCODES = (0x3623,)
    position: Position | None

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        _, n = uvarint(p)
        return cls(_position_or_none(p, n + 5))


@dataclass(frozen=True)
class ZoneChange(Message):
    """Eigener Zonenwechsel: Zonen-ID u32, im Dungeon die Dungeon-ID (geprüft)."""
    OPCODES = (0x4002,)
    zone: int

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        uvarint(p)
        return cls(_u32(p, 0))


@dataclass(frozen=True)
class NpcSeen(Message):
    """NPC erscheint: Entity, 3 Byte, NPC-ID u32, 2 Byte, x/y/z (geprüft)."""
    OPCODES = (0x3641,)
    entity: int
    npc: int
    position: Position | None

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        return cls(entity, _u32(p, n + 3), _position_or_none(p, n + 9))


@dataclass(frozen=True)
class PositionUpdate(Message):
    """Position einer Entity. 0x382B ist die Status-Variante mit Position am Ende, 0x371A eine Bewegung
    (Entity, 2 Byte, x/y/z). Die übrigen Bewegungsarten 0x3710–0x3750 sind ungeprüft (Erkenntnis aus
    benhighlanderr/Aion2-Hidden-Cube-Radar, dort ohne Lizenz): `checked` heißt, der Abnehmer soll einen
    Sprung nicht glauben."""
    STATUS: ClassVar[int] = 0x382B
    MOVE: ClassVar[int] = 0x371A
    OPCODES = (STATUS, *range(0x3710, 0x3751))
    entity: int
    position: Position
    checked: bool

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        position = _position(p, len(p) - 12 if opcode == cls.STATUS else n + 2)
        return cls(entity, position, opcode not in (cls.STATUS, cls.MOVE))


@dataclass(frozen=True)
class WorldEntry(Message):
    """Eigener Charakter betritt die Welt: Entity, …, x/y/z ab Byte 16 (ungeprüft, Quelle wie oben)."""
    OPCODES = (0x3621,)
    entity: int
    position: Position

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self | None:
        return cls(uvarint(p)[0], _position(p, 16)) if len(p) >= 28 else None


@dataclass(frozen=True)
class ZonePosition(Message):
    """Zonenwechsel mit Position ab Byte 17 (ungeprüft, Quelle wie oben)."""
    OPCODES = (0x561E,)
    position: Position

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self | None:
        uvarint(p)
        return cls(_position(p, 17)) if len(p) >= 29 else None


@dataclass(frozen=True)
class PartyMember(Message):
    """Gruppenmitglied, etwa alle 2 s: Charakter-ID u32, Zone u32 ab Byte 12, x/y/z ab Byte 24. Der Name
    ab Byte 49 ist die Gilde, nicht der Charakter."""
    OPCODES = (0x921C,)
    character_id: int
    position: Position

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self | None:
        uvarint(p)
        position = _position(p, 24)
        return cls(_u32(p, 0), position) if valid(*position) else None


@dataclass(frozen=True)
class PartyList(Message):
    """Gruppenliste: je Mitglied Charakter-ID u32, 00 00, 2 Byte, Namenslänge, Name (geprüft)."""
    OPCODES = (0x9200, 0x920D)
    names: dict[int, str]  # Charakter-ID → Name

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        uvarint(p)
        names = {}
        for m in PARTY_NAME.finditer(p):
            start, length = m.start() + 9, m.group(2)[0]
            raw = p[start:start + length]
            try:
                name = raw.decode()
            except UnicodeDecodeError:
                continue
            if len(raw) == length and name.isalnum():
                names[struct.unpack("<I", m.group(1))[0]] = name
        return cls(names)


@dataclass(frozen=True)
class PartyHp(Message):
    """LP eines Gruppenmitglieds: Entity, LP, max. LP (Varints, Aufbau aus glass-cannon, MIT)."""
    OPCODES = (0x921B,)
    entity: int
    hp: int
    maximum: int

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        hp, length = uvarint(p, n)
        return cls(entity, hp, uvarint(p, n + length)[0])


@dataclass(frozen=True)
class FieldBossSlot:
    slot: int
    alive: bool
    position: Position | None
    time: float  # lebt: seit wann, tot: Respawn


@dataclass(frozen=True)
class FieldBossList(Message):
    """Feldbosse einer Karte: u16 0, Karte u32, Anzahl u8, je Boss: lebt u8, Platz-Varint, bei lebend
    x/y/z, u64 ms (geprüft). Kommt etwa jede Sekunde, solange die Karte im Spiel offen ist."""
    OPCODES = (0x9101,)
    map_id: int | None
    slots: tuple[FieldBossSlot, ...] | None  # None: Liste unlesbar (die Karte ist trotzdem offen)

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        uvarint(p)
        try:
            return cls(_u32(p, 2), tuple(cls._slots(p)))
        except (ValueError, struct.error, IndexError):
            return cls(None, None)

    @staticmethod
    def _slots(p: bytes) -> list[FieldBossSlot]:
        slots, i = [], 7
        for _ in range(p[6]):
            alive = p[i] == 1
            slot, length = uvarint(p, i + 1)
            i += 1 + length
            position = None
            if alive:
                position, i = _position(p, i), i + 12
            ms = struct.unpack_from("<Q", p, i)[0]
            if ms and not PLAUSIBLE_MS[0] < ms < PLAUSIBLE_MS[1]:  # Variante mit einem Byte mehr
                i += 1
                ms = struct.unpack_from("<Q", p, i)[0]
            i += 8
            slots.append(FieldBossSlot(slot, alive, position, ms / 1000))
        return slots


@dataclass(frozen=True)
class Effect(Message):
    """Status auf einer Entity: Entity, 01, Flags u8, Instanz, Effekt-ID u32, Dauer i64 ms (Aufbau aus dem
    A2Tools-Kern, capture/abnormal.rs), am Ende die Position. Mit eigener Entity eine Positionsquelle, im
    Kampf aber oft die Position des Effekts (unsicher)."""
    OPCODES = (0x382A,)
    entity: int
    applied: tuple[int, int, float] | None  # (Instanz, Effekt-ID, Dauer s), falls ein Effekt landet
    head: bytes  # die 12 Byte nach der Entity: die Status-ID steht je nach Zähler-Länge 4–6 Byte dahinter
    position: Position | None

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        applied = None
        if p[n:n + 1] == b"\x01":
            instance, length = uvarint(p, n + 2)
            effect, duration_ms = struct.unpack_from("<Iq", p, n + 2 + length)
            applied = (instance, effect, duration_ms / 1000)
        return cls(entity, applied, p[n:n + 12], _position_or_none(p, len(p) - 12))

    def has_status(self, status_id: int) -> bool:
        return struct.pack("<I", status_id) in self.head


@dataclass(frozen=True)
class EffectGone(Message):
    """Effekte enden: Entity, Anzahl u8, je Effekt: Art u8, Instanz, Grund u8 … Gelesen wird nur der erste,
    wie im Plugin Boss Callouts (taengu/A2Tools-Plugins)."""
    OPCODES = (0x382C,)
    entity: int
    instance: int

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self | None:
        entity, n = uvarint(p)
        return cls(entity, uvarint(p, n + 2)[0]) if len(p) > n + 2 else None


def _target(p: bytes, n: int) -> int | None:
    return uvarint(p, n + 7)[0] if len(p) > n + 7 else None


@dataclass(frozen=True)
class Cast(Message):
    """Skill geht los: Caster, 00, Skill u32, 2 Byte, Ziel (geprüft). Im eigenen Cast stehen x/y/z ab
    Byte 17 (ungeprüft, im Kampf oft die beste Positionsquelle)."""
    OPCODES = (0x3802,)
    POSITION_AT: ClassVar[int] = 17
    entity: int
    skill: int | None  # None: nur die Position war lesbar
    target: int | None
    position: Position | None

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        position = _position(p, cls.POSITION_AT) if len(p) >= cls.POSITION_AT + 12 else None
        try:
            return cls(entity, _u32(p, n + 1), _target(p, n), position)
        except (ValueError, struct.error):
            return cls(entity, None, None, position)


@dataclass(frozen=True)
class CastBar(Message):
    """Cast-Leiste beginnt (kommt vor 0x3802): Caster, Flag u8, Skill u32, 2 Byte, Ziel. Aus dem Plugin
    Boss Callouts, im eigenen Mitschnitt noch nicht geprüft."""
    OPCODES = (0x3809,)
    entity: int
    skill: int
    target: int | None

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        return cls(entity, _u32(p, n + 1), _target(p, n))


@dataclass(frozen=True)
class Wave(Message):
    """Spätere Treffer eines Skills (Vakrons Wellen): Caster, u8, Quelle, Skill u32 (Quelle wie CastBar)."""
    OPCODES = (0x3803,)
    entity: int
    skill: int

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        return cls(entity, _u32(p, n + 1 + uvarint(p, n + 1)[1]))


@dataclass(frozen=True)
class Hit(Message):
    """Treffer: Ziel, Flags u16, Angreifer, Skill u32 … (Aufbau aus glass-cannon, MIT)."""
    OPCODES = (0x3804,)
    entity: int  # das Ziel
    attacker: int
    skill: int

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        attacker, length = uvarint(p, n + 2)
        return cls(entity, attacker, _u32(p, n + 2 + length))


@dataclass(frozen=True)
class GroundMarker(Message):
    """Boden-Markierung eines Skills (glass-cannon, MIT): Caster, Skill u32, Cast-ID u8, u32, u16, x/y/z,
    Richtung, ms bis zum Einschlag u16. Nur der Mittelpunkt, keine Größe und Form."""
    OPCODES = (0x3848,)
    entity: int
    skill: int
    x: float
    y: float
    seconds: float  # bis zum Einschlag

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self | None:
        entity, n = uvarint(p)
        if len(p) != n + 29:
            return None
        x, y, _ = _position(p, n + 11)
        return cls(entity, _u32(p, n), x, y, struct.unpack_from("<H", p, n + 27)[0] / 1000)


@dataclass(frozen=True)
class Stagger(Message):
    """Stagger-Leiste: Entity, Flags, Zustand, Max u32 und Wert u32 (falls da), Status. Flags 0 = gebrochen."""
    OPCODES = (0xE005,)
    READY: ClassVar[int] = 0x02  # Bit im Status: jetzt brechbar
    entity: int
    broken: bool
    ready: bool | None  # None: Aufbau unbekannt

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        flags = p[n]
        if flags == 0:
            return cls(entity, True, None)
        end = n + 2 + 4 * bool(flags & 1) + 4 * bool(flags & 2)
        known = not flags & ~3 and len(p) > end
        return cls(entity, False, bool(p[end] & cls.READY) if known else None)


@dataclass(frozen=True)
class FightState(Message):
    """Kampf an/aus: Entity, Flags u8, Zustand u8, bei Flag 1 Berserker-Zeit u64 ms (glass-cannon)."""
    OPCODES = (0x8D21,)
    entity: int
    active: bool
    berserk_at: float | None  # Sekunden seit 1970

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        entity, n = uvarint(p)
        active = p[n + 1] != 0
        berserk = struct.unpack_from("<Q", p, n + 2)[0] / 1000 if active and p[n] & 1 else None
        return cls(entity, active, berserk)


@dataclass(frozen=True)
class DungeonRun(Message):
    """Dungeon-Lauf: Dungeon u32, Status (2 läuft, 3 geschafft), Start u64 ms, Ende u64 ms (geprüft)."""
    OPCODES = (0x6100,)
    RUNNING: ClassVar[int] = 2
    ends_at: float | None  # Zeitlimit, solange der Lauf läuft

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        uvarint(p)
        return cls(struct.unpack_from("<Q", p, 13)[0] / 1000 if p[4] == cls.RUNNING else None)


@dataclass(frozen=True)
class Death(Message):
    """CharDie_NT (Name wie im Desktop-Programm von questlog.gg): Opfer, Skill u32, Täter, Server u16,
    Name des Täters (nur bei einem Spieler als Täter)."""
    OPCODES = (0x8D04,)
    victim: int
    skill: int
    killer_name: str

    @classmethod
    def read(cls, opcode: int, p: bytes) -> Self:
        r = Reader(p)
        victim, skill = r.varint(), r.i32()
        r.varint()  # Täter
        r.u16()  # Server des Täters
        return cls(victim, skill, r.text())
