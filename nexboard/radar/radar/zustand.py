"""Radar-Zustand: wertet die Server-Nachrichten aus und merkt sich Cubes und Position.

Koordinaten sind in Zentimetern. Was am eigenen Mitschnitt geprueft ist, steht
bei den Opcodes. Die Cube-IDs stammen zum Teil vom Vorlaeufer-Projekt.
"""
from __future__ import annotations

import json
import math
import re
import struct
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import daten
from .protokoll import uvarint
from .pvp import OPCODES as PVP_OPCODES, PvpSitzung

OP_SPAWN = 0x3634     # Objekt erscheint: Entity, 2 Byte, Objekt-ID u32, x/y/z, 8 Byte, 01 01, Zustand u8,
                      # seit u64 ms (Format aus a2kit, am Cube geprueft)
OP_WEG = 0x3635       # Objekt verschwindet, auch nach dem Oeffnen (geprueft)
OP_OEFFNEN = 0x3638   # Spieler beginnt ein Objekt zu oeffnen: Objekt-Entity, Spieler-Entity (aus aion2cubedetector,
                      # am Cube geprueft: 4 s spaeter 0x363A = fertig)
OP_POSITION = 0x382B  # Status-Variante mit Position am Ende, wie 0x382A (verdoppelt die eigenen Positionen)
OP_BEWEGUNG = 0x371A  # Bewegung: Entity, 2 Byte, x/y/z
OP_CHARAKTER = 0x3633 # Spieler erscheint, enthaelt den Namen (geprueft)
OP_TELEPORT = 0x3623  # eigener Teleport/Zonenwechsel mit Position ab Byte 6 (geprueft)
OP_SYNC = 0x8D00      # traegt meist die eigene Entity-ID (geprueft)
OP_CAST = 0x3802      # Cast-Beginn: Caster, 00, Skill u32, 2 Byte, Ziel (geprueft)
OP_ZONE = 0x4002      # eigener Zonenwechsel: Zonen-ID u32, im Dungeon die Dungeon-ID (geprueft)
OP_NPC = 0x3641       # NPC erscheint: Entity, 3 Byte, NPC-ID u32 (geprueft)
OP_SPIELER = 0x3645   # anderer Spieler erscheint: Entity, 4 Byte, Namenslaenge, Name (geprueft)
OP_GRUPPE = 0x921C    # Gruppenmitglied, etwa alle 2 s: Charakter-ID u32, Zone u32 ab Byte 12,
                      # x/y/z ab Byte 24. Der Name ab Byte 49 ist die Gilde, nicht der Charakter
OP_GRUPPENLISTE = (0x9200, 0x920D)  # enthalten je Mitglied: Charakter-ID u32, 00 00, 2 Byte,
                                    # Namenslaenge, Name (geprueft)
GRUPPEN_NAME = re.compile(rb"(?=(....)\x00\x00..([\x02-\x18]))", re.S)
OP_FELDBOSSE = 0x9101 # Feldbosse einer Karte: u16 0, Karte u32, Anzahl u8, je Boss: lebt u8,
                      # Platz-Varint, bei lebend x/y/z, u64 ms (lebt: seit, tot: Respawn) (geprueft)
OP_VERTRAUTE = 0x9000 # alle Vertrauten: u32, Varint N, N x (id, id, Stufe) u32, Varint M, M x (id, Seelen)
OP_SEELE = 0x900D     # neue Seele: 01, id u32, Anzahl u32
OP_STUFE = 0x9014     # neue Stufe: u16 0, id u32, Stufe u32 (Opcodes aus aion2assistant, Formate geprueft)
OP_STAGGER = 0xE005   # Stagger-Leiste: Entity, 03 01, Max u32, Wert u32, Status. Kurz (Entity, 00 ..) = gebrochen
OP_DUNGEON = 0x6100   # Dungeon-Lauf: Dungeon u32, Status (2 laeuft, 3 geschafft), Start u64 ms, Ende u64 ms (geprueft)
OP_EFFEKT = 0x382A    # Status auf einer Entity (Ziel, 2 Byte, Zaehler, Status-ID u32, Dauer u32 ms, ...)
                      # mit Position am Ende. Mit eigener ID die einzige
                      # Positionsquelle, im Kampf aber oft die Position des Effekts (unsicher)

# Objekt-IDs der Hidden Cubes. 1301199 am echten Cube bestaetigt, Rest vom Vorlaeufer.
CUBE_IDS = {
    1000295, 1000548, 1000556, 1000566, 1000567, 1000568, 1100056, 1100094,
    1200018, 1200036, 1200037, 1200039, 1200040, 1200041, 1200667, 1200707,
    1201054, 1201055, 1300754, 1301199, 1301200, 1401335, 1401336, 3682560,
}

# Boss-NPC-ID -> Dungeon und Zonen-ID -> Dungeon, erzeugt mit `python -m werkzeuge.bosse`
BOSSE: dict[int, str] = {int(k): v for k, v in
                         json.loads((Path(__file__).parent / "bosse.json").read_text()).items()}
ZONEN: dict[int, str] = {int(k): v for k, v in
                         json.loads((Path(__file__).parent / "zonen.json").read_text()).items()}


def gueltig(*werte: float) -> bool:
    return all(math.isfinite(v) and abs(v) < 1_000_000 for v in werte)


@dataclass
class Cube:
    eid: int
    objekt_id: int
    x: float
    y: float
    z: float
    seit: float = field(default_factory=time.time)  # seit wann der Cube steht (Serverzeit, sonst gesehen)
    oeffner: str = ""  # wer ihn gerade oeffnet


class RadarZustand:
    def __init__(self, charname: str = "", spawn_log: Path | None = None,
                 extra_ids: set[int] = frozenset(), speichern: bool = False) -> None:
        self.lock = threading.Lock()
        self.charname = charname
        self.namen = (charname.encode(), charname.encode("utf-16le")) if charname else ()
        self.cube_ids = CUBE_IDS | set(extra_ids)
        self.spawn_log = spawn_log
        self.eigene_eid: int | None = None
        self.eid_ueber_name = False
        self._sync_zaehler: Counter[int] = Counter()
        self.position: tuple[float, float, float] | None = None
        self.position_zeit = 0.0
        self.cubes: dict[int, Cube] = {}
        self.dungeon: str | None = None  # beim Betreten (0x4002), sonst am ersten Boss
        self.gruppe: dict[int, tuple[float, float, float, float]] = {}  # Charakter-ID -> x, y, z, zeit
        self.charnamen: dict[int, str] = {}   # Charakter-ID -> Name (aus den Gruppenlisten)
        self.spieler: dict[int, str] = {}     # Entity -> Name, fuer "Todesmal auf ..."
        self.bosse: dict[int, int] = {}       # Entity -> Boss-NPC-ID
        self.zone: int | None = None
        # live gespeichert, damit Timer und Seelen einen Neustart ueberleben (nicht beim Abspielen alter Mitschnitte)
        self.speichern = speichern
        self.feldbosse: dict[str, dict] = daten.laden("feldbosse.json") if speichern else {}  # Platz -> Daten
        self.vertraute: dict[str, list[int]] = daten.laden("vertraute.json") if speichern else {}  # id -> [Stufe, Seelen]
        self.vertraute_stand = 0  # zaehlt Aenderungen, damit die Liste nur dann neu gebaut wird
        self.nachrichten = 0
        # Rueckrufe: neuer Cube, Cast (caster, skill, ziel)
        self.bei_neuem_cube: list[Callable[[Cube], None]] = []
        self.bei_cast: list[Callable[[int, int, int | None], None]] = []
        self.bei_status: list[Callable[[int, int], None]] = []  # (Ziel, Status-ID), nur IDs aus status_ids
        self.bei_groggy: list[Callable[[int], None]] = []       # Boss-Entity, deren Stagger-Leiste bricht
        self.status_ids: set[int] = set()
        self.dungeon_ende: float | None = None  # Zeitlimit des laufenden Dungeons (Sekunden seit 1970)
        self.pvp = PvpSitzung(self)

    def verarbeiten(self, op: int, p: bytes) -> None:
        self.nachrichten += 1
        try:
            eid, n = uvarint(p)
            if op == OP_SPAWN:
                self._spawn(eid, p, n)
            elif op == OP_WEG:
                with self.lock:
                    self.cubes.pop(eid, None)
            elif op in (OP_CHARAKTER, OP_SPIELER):
                self.spieler[eid] = p[n + 6:n + 6 + p[n + 5]].decode("utf-8", "replace")
                if op == OP_CHARAKTER and any(name in p[:64] for name in self.namen):
                    self.eigene_eid, self.eid_ueber_name = eid, True
            elif op == OP_SYNC and not self.eid_ueber_name:
                self._sync(eid)
            elif op == OP_TELEPORT:
                # Entity-IDs gelten nur bis zum naechsten Teleport/Zonenwechsel
                with self.lock:
                    self.cubes.clear()
                self.eigene_eid, self.eid_ueber_name = None, False
                self._position(*struct.unpack_from("<fff", p, n + 5))
            elif op == OP_ZONE:
                self.zone = struct.unpack_from("<I", p, 0)[0]
                self.dungeon = ZONEN.get(self.zone)  # None = kein Dungeon
            elif op == OP_NPC:
                npc = struct.unpack_from("<I", p, n + 3)[0]
                if npc in BOSSE:
                    self.dungeon, self.bosse[eid] = BOSSE[npc], npc
                elif npc in daten.feldboss_npcs():
                    self._feldboss_name(npc, struct.unpack_from("<fff", p, n + 9))
            elif op == OP_GRUPPE:
                self._gruppe(p)
            elif op in OP_GRUPPENLISTE:
                self._gruppenliste(p)
            elif op == OP_FELDBOSSE:
                self._feldbosse(p)
            elif op in (OP_VERTRAUTE, OP_SEELE, OP_STUFE):
                self._vertraute(op, p)
            elif op == OP_EFFEKT:
                for sid in self.status_ids:  # Status-ID steht je nach Zaehler-Laenge 4-6 Byte nach der Entity
                    if struct.pack("<I", sid) in p[n:n + 12]:
                        for f in self.bei_status:
                            f(eid, sid)
                if eid == self.eigene_eid:
                    self._position(*struct.unpack_from("<fff", p, len(p) - 12))
            elif op == OP_POSITION and eid == self.eigene_eid:
                self._position(*struct.unpack_from("<fff", p, len(p) - 12))
            elif op == OP_BEWEGUNG and eid == self.eigene_eid:
                self._position(*struct.unpack_from("<fff", p, n + 2))
            elif op == OP_OEFFNEN and eid in self.cubes:
                spieler = uvarint(p, n)[0]
                self.cubes[eid].oeffner = self.spieler.get(spieler, "?")
            elif op == OP_STAGGER and p[n] == 0 and eid in self.bosse:
                for f in self.bei_groggy:
                    f(eid)
            elif op == OP_DUNGEON:
                laeuft = p[4] == 2
                self.dungeon_ende = struct.unpack_from("<Q", p, 13)[0] / 1000 if laeuft else None
            elif op in PVP_OPCODES:
                self.pvp.verarbeiten(op, p)
            elif op == OP_CAST and self.bei_cast:
                skill = struct.unpack_from("<I", p, n + 1)[0]
                ziel = uvarint(p, n + 7)[0] if len(p) > n + 7 else None
                for f in self.bei_cast:
                    f(eid, skill, ziel)
        except (ValueError, struct.error):
            pass  # kaputte oder unbekannte Nachricht

    def _spawn(self, eid: int, p: bytes, n: int) -> None:
        objekt_id = struct.unpack_from("<I", p, n + 2)[0]
        x, y, z = struct.unpack_from("<fff", p, n + 6)
        if not gueltig(x, y, z):
            return
        if self.spawn_log:
            self._loggen(eid, objekt_id, x, y, z)
        if objekt_id not in self.cube_ids:
            return
        cube = Cube(eid, objekt_id, x, y, z)
        if p[n + 26:n + 28] == b"\x01\x01":
            seit = struct.unpack_from("<Q", p, n + 29)[0] / 1000
            if 0 < time.time() - seit < 86400:  # nur plausible Zeiten (letzte 24 h)
                cube.seit = seit
        with self.lock:
            neu = eid not in self.cubes
            self.cubes[eid] = cube
        if neu:
            for f in self.bei_neuem_cube:
                f(cube)

    def _gruppe(self, p: bytes) -> None:
        x, y, z = struct.unpack_from("<fff", p, 24)
        if gueltig(x, y, z):
            with self.lock:
                self.gruppe[struct.unpack_from("<I", p, 0)[0]] = (x, y, z, time.time())

    def _gruppenliste(self, p: bytes) -> None:
        for m in GRUPPEN_NAME.finditer(p):
            start, laenge = m.start() + 9, m.group(2)[0]
            roh = p[start:start + laenge]
            try:
                name = roh.decode()
            except UnicodeDecodeError:
                continue
            if len(roh) == laenge and name.isalnum():
                self.charnamen[struct.unpack("<I", m.group(1))[0]] = name

    def _feldbosse(self, p: bytes) -> None:
        karte, anzahl, i = struct.unpack_from("<I", p, 2)[0], p[6], 7
        neu = {}
        for _ in range(anzahl):
            lebt = p[i] == 1
            platz, k = uvarint(p, i + 1)
            i += 1 + k
            pos = None
            if lebt:
                pos, i = struct.unpack_from("<fff", p, i), i + 12
            zeit = struct.unpack_from("<Q", p, i)[0]
            if zeit and not 1.6e12 < zeit < 2.6e12:  # Variante mit einem Byte mehr
                i += 1
                zeit = struct.unpack_from("<Q", p, i)[0]
            i += 8
            alt = self.feldbosse.get(str(platz), {})
            neu[str(platz)] = {"karte": karte, "lebt": lebt, "pos": pos or alt.get("pos"),
                               "zeit": zeit / 1000, "npc": alt.get("npc")}
        if any(self.feldbosse.get(k) != v for k, v in neu.items()):
            self.feldbosse.update(neu)
            self._speichern("feldbosse.json", self.feldbosse)

    def _feldboss_name(self, npc: int, pos: tuple[float, float, float]) -> None:
        """Ein Boss, der hoechstens 50 m neben einem Feldboss-Platz erscheint, ist dieser Feldboss."""
        for platz in self.feldbosse.values():
            if platz["pos"] and platz["npc"] != npc and math.dist(platz["pos"], pos) < 5000:
                platz["npc"] = npc
                self._speichern("feldbosse.json", self.feldbosse)

    def _vertraute(self, op: int, p: bytes) -> None:
        if op == OP_VERTRAUTE:
            stand, i = {}, 4
            for groesse in (12, 8):  # erst Stufen (id, id, Stufe), dann Seelen (id, Seelen)
                anzahl, k = uvarint(p, i)
                i += k
                for _ in range(anzahl):
                    vid, wert = struct.unpack_from("<I", p, i)[0], struct.unpack_from("<I", p, i + groesse - 4)[0]
                    stand.setdefault(str(vid), [0, 0])[0 if groesse == 12 else 1] = wert
                    i += groesse
            self.vertraute = stand
        elif op == OP_SEELE and p[0] == 1:
            vid, anzahl = struct.unpack_from("<II", p, 1)
            self.vertraute.setdefault(str(vid), [0, 0])[1] += anzahl
        elif op == OP_STUFE:
            vid, stufe = struct.unpack_from("<II", p, 2)
            self.vertraute.setdefault(str(vid), [0, 0])[0] = stufe
        self.vertraute_stand += 1
        self._speichern("vertraute.json", self.vertraute)

    def _speichern(self, name: str, inhalt: dict) -> None:
        if self.speichern:
            daten.speichern(name, inhalt)

    def _sync(self, eid: int) -> None:
        """Ohne Namenstreffer: die haeufigste Entity-ID in 0x8D00 ist die eigene."""
        self._sync_zaehler[eid] += 1
        if sum(self._sync_zaehler.values()) >= 100:
            self.eigene_eid = self._sync_zaehler.most_common(1)[0][0]
            self._sync_zaehler.clear()

    def _position(self, x: float, y: float, z: float) -> None:
        if gueltig(x, y, z):
            with self.lock:
                self.position, self.position_zeit = (x, y, z), time.time()

    def _loggen(self, eid: int, objekt_id: int, x: float, y: float, z: float) -> None:
        zeile = {"t": round(time.time(), 2), "eid": eid, "objekt_id": objekt_id,
                 "x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                 "cube": objekt_id in self.cube_ids}
        try:
            with open(self.spawn_log, "a") as f:
                f.write(json.dumps(zeile) + "\n")
        except OSError:
            pass

    def schnappschuss(self) -> dict:
        with self.lock:
            return {
                "eid": self.eigene_eid,
                "eid_ueber_name": self.eid_ueber_name,
                "position": self.position,
                "position_alter": time.time() - self.position_zeit if self.position else None,
                "cubes": list(self.cubes.values()),
                "dungeon": self.dungeon,
                "feldbosse": [b for b in self.feldbosse.values()
                              if b["lebt"] and b["pos"] and b["karte"] == self.zone],
                "gruppe": [(self.charnamen.get(cid, ""), *g) for cid, g in self.gruppe.items()
                           if time.time() - g[3] < 10],
                "nachrichten": self.nachrichten,
            }
