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
from .protokoll import Leser, uvarint
from .pvp import OPCODES as PVP_OPCODES
from .pvp import PvpSitzung

OP_SPAWN = 0x3634     # Objekt erscheint: Entity, 2 Byte, Objekt-ID u32, x/y/z, 8 Byte, 01 01, Zustand u8,
                      # seit u64 ms (Format aus a2kit, am Cube geprueft)
OP_WEG = 0x3635       # Objekt verschwindet, auch nach dem Oeffnen (geprueft)
OP_OEFFNEN = 0x3638   # Spieler beginnt ein Objekt zu oeffnen: Objekt-Entity, Spieler-Entity (aus aion2cubedetector,
                      # am Cube geprueft: 4 s spaeter 0x363A = fertig)
OP_POSITION = 0x382B  # Status-Variante mit Position am Ende, wie 0x382A (verdoppelt die eigenen Positionen)
OP_BEWEGUNG = 0x371A  # Bewegung: Entity, 2 Byte, x/y/z
# Ungeprueft, aus benhighlanderr/Aion2-Hidden-Cube-Radar (ohne Lizenz, nur die Erkenntnis uebernommen).
# Diese Quellen gehen ueber _position_pruefen, damit ein falscher Wert die Position nicht verdirbt.
OP_BEWEGUNG_ALLE = range(0x3710, 0x3751)  # weitere Bewegungsarten, gleicher Aufbau wie 0x371A
OP_EINTRITT = 0x3621  # eigener Charakter betritt die Welt: Entity, ..., x/y/z ab Byte 16
OP_ZONE_POS = 0x561E  # Zonenwechsel mit Position ab Byte 17
CAST_POS = 17         # im eigenen Cast (0x3802) stehen x/y/z ab Byte 17
MAX_SPRUNG_CM = 3000  # ungepruefte Position: hoechstens 30 m neben der letzten ...
SPRUNG_ALTER_S = 10   # ... ausser die letzte ist aelter
KURS_AB_CM = 100      # Laufrichtung erst ab 1 m Weg neu bestimmen
OP_CHARAKTER = 0x3633 # Spieler erscheint, enthaelt den Namen (geprueft)
OP_TELEPORT = 0x3623  # eigener Teleport/Zonenwechsel mit Position ab Byte 6 (geprueft)
OP_SYNC = 0x8D00      # Punkte einer Entity (HP, MP, ...): Entity, Flags u8, bei Flag 1 Varint N, N x (Art u8, i32).
                      # MP und SP (Art 1, 3) schickt der Server nur fuer den eigenen Charakter (geprueft)
EIGENE_PUNKTE = {1, 3}
OP_CAST = 0x3802      # Skill geht los: Caster, 00, Skill u32, 2 Byte, Ziel (geprueft)
# Aus taengu/A2Tools-Plugins (Boss Callouts), noch nicht im eigenen Mitschnitt geprueft:
OP_LEISTE = 0x3809    # Cast-Leiste beginnt (kommt vor 0x3802): Caster, Flag u8, Skill u32
OP_WELLE = 0x3803     # spaetere Treffer eines Skills (Vakrons Wellen): Caster, u8, Quelle, Skill u32
OP_EFFEKT_WEG = 0x382C  # Effekte enden: Entity, Anzahl u8, je Effekt: Art u8, Instanz, Grund u8, ...
# Boden-Markierung eines Skills (glass-cannon, MIT): Caster, Skill u32, Cast-ID u8, u32, u16, x/y/z, Richtung,
# ms bis zum Einschlag u16. Nur der Mittelpunkt, keine Groesse und Form.
OP_MARKIERUNG = 0x3848
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
# Kommt nach dem Brechen keine neue Leiste, gilt der Boss nach so vielen Sekunden wieder als nicht groggy
GROGGY_MAX_S = 8.0
OP_DUNGEON = 0x6100   # Dungeon-Lauf: Dungeon u32, Status (2 laeuft, 3 geschafft), Start u64 ms, Ende u64 ms (geprueft)
OP_TREFFER = 0x3804   # Treffer: Ziel, Flags u16, Angreifer, Skill u32, ... (Aufbau aus glass-cannon, MIT)
OP_KAMPF = 0x8D21     # Kampf an/aus: Entity, Flags u8, Zustand u8, bei Flag 1 Berserker-Zeit u64 ms (glass-cannon)
OP_GRUPPE_LP = 0x921B # LP eines Gruppenmitglieds: Entity, LP, max. LP (Varints, glass-cannon)
OP_GEOEFFNET = 0x363A # Objekt fertig geoeffnet; beim Cube steht am Ende der verbrauchte Schluessel
CUBE_SCHLUESSEL = 630900003  # Item, das beim Oeffnen eines Cubes verbraucht wird (aion2-cube-radar, AsseylumVA)
STAGGER_BEREIT = 0x02  # Bit im letzten Byte der Stagger-Leiste: jetzt brechbar
STAGGER_SPAET_S = 5.0  # erscheint die Leiste so lange nach dem Boss, ist es eine Stagger-Pruefung
OP_EFFEKT = 0x382A    # Status auf einer Entity (Ziel, 2 Byte, Zaehler, Status-ID u32, Dauer u32 ms, ...)
                      # mit Position am Ende. Mit eigener ID die einzige
                      # Positionsquelle, im Kampf aber oft die Position des Effekts (unsicher)

# Objekt-IDs der Hidden Cubes. 1301199 am echten Cube bestaetigt, Rest vom Vorlaeufer.
CUBE_IDS = {
    1000295, 1000548, 1000556, 1000566, 1000567, 1000568, 1100056, 1100094,
    1200018, 1200036, 1200037, 1200039, 1200040, 1200041, 1200667, 1200707,
    1201054, 1201055, 1300754, 1301199, 1301200, 1401335, 1401336, 3682560,
    # ungeprueft, aus benhighlanderr/Aion2-Hidden-Cube-Radar: Varianten 01_V01-V19 und 1300081/82
    *range(1000549, 1000566), 1300081, 1300082,
}

# Boss-NPC-ID -> Dungeon und Zonen-ID -> Dungeon, erzeugt mit `python -m werkzeuge.bosse`
BOSSE: dict[int, str] = {int(k): v for k, v in
                         json.loads((Path(__file__).parent / "bosse.json").read_text()).items()}
ZONEN: dict[int, str] = {int(k): v for k, v in
                         json.loads((Path(__file__).parent / "zonen.json").read_text()).items()}
# Boss-Mechaniken (mechaniken.json). Bosse, die A2Tools nicht als Boss fuehrt, kommen von dort dazu
MECHANIKEN: list[dict] = json.loads((Path(__file__).parent / "mechaniken.json").read_text())["mechaniken"]
for _m in MECHANIKEN:
    for _npc in _m["bosse"]:
        BOSSE.setdefault(_npc, _m["dungeon"])
STAGGER_BOSSE = {npc for m in MECHANIKEN if m["wann"]["art"] == "stagger" for npc in m["bosse"]}
# Boss-Ansagen aus dem A2Tools-Plugin (ansagen.json, erzeugt mit `python -m werkzeuge.ansagen`)
BOSS_ANSAGEN: dict = json.loads((Path(__file__).parent / "ansagen.json").read_text())


KARTE_OFFEN_S = 2.5  # so lange nach der letzten Feldboss-Liste gilt die Ingame-Karte als offen


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
        self.eid_sicher = False
        self._sync_zaehler: Counter[int] = Counter()
        self.position: tuple[float, float, float] | None = None
        self.position_zeit = 0.0
        self.kurs: tuple[float, float] | None = None  # Laufrichtung als Einheitsvektor (Welt x, y)
        self._kurs_von: tuple[float, float] | None = None
        self.cubes: dict[int, Cube] = {}
        self.dungeon: str | None = None  # beim Betreten (0x4002), sonst am ersten Boss
        self.gruppe: dict[int, tuple[float, float, float, float]] = {}  # Charakter-ID -> x, y, z, zeit
        self.charnamen: dict[int, str] = {}   # Charakter-ID -> Name (aus den Gruppenlisten)
        self.spieler: dict[int, str] = {}     # Entity -> Name, fuer "Todesmal auf ..."
        self.bosse: dict[int, int] = {}       # Entity -> Boss-NPC-ID
        self.groggy_seit: dict[int, float] = {}  # Boss-Entity -> Zeit, seit die Stagger-Leiste gebrochen ist
        self.boss_seit: dict[int, float] = {}    # Boss-Entity -> Zeit, seit er erschienen ist
        self.leiste_bereit: dict[int, bool] = {}  # Boss-Entity -> war die Leiste zuletzt brechbar
        self.berserker: dict[int, float] = {}    # Boss-Entity -> Berserker-Zeit (Sekunden seit 1970)
        self.schluessel = 0  # verbrauchte Cube-Schluessel seit dem Start
        self.zone: int | None = None
        self.karte_offen_zeit = 0.0  # letzte Feldboss-Liste: kommt etwa jede Sekunde, solange die Ingame-Karte offen ist
        # live gespeichert, damit Timer und Seelen einen Neustart ueberleben (nicht beim Abspielen alter Mitschnitte)
        self.speichern = speichern
        self.feldbosse: dict[str, dict] = daten.laden("feldbosse.json") if speichern else {}  # Platz -> Daten
        self.vertraute: dict[str, list[int]] = daten.laden("vertraute.json") if speichern else {}  # id -> [Stufe, Seelen]
        self.vertraute_stand = 0  # zaehlt Aenderungen, damit die Liste nur dann neu gebaut wird
        self.nachrichten = 0
        # Rueckrufe: neuer Cube, Cast (caster, skill, ziel)
        self.bei_neuem_cube: list[Callable[[Cube], None]] = []
        self.bei_cast: list[Callable[[int, int, int | None], None]] = []
        self.bei_leiste: list[Callable[[int, int], None]] = []  # (Caster, Skill), Cast-Leiste beginnt
        self.bei_welle: list[Callable[[int, int], None]] = []   # (Caster, Skill), spaeterer Treffer
        # (Entity, Instanz, Effekt-ID, Dauer s), nur IDs aus effekt_ids; und (Entity, Instanz), Effekt endet
        self.bei_effekt: list[Callable[[int, int, int, float], None]] = []
        self.bei_effekt_weg: list[Callable[[int, int], None]] = []
        self.effekt_ids: set[int] = set()
        self.bei_status: list[Callable[[int, int], None]] = []  # (Ziel, Status-ID), nur IDs aus status_ids
        self.bei_groggy: list[Callable[[int], None]] = []       # Boss-Entity, deren Stagger-Leiste bricht
        self.bei_hp: list[Callable[[int], None]] = []           # eigene aktuelle HP
        self.bei_staggern: list[Callable[[int], None]] = []     # Boss-Entity, deren Leiste brechbar wird
        self.bei_treffer: list[Callable[[int], None]] = []      # Skill, der dich trifft, nur IDs aus treffer_ids
        self.bei_gruppe_lp: list[Callable[[int, float], None]] = []  # (Entity, LP-Anteil 0-1)
        self.bei_tod: list[Callable[[int, int, str], None]] = []
        self.bei_flaeche: list[Callable[[int, float, float, float], None]] = []  # (Skill, x, y, s bis Einschlag)  # (Opfer, Skill, Name des Taeters oder "")
        self.status_ids: set[int] = set()
        self.treffer_ids: set[int] = set()
        self.dungeon_ende: float | None = None  # Zeitlimit des laufenden Dungeons (Sekunden seit 1970)
        self.pvp = PvpSitzung(self)

    def _stagger(self, boss: int, p: bytes, n: int) -> None:
        """Gebrochene Leiste (Flags 0): Boss ist groggy. Jede andere Leisten-Nachricht heißt, die
        Leiste läuft wieder, also ist es vorbei. Bei Bossen mit Stagger-Prüfung zusätzlich melden,
        wenn die Leiste brechbar wird."""
        if p[n] == 0:
            self.groggy_seit[boss] = time.time()
            self.leiste_bereit[boss] = False
            for f in self.bei_groggy:
                f(boss)
            return
        self.groggy_seit.pop(boss, None)
        if self.bosse[boss] in STAGGER_BOSSE:
            self._stagger_pruefung(boss, p, n)

    def _stagger_pruefung(self, boss: int, p: bytes, n: int) -> None:
        """Brechbar nach einer Pause oder eine Leiste, die erst spaeter im Kampf erscheint = Pruefung.
        Eine Leiste, die von Anfang an brechbar ist, gehoert zum Boss selbst (glass-cannon: Lakshmi)."""
        flags = p[n]
        ende = n + 2 + 4 * bool(flags & 1) + 4 * bool(flags & 2)  # Flags, Zustand, Max und Wert, falls da
        if flags & ~3 or len(p) <= ende:
            return  # Aufbau unbekannt: lieber nichts melden
        bereit = bool(p[ende] & STAGGER_BEREIT)
        vorher = self.leiste_bereit.get(boss)
        self.leiste_bereit[boss] = bereit
        spaet = time.time() - self.boss_seit.get(boss, time.time()) >= STAGGER_SPAET_S
        if bereit and (vorher is False or (vorher is None and spaet)):
            for f in self.bei_staggern:
                f(boss)

    def _kampf(self, eid: int, p: bytes, n: int) -> None:
        """Berserker-Zeit eines Bosses merken; Kampf vorbei (Zustand 0) = weg."""
        if eid not in self.bosse:
            return
        if p[n + 1] == 0:
            self.berserker.pop(eid, None)
        elif p[n] & 1:
            self.berserker[eid] = struct.unpack_from("<Q", p, n + 2)[0] / 1000

    def boss_groggy(self, jetzt: float | None = None) -> bool:
        """Ist gerade ein Boss groggy? Für andere Programme, unabhängig davon, ob die Warnung angezeigt wird."""
        jetzt = time.time() if jetzt is None else jetzt
        return any(jetzt - seit < GROGGY_MAX_S for seit in self.groggy_seit.values())

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
                    self.eigene_eid, self.eid_sicher = eid, True
            elif op == OP_SYNC:
                self._sync(eid, p, n)
                # eigene aktuelle HP, nur bei sicher erkanntem Charakter (sonst evtl. der Boss)
                if self.eid_sicher and eid == self.eigene_eid and p[n:n + 3] == b"\x02\x01\x00":
                    for f in self.bei_hp:
                        f(struct.unpack_from("<I", p, n + 3)[0])
            elif op == OP_TELEPORT:
                # Entity-IDs gelten nur bis zum naechsten Teleport/Zonenwechsel
                with self.lock:
                    self.cubes.clear()
                self.eigene_eid, self.eid_sicher = None, False
                self._position(*struct.unpack_from("<fff", p, n + 5))
            elif op == OP_ZONE:
                self.zone = struct.unpack_from("<I", p, 0)[0]
                self.dungeon = ZONEN.get(self.zone)  # None = kein Dungeon
            elif op == OP_NPC:
                npc = struct.unpack_from("<I", p, n + 3)[0]
                if npc in BOSSE:
                    self.dungeon, self.bosse[eid] = BOSSE[npc], npc
                    self.boss_seit[eid] = time.time()
                elif npc in daten.feldboss_npcs():
                    self._feldboss_name(npc, struct.unpack_from("<fff", p, n + 9))
            elif op == OP_GRUPPE:
                self._gruppe(p)
            elif op in OP_GRUPPENLISTE:
                self._gruppenliste(p)
            elif op == OP_FELDBOSSE:
                self.karte_offen_zeit = time.time()
                self._feldbosse(p)
            elif op in (OP_VERTRAUTE, OP_SEELE, OP_STUFE):
                self._vertraute(op, p)
            elif op == OP_EFFEKT:
                self._effekt(eid, p, n)
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
            elif op in OP_BEWEGUNG_ALLE and eid == self.eigene_eid:
                self._position_pruefen(*struct.unpack_from("<fff", p, n + 2))
            elif op == OP_EINTRITT and len(p) >= 28:
                if self.eigene_eid is None:
                    self.eigene_eid = eid  # nur geschaetzt; Name oder MP/SP machen sie sicher
                if eid == self.eigene_eid:
                    self._position_pruefen(*struct.unpack_from("<fff", p, 16))
            elif op == OP_ZONE_POS and len(p) >= 29:
                self._position_pruefen(*struct.unpack_from("<fff", p, 17))
            elif op == OP_OEFFNEN and eid in self.cubes:
                spieler = uvarint(p, n)[0]
                self.cubes[eid].oeffner = self.spieler.get(spieler, "?")
            elif op == OP_STAGGER and eid in self.bosse:
                self._stagger(eid, p, n)
            elif op == OP_TREFFER and eid == self.eigene_eid and self.bei_treffer:
                angreifer_laenge = uvarint(p, n + 2)[1]  # nach den 2 Flag-Bytes
                skill = struct.unpack_from("<I", p, n + 2 + angreifer_laenge)[0]
                if skill in self.treffer_ids:
                    for f in self.bei_treffer:
                        f(skill)
            elif op == OP_KAMPF:
                self._kampf(eid, p, n)
            elif op == OP_GRUPPE_LP and eid != self.eigene_eid:
                lp, laenge = uvarint(p, n)
                maximal = uvarint(p, n + laenge)[0]
                if maximal:
                    for f in self.bei_gruppe_lp:
                        f(eid, lp / maximal)
            elif op == OP_GEOEFFNET and struct.pack("<I", CUBE_SCHLUESSEL) in p[-12:]:
                self.schluessel += 1
            elif op == OP_DUNGEON:
                laeuft = p[4] == 2
                self.dungeon_ende = struct.unpack_from("<Q", p, 13)[0] / 1000 if laeuft else None
            elif op in PVP_OPCODES:
                self.pvp.verarbeiten(op, p)
            elif op == OP_MARKIERUNG and len(p) == n + 29 and eid != self.eigene_eid and eid not in self.spieler:
                skill = struct.unpack_from("<I", p, n)[0]
                x, y, _z = struct.unpack_from("<fff", p, n + 11)
                bis = struct.unpack_from("<H", p, n + 27)[0] / 1000
                for f in self.bei_flaeche:
                    f(skill, x, y, bis)
            elif op == OP_CAST:
                if eid == self.eigene_eid and len(p) >= CAST_POS + 12:
                    self._position_pruefen(*struct.unpack_from("<fff", p, CAST_POS))  # im Kampf oft die beste Quelle
                skill = struct.unpack_from("<I", p, n + 1)[0]
                ziel = uvarint(p, n + 7)[0] if len(p) > n + 7 else None
                for f in self.bei_cast:
                    f(eid, skill, ziel)
            elif op == OP_LEISTE:
                skill = struct.unpack_from("<I", p, n + 1)[0]
                for f in self.bei_leiste:
                    f(eid, skill)
            elif op == OP_WELLE:
                quelle_laenge = uvarint(p, n + 1)[1]
                skill = struct.unpack_from("<I", p, n + 1 + quelle_laenge)[0]
                for f in self.bei_welle:
                    f(eid, skill)
            elif op == OP_EFFEKT_WEG and len(p) > n + 2:
                instanz = uvarint(p, n + 2)[0]  # nur der erste der beendeten Effekte, wie im Plugin
                for f in self.bei_effekt_weg:
                    f(eid, instanz)
        except (ValueError, struct.error):
            pass  # kaputte oder unbekannte Nachricht

    def _effekt(self, eid: int, p: bytes, n: int) -> None:
        """Ein Effekt landet: Entity, 01, Flags u8, Instanz, Effekt-ID u32, Dauer i64 ms (Aufbau aus
        dem A2Tools-Kern, capture/abnormal.rs). Nur fuer die Boss-Ansagen, nur deren Effekte."""
        if not self.bei_effekt or p[n] != 1:
            return
        instanz, laenge = uvarint(p, n + 2)
        effekt, dauer_ms = struct.unpack_from("<Iq", p, n + 2 + laenge)
        if effekt in self.effekt_ids:
            for f in self.bei_effekt:
                f(eid, instanz, effekt, dauer_ms / 1000)

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

    def _sync(self, eid: int, p: bytes, n: int) -> None:
        """MP oder SP gibt es nur fuer den eigenen Charakter: dann ist die ID sicher. Bis dahin gilt die
        haeufigste Entity-ID in 0x8D00 (im Massen-PvP oft falsch, dort tragen alle Spieler HP)."""
        if self._eigene_punkte(p, n):
            self.eigene_eid, self.eid_sicher = eid, True
            return
        if self.eid_sicher:
            return
        self._sync_zaehler[eid] += 1
        if sum(self._sync_zaehler.values()) >= 100:
            self.eigene_eid = self._sync_zaehler.most_common(1)[0][0]
            self._sync_zaehler.clear()

    @staticmethod
    def _eigene_punkte(p: bytes, n: int) -> bool:
        r = Leser(p)
        r.pos = n
        if not r.u8() & 1:
            return False
        arten = []
        for _ in range(r.varint()):
            arten.append(r.u8())
            r.i32()
        return bool(EIGENE_PUNKTE & set(arten))

    def _position(self, x: float, y: float, z: float) -> None:
        if gueltig(x, y, z):
            with self.lock:
                self.position, self.position_zeit = (x, y, z), time.time()
                self._kurs_merken(x, y)

    def _position_pruefen(self, x: float, y: float, z: float) -> None:
        """Position aus einer ungeprueften Quelle: nur nah an der letzten (oder wenn die alt ist)."""
        alt = self.position
        if alt and time.time() - self.position_zeit < SPRUNG_ALTER_S \
                and math.hypot(x - alt[0], y - alt[1]) > MAX_SPRUNG_CM:
            return
        self._position(x, y, z)

    def _kurs_merken(self, x: float, y: float) -> None:
        """Laufrichtung aus den letzten Metern. Spruenge (Teleport) setzen nur den Startpunkt neu."""
        if self._kurs_von is None:
            self._kurs_von = (x, y)
            return
        dx, dy = x - self._kurs_von[0], y - self._kurs_von[1]
        weg = math.hypot(dx, dy)
        if weg >= MAX_SPRUNG_CM:
            self._kurs_von = (x, y)
        elif weg >= KURS_AB_CM:
            self.kurs, self._kurs_von = (dx / weg, dy / weg), (x, y)

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
                "eid_sicher": self.eid_sicher,
                "position": self.position,
                "position_alter": time.time() - self.position_zeit if self.position else None,
                "kurs": self.kurs,
                "cubes": list(self.cubes.values()),
                "dungeon": self.dungeon,
                "feldbosse": [b for b in self.feldbosse.values()
                              if b["lebt"] and b["pos"] and b["karte"] == self.zone],
                "gruppe": [(self.charnamen.get(cid, ""), *g) for cid, g in self.gruppe.items()
                           if time.time() - g[3] < 10],
                "nachrichten": self.nachrichten,
                "karte_offen": time.time() - self.karte_offen_zeit < KARTE_OFFEN_S,
            }
