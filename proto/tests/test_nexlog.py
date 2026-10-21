"""Tests mit erfundenen Daten – echte Kampfdateien enthalten Mitspielernamen und gehören nicht ins Repo."""
import gzip
import json

import pytest

from nexproto import NexLog, NexLogError, pack, unpack
from nexproto.nexlog import MAX_PACKED, MAX_UNPACKED
from nexproto.schema import SCHEMA_DIR, SCHEMAS, render


def fight(n: int = 1, dungeon: int = 600123) -> dict:
    """Kampfdatei im A2Tools-Format, auf das Nötigste gekürzt, plus ein Feld, das das Modell nicht kennt."""
    return {
        "id": f"auto_{n}", "bossName": f"Boss {n}", "mobCode": 2400000 + n, "dungeonId": dungeon,
        "startTimeMs": 1_792_000_000_000 + n * 120_000, "durationMs": 90_000,
        "actors": [{"actorId": 1, "nickname": "Testheld", "jobId": 14, "gearScore": 2400},
                   {"actorId": 2, "nickname": "Mo***n", "jobId": 17}],
        "details": {"maxHp": 1_000_000, "skills": [{"actorId": 1, "code": 1, "dmg": 900_000,
                                                    "hitTimestamps": [100, 900]}]},
        "buffs": [{"on": 1, "id": 20100, "segs": "0,90000,1,0"}],
        "appVersion": "9.9.9",
    }


def log(**overrides) -> NexLog:
    doc = {
        "recorder": {"nexboard": "0.5.0", "capture": "build-1"},
        "run": {"dungeon_id": 600123, "dungeon": "Ferocious Horn Den", "difficulty": "Normal",
                "start_ms": 1_792_000_120_000, "end_ms": 1_792_000_450_000, "complete": True,
                "bosses_total": 2, "bosses_killed": 2},
        "you": {"name": "Testheld", "cls": "ranger"},
        "names": {"Mo***n|cleric": "Moonlin"},
        "fights": [fight(1), fight(2)],
    }
    return NexLog.model_validate({**doc, **overrides})


def gz(doc: dict) -> bytes:
    return gzip.compress(json.dumps(doc).encode())


def test_hin_und_zurueck_ohne_verlust():
    original = log()
    back = unpack(pack(original))
    assert back == original
    # Felder, die das Modell nicht kennt, kommen unverändert mit
    assert back.fights[0].model_dump()["buffs"][0]["segs"] == "0,90000,1,0"
    assert back.fights[0].actors[0].model_dump()["gearScore"] == 2400


def test_packen_ist_reproduzierbar():
    assert pack(log()) == pack(log())


def test_kampf_aus_anderem_dungeon():
    with pytest.raises(ValueError, match="Dungeon des Runs"):
        log(fights=[fight(1), fight(2, dungeon=600999)])


def test_mindestens_ein_kampf():
    with pytest.raises(ValueError):
        log(fights=[])


@pytest.mark.parametrize("data, grund", [
    (b"kein gzip", "kein gültiges gzip"),
    (gzip.compress(b"{kaputt"), "kein gültiges JSON"),
    (gz({"format": "anderes"}), "kein NexLog"),
    (gz({"format": "nexlog", "version": 2}), "Version 2"),
    (gz({"format": "nexlog", "version": 1, "recorder": {"nexboard": "1"}}), "ungültiges NexLog"),
])
def test_kaputte_dateien(data, grund):
    with pytest.raises(NexLogError, match=grund):
        unpack(data)


def test_abgeschnittene_datei():
    with pytest.raises(NexLogError, match="unvollständig"):
        unpack(pack(log())[:-10])


def test_zu_gross_gepackt():
    with pytest.raises(NexLogError, match="zu groß"):
        unpack(b"\0" * (MAX_PACKED + 1))


def test_entpackbombe():
    # 40 MB Nullen packen auf wenige KB – darf nicht vollständig entpackt werden
    bomb = gzip.compress(b"\0" * (MAX_UNPACKED + 8 * 1024 * 1024))
    assert len(bomb) < MAX_PACKED
    with pytest.raises(NexLogError, match="entpackt zu groß"):
        unpack(bomb)


def test_schema_dateien_passen_zum_code():
    for name, model in SCHEMAS.items():
        assert (SCHEMA_DIR / name).read_text(encoding="utf-8") == render(model), \
            f"schema/{name} veraltet – uv run python -m nexproto.schema"
