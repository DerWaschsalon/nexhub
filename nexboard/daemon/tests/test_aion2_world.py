"""Pakete bis in Welt und Tracker: eigene ID, Position und Laufrichtung, Cubes, Gruppe, Feldbosse, Stagger
und was der Kampf meldet. Die Nutzdaten sind gebaut wie im Mitschnitt."""
import math
import struct
import time

import pytest
from aion2_bench import Bench, frame, varint, xyz

from deckbar_daemon.aion2 import minimap
from deckbar_daemon.aion2.cubes import CUBE_IDS, CUBE_KEY
from deckbar_daemon.aion2.field_bosses import rift
from deckbar_daemon.aion2.rules import STAGGER_RULES
from deckbar_daemon.aion2.world import HEADING_FROM_CM, World
from deckbar_daemon.core.packets import PcapSource

RAUR, BERK = 2300206, 2300171
OWN = 300
FLOW = (b"\x01\x02\x03\x04", 13328, b"\x0a\x00\x00\x02", 50000)


@pytest.fixture
def bench() -> Bench:
    return Bench(own_id=OWN)


def spawn(entity: int, object_id: int, x: float, y: float, z: float, since_ms: int | None = None) -> bytes:
    tail = bytes(8) + b"\x01\x01\x01" + struct.pack("<Q", since_ms) + bytes(20) if since_ms is not None else b""
    return varint(entity) + b"\x04\x00" + struct.pack("<I", object_id) + xyz(x, y, z) + tail


# ---------------------------------------------------------------- eigene ID
def test_eigene_id_ueber_mp():
    """Im Massen-PvP tragen fast alle Vitals fremde HP; nur der eigene Charakter bekommt MP/SP."""
    bench = Bench(own_id=None)
    hp = varint(5) + b"\x02\x01\x00" + struct.pack("<q", 1000)  # Flag 2: HP einer fremden Entity
    mp = varint(42) + b"\x01\x01\x01" + struct.pack("<i", 300)  # Flag 1: MP
    for _ in range(150):
        bench.packet(0x8D00, hp)
    assert (bench.world.own_id, bench.world.own_id_sure) == (5, False)  # geschätzt
    bench.packet(0x8D00, mp)
    for _ in range(150):
        bench.packet(0x8D00, hp)
    assert (bench.world.own_id, bench.world.own_id_sure) == (42, True)


def test_name_macht_die_id_sicher_und_cube_erscheint():
    source, world = PcapSource(), World("Navonex")
    bench = Bench(own_id=None)
    bench.world, bench.source = world, source
    bench.cubes.world = world
    for part in (world, bench.cubes):
        part.attach(source)
    seen = []
    bench.cubes.appeared.connect(seen.append)
    character = frame(0x3633, varint(8956) + b"\x5f\x91\xe9\x28\x37\x07Navonex" + bytes(40))
    moved = frame(0x382A, varint(8956) + b"\x00\x11" + bytes(20) + xyz(1000.0, 2000.0, 50.0))
    data = (character + moved
            + frame(0x3634, spawn(77, 1000295, 3000.0, 2000.0, 450.0))  # Cube, 20 m nördlich, 4 m höher
            + frame(0x3634, spawn(78, 1100133, 0.0, 0.0, 0.0)))  # kein Cube
    source.feed(FLOW, 1, 0, data)
    assert (world.own_id, world.own_id_sure, world.position) == (8956, True, (1000.0, 2000.0, 50.0))
    assert [c.entity for c in bench.cubes.current()] == [77] and len(seen) == 1
    source.feed(FLOW, 1 + len(data), 0, frame(0x3635, varint(77)))
    assert bench.cubes.current() == []


def test_fremde_bewegung_zaehlt_nicht(bench):
    bench.packet(0x382A, varint(2) + b"\x00\x11" + bytes(20) + xyz(5.0, 5.0, 5.0))
    assert bench.world.position is None


# ---------------------------------------------------------------- Position und Laufrichtung
def test_eigener_cast_gibt_position(bench):
    bench.packet(0x3802, varint(OWN) + bytes(15) + xyz(1000.0, 2000.0, 50.0))  # x/y/z ab Byte 17
    assert bench.world.position == (1000.0, 2000.0, 50.0)
    bench.packet(0x3802, varint(OWN + 1) + bytes(15) + xyz(1.0, 1.0))  # fremder Cast: nicht
    assert bench.world.position == (1000.0, 2000.0, 50.0)


def test_sprung_aus_ungepruefter_quelle_wird_verworfen(bench):
    bench.packet(0x371A, varint(OWN) + b"\0\0" + xyz(0.0, 0.0))
    bench.packet(0x3712, varint(OWN) + b"\0\0" + xyz(500.0, 0.0))  # 5 m: ok
    assert bench.world.position[0] == 500.0
    bench.packet(0x3712, varint(OWN) + b"\0\0" + xyz(90000.0, 0.0))  # 900 m: Unsinn
    assert bench.world.position[0] == 500.0
    bench.world.position_time = time.time() - 11  # letzte Position alt: dann gilt auch ein Sprung
    bench.packet(0x3712, varint(OWN) + b"\0\0" + xyz(90000.0, 0.0))
    assert bench.world.position[0] == 90000.0


def test_eintritt_zonenwechsel_und_status_position():
    bench = Bench(own_id=None)
    bench.packet(0x3621, varint(OWN) + bytes(14) + xyz(10.0, 20.0, 30.0))  # x/y/z ab Byte 16
    assert (bench.world.own_id, bench.world.own_id_sure, bench.world.position) == (OWN, False, (10.0, 20.0, 30.0))
    bench.packet(0x561E, bytes(17) + xyz(15.0, 25.0, 35.0))
    assert bench.world.position == (15.0, 25.0, 35.0)
    bench.packet(0x382B, varint(OWN) + bytes(20) + xyz(100.0, 200.0, 300.0))
    assert bench.world.position == (100.0, 200.0, 300.0)


def test_laufrichtung(bench):
    def move(x: float, y: float) -> None:
        bench.packet(0x371A, varint(OWN) + b"\0\0" + xyz(x, y))
    move(0, 0)
    move(50, 0)  # unter 1 m: noch keine Richtung
    assert bench.world.heading is None
    move(200, 0)  # nach Osten
    assert bench.world.heading == (1.0, 0.0)
    move(200, -300)  # nach Norden (Welt -y)
    assert math.isclose(bench.world.heading[1], -1.0)
    move(200, -300 + 5000)  # Teleport: die Richtung bleibt, nur der Startpunkt springt
    assert math.isclose(bench.world.heading[1], -1.0)


def test_blick_aus_der_minikarte_geht_vor_der_laufrichtung():
    world = World()
    world.heading, world.look_until = minimap.heading(0), time.time() + 5
    world._note_heading(0, 0)
    world._note_heading(HEADING_FROM_CM + 100, 0)  # läuft nach Osten, schaut nach Norden
    assert world.heading == minimap.heading(0)
    world.look_until = time.time() - 1  # abgelaufen: wieder die Laufrichtung, von dort, wo der Blick zuletzt galt
    world._note_heading(HEADING_FROM_CM + 100, HEADING_FROM_CM + 100)
    assert world.heading == (0.0, 1.0)


# ---------------------------------------------------------------- Cubes
def test_cube_alter_oeffner_und_schluessel(bench):
    since = int((time.time() - 125) * 1000)
    bench.packet(0x3634, spawn(4711, 1301199, 1.0, 2.0, 3.0, since))
    assert bench.cubes.cubes[4711].since == pytest.approx(since / 1000)
    bench.world.players[9001] = "Defiance"
    bench.packet(0x3638, varint(4711) + varint(9001))
    assert bench.cubes.cubes[4711].opener == "Defiance"
    bench.packet(0x363A, varint(400) + b"\x01" + struct.pack("<I", CUBE_KEY))
    bench.packet(0x363A, varint(401) + b"\x01" + struct.pack("<I", 12345))
    assert bench.cubes.keys_used == 1
    bench.packet(0x3623, varint(1) + bytes(5) + xyz(7.0, 8.0, 9.0))  # Teleport: Entity-IDs gelten nicht mehr
    assert bench.cubes.current() == [] and bench.world.own_id is None and bench.world.position == (7.0, 8.0, 9.0)
    assert {1000549, 1000565, 1300081, 1300082} <= CUBE_IDS and 1000567 + 100 not in CUBE_IDS


# ---------------------------------------------------------------- Feldbosse und Dungeon
def test_feldboss_liste_und_karte_offen(bench):
    assert not bench.field_bosses.map_open
    bench.packet(0x9101, b"\0\0" + struct.pack("<IB", 1110, 2)
                 + b"\x01" + varint(111001) + struct.pack("<fffQ", 100.0, 200.0, 300.0, 1792745536509)
                 + b"\x00" + varint(111007) + struct.pack("<Q", 1792755404209))
    slots = bench.field_bosses.slots
    assert slots["111001"]["pos"] == (100.0, 200.0, 300.0) and slots["111001"]["lebt"]
    assert not slots["111007"]["lebt"] and slots["111007"]["zeit"] == pytest.approx(1792755404.209)
    assert bench.field_bosses.map_open
    bench.field_bosses.list_seen -= 3  # keine Liste mehr: Karte zu
    assert not bench.field_bosses.map_open


def test_riss_zeitplan():
    from datetime import datetime, timezone

    def at(hour: int, minute: int) -> float:  # UTC
        return datetime(2026, 10, 24, hour, minute, tzinfo=timezone.utc).timestamp()
    assert rift(at(2, 59)) == (at(3, 0), False)
    assert rift(at(3, 5)) == (at(3, 0), True)  # 10 min offen
    assert rift(at(3, 11)) == (at(6, 0), False)
    assert rift(at(22, 30))[0] == at(21, 0) + 3 * 3600  # 00:00 UTC am nächsten Tag


def test_dungeon_zeit_und_berserker(bench):
    bench.packet(0x6100, struct.pack("<IBQQ", 600022, 2, 1792742000000, 1792745600000))
    assert bench.world.dungeon_ends_at == 1792745600.0
    bench.world.bosses[72] = BERK
    bench.packet(0x8D21, varint(72) + b"\x01\x01" + struct.pack("<Q", 1792745600000))
    assert bench.aids.berserk == {72: 1792745600.0}
    bench.packet(0x8D21, varint(72) + b"\x00\x00")  # Kampf vorbei
    assert bench.aids.berserk == {}


# ---------------------------------------------------------------- Stagger
def bar(entity: int, ready: bool) -> bytes:
    return varint(entity) + b"\x03\x01" + struct.pack("<II", 557, 300) + bytes([0x02 if ready else 0])


def test_groggy_endet_mit_neuer_leiste(bench):
    bench.world.bosses[1000] = 2300311
    broken = []
    bench.stagger.broken.connect(broken.append)
    bench.packet(0xE005, varint(1000) + b"\x00\x03\x02")
    assert broken == [1000] and bench.stagger.groggy()
    assert not bench.stagger.groggy(time.time() + 9)  # ohne neue Leiste nach 8 s vorbei
    bench.packet(0xE005, bar(1000, False))  # Leiste läuft wieder
    assert not bench.stagger.groggy()
    bench.packet(0xE005, varint(55) + b"\x00\x03\x02")  # kein Boss: zählt nicht
    assert not bench.stagger.groggy()


def test_stagger_pruefung(bench):
    ready = []
    bench.stagger.ready.connect(ready.append)
    bench.world.bosses.update({72: BERK, 70: RAUR})
    bench.world.boss_since.update({72: time.time() - 60, 70: time.time() - 60})
    bench.packet(0xE005, bar(70, True))  # Raur: keine Prüfung
    bench.packet(0xE005, bar(72, True))  # spät erschienen und brechbar
    bench.packet(0xE005, bar(72, True))  # weiter brechbar: nicht nochmal
    bench.packet(0xE005, bar(72, False))  # Pause
    bench.packet(0xE005, bar(72, True))  # wieder brechbar
    assert ready == [72, 72] and BERK in STAGGER_RULES


def test_leiste_von_anfang_an_ist_keine_pruefung(bench):
    ready = []
    bench.stagger.ready.connect(ready.append)
    bench.world.bosses[72] = BERK
    bench.world.boss_since[72] = time.time()
    bench.packet(0xE005, bar(72, True))
    assert ready == []


# ---------------------------------------------------------------- was der Kampf meldet
def test_status_und_effekt_mit_dauer_und_ende(bench):
    seen = []
    bench.fight.status.connect(lambda *a: seen.append(("status", *a)))
    bench.fight.effect.connect(lambda *a: seen.append(("an", *a)))
    bench.fight.effect_gone.connect(lambda *a: seen.append(("weg", *a)))
    bench.fight.status_ids, bench.fight.effect_ids = {16008401}, {16046701}
    # echte Nachricht aus dem Mitschnitt (Ziel 2489, Status 16008401, 3000 ms)
    bench.packet(0x382A, bytes.fromhex("b9 13 01 13 6f d1 44 f4 00 b8 0b 00 00") + bytes(24))
    # Entity, 01, Flags, Instanz, Effekt-ID, Dauer i64 ms, Ende i64 ms (A2Tools capture/abnormal.rs)
    bench.packet(0x382A, varint(70) + b"\x01\x00" + varint(300) + struct.pack("<Iqq", 16046701, 8500, 0))
    bench.packet(0x382C, varint(70) + b"\x01\x01" + varint(300) + b"\x01")
    assert seen == [("status", 2489, 16008401), ("an", 70, 300, 16046701, 8.5), ("weg", 70, 300)]


def test_leiste_mit_und_ohne_ziel_und_welle(bench):
    seen = []
    bench.fight.cast_bar.connect(lambda *a: seen.append(("leiste", *a)))
    bench.fight.wave.connect(lambda *a: seen.append(("welle", *a)))
    bench.packet(0x3809, varint(3199) + b"\x02" + struct.pack("<I", 1604670) + b"\x01\x02")
    # wie im Ludra-Mitschnitt: Caster, Flag, Skill, 01 02, Ziel (Varint), Position …
    bench.packet(0x3809, varint(23107) + b"\x02" + struct.pack("<I", 1802730) + b"\x01\x02" + varint(7271) + bytes(16))
    bench.packet(0x3803, varint(3199) + b"\x00" + varint(5000) + struct.pack("<I", 1604390))
    assert seen == [("leiste", 3199, 1604670, None), ("leiste", 23107, 1802730, 7271), ("welle", 3199, 1604390)]


def test_treffer_auf_mir(bench):
    hits = []
    bench.fight.hit.connect(hits.append)
    bench.fight.hit_ids = {18010340}
    bench.world.own_id = 37109
    # echte Nachricht aus glass-cannon (damage.rs): Ziel 37109, Angreifer 3199, Skill 18010340
    p = bytes.fromhex("f5 a1 02 04 00 ff 18 e4 d0 12 01 62 03 0d 20 59 6b 02 00 00 00 96 56 f2 14 02 00")
    bench.packet(0x3804, p)
    bench.world.own_id = 1  # trifft einen anderen: nichts
    bench.packet(0x3804, p)
    assert hits == [18010340]


def test_gruppen_lp_ohne_mich(bench):
    hp = []
    bench.party.hp.connect(lambda entity, share: hp.append((entity, share)))
    bench.packet(0x921B, varint(9) + varint(250) + varint(1000) + bytes(25))
    bench.packet(0x921B, varint(OWN) + varint(1) + varint(1000) + bytes(25))  # ich: nicht
    assert hp == [(9, 0.25)]


def test_markierung_nur_von_monstern(bench):
    def marker(caster: int) -> bytes:
        # Aufbau wie in glass-cannon (cast.rs): Caster, Skill, Cast-ID, u32, u16, x/y/z, Richtung, ms
        return varint(caster) + struct.pack("<IBIH", 1226350, 2, 1, 0) + struct.pack("<ffff", 1.0, 2.0, 0.0, 0.0) \
            + struct.pack("<H", 2850)
    areas = []
    bench.fight.area.connect(lambda *a: areas.append(a))
    bench.world.players[9] = "Anna"
    for caster in (70, OWN, 9):  # Monster, ich, anderer Spieler
        bench.packet(0x3848, marker(caster))
    assert areas == [(1226350, 1.0, 2.0, 2.85)]
