"""Tests mit erfundenen Daten – echte Kampfdateien enthalten Mitspielernamen und gehören nicht ins Repo."""
import gzip
import json

import pytest

from nexproto import NexLog, NexLogError, dungeon_label, pack, player_name, unpack
from nexproto.nexlog import HIT_COLUMNS, MAX_PACKED, MAX_UNPACKED
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


def hits(n: int = 1) -> dict:
    """Treffer-Datei wie von deckbar-capture (hits/<id>.json)."""
    return {"version": 1, "fight": f"auto_{n}", "target": 9000 + n, "start_ms": 1_792_000_000_000 + n * 120_000,
            "columns": list(HIT_COLUMNS), "flags": {"crit": 1, "back": 2, "dot": 1024},
            "rows": [[100, 1, 0, 1, 450_000, 0, 1], [900, 1, 0, 1, 450_000, 2, 0], [950, 7, 2, 2, 1, 0, 1024]]}


def log(**overrides) -> NexLog:
    doc = {
        "recorder": {"nexboard": "0.5.0", "capture": "build-1"},
        "run": {"dungeon_id": 600123, "dungeon": "Ferocious Horn Den", "difficulty": "Normal",
                "start_ms": 1_792_000_120_000, "end_ms": 1_792_000_450_000, "complete": True,
                "bosses_total": 2, "bosses_killed": 2},
        "you": {"name": "Testheld", "cls": "ranger"},
        "names": {"Mo***n|cleric": "Moonlin"},
        "fights": [fight(1), fight(2)],
        "hits": {"auto_1": hits(1)},
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


def test_treffer_kommen_mit():
    back = unpack(pack(log()))
    assert back.hits["auto_1"].rows[1] == (900, 1, 0, 1, 450_000, 2, 0)
    assert "auto_2" not in back.hits  # Kampf ohne Treffer-Datei


def test_treffer_zu_unbekanntem_kampf():
    with pytest.raises(ValueError, match="unbekanntem Kampf"):
        log(hits={"auto_9": hits(9)})
    with pytest.raises(ValueError, match="unbekanntem Kampf"):
        log(hits={"auto_1": hits(2)})


def test_treffer_mit_falschen_spalten():
    bad = hits(1)
    bad["columns"] = ["t_ms", "actor", "skill", "owner", "damage", "multi", "flags"]
    with pytest.raises(ValueError, match="Spalten"):
        log(hits={"auto_1": bad})
    bad = hits(1)
    bad["rows"][0] = [100, 1, 0]
    with pytest.raises(ValueError):
        log(hits={"auto_1": bad})


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


def test_namen_aufloesen():
    lg = log()
    me, other = lg.fights[0].actors
    assert player_name(lg, me) == "Testheld"  # eigener Name ist nicht maskiert
    assert player_name(lg, other) == "Moonlin"  # "Mo***n" + jobId 17 (cleric)
    other.jobId = 14
    assert player_name(lg, other) == "Mo***n"  # anderer Klasse: unbekannt, bleibt maskiert


def test_dungeon_label_fuellt_nur_den_platzhalter():
    assert dungeon_label(610062, "Dungeon 610062") == "Shattered Arkanis"
    assert dungeon_label(610062, "Eigener Name") == "Eigener Name"
    assert dungeon_label(1, "Dungeon 1") == "Dungeon 1"
