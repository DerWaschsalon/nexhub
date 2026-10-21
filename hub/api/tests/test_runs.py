"""Runs hochladen und ansehen. NexLogs aus erfundenen Daten (nexproto-Modell), nie aus echten Kampfdateien."""
from nexproto import NexLog, pack
from nexproto.nexlog import HIT_COLUMNS

from .conftest import ADMIN, BASE, MEMBER
from .test_devices import ORIGIN, bearer, pair


def fight(n: int, boss_dmg: int = 1_000_000) -> dict:
    return {
        "id": f"auto_{n}", "bossName": f"Boss {n}", "mobCode": 2400000 + n, "dungeonId": 600123,
        "startTimeMs": 1_792_000_000_000 + n * 300_000, "durationMs": 100_000, "totalDamage": boss_dmg,
        "actors": [{"actorId": 1, "nickname": "Testheld", "jobId": 14},
                   {"actorId": 2, "nickname": "Mo***n", "jobId": 17}],
        "details": {"maxHp": 1_000_000, "totalTargetDamage": boss_dmg,
                    "skills": [{"actorId": 1, "code": 1, "dmg": boss_dmg * 3 // 4},
                               {"actorId": 2, "code": 2, "dmg": boss_dmg // 4}]},
    }


def nexlog(**run) -> bytes:
    return pack(NexLog.model_validate({
        "recorder": {"nexboard": "0.6.0"},
        "run": {"dungeon_id": 600123, "dungeon": "Ferocious Horn Den", "difficulty": "Normal",
                "start_ms": 1_792_000_300_000, "end_ms": 1_792_000_700_000, "complete": True,
                "bosses_total": 2, "bosses_killed": 1, **run},
        "you": {"name": "Testheld", "cls": "ranger"},
        "names": {"Mo***n|cleric": "Moonlin"},
        "fights": [fight(1), fight(2, boss_dmg=500_000)],
        "hits": {"auto_1": {"fight": "auto_1", "target": 1, "start_ms": 0, "columns": list(HIT_COLUMNS),
                            "flags": {"crit": 1}, "rows": [[0, 1, 0, 1, 10, 0, 1], [5, 2, 0, 2, 5, 0, 0]]}},
    }))


def upload(client, token, data):
    return client.post("/api/runs", content=data, headers={**bearer(token), "content-type": "application/gzip"})


def test_hochladen_und_ansehen(client, as_user):
    member = as_user(MEMBER)
    token = pair(client, member)
    data = nexlog()
    r = upload(client, token, data)
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    assert r.json() == {"id": run_id, "url": f"{BASE}/hub/runs/{run_id}", "duplicate": False}

    runs = as_user(ADMIN).get("/api/runs").json()  # alle Angemeldeten sehen alle Runs
    assert [(x["dungeon"], x["bosses_killed"], x["fights"], x["hits"], x["character"]) for x in runs] == \
        [("Ferocious Horn Den", 1, 2, 2, "Testheld")]
    assert runs[0]["uploader"] == "Testname"

    detail = member.get(f"/api/runs/{run_id}").json()
    s = detail["summary"]
    assert [(b["name"], b["killed"]) for b in s["bosses"]] == [("Boss 1", True), ("Boss 2", False)]
    # Maskierter Name ist über `names` aufgelöst, Schaden je Spieler über beide Bosse summiert
    assert [(p["name"], p["cls"], p["damage"]) for p in s["players"]] == \
        [("Testheld", "ranger", 1_125_000), ("Moonlin", "cleric", 375_000)]
    assert s["players"][0]["dps"] == 1_125_000 * 1000 // 200_000
    assert detail["can_delete"] is True and detail["size"] == len(data)

    # Die Datei kommt unverändert zurück
    assert member.get(f"/api/runs/{run_id}/nexlog").content == data


def test_dieselbe_datei_nur_einmal(client, as_user):
    token = pair(client, as_user(MEMBER))
    first = upload(client, token, nexlog()).json()
    again = upload(client, token, nexlog())
    assert again.status_code == 200 and again.json() == {**first, "duplicate": True}


def test_hochladen_nur_mit_geraete_token(client, as_user):
    assert upload(client, "falsch", nexlog()).status_code == 401
    member = as_user(MEMBER)
    # Auch eine Browser-Sitzung reicht nicht: hochladen dürfen nur Geräte
    assert member.post("/api/runs", content=nexlog(), headers=ORIGIN).status_code == 401


def test_kaputte_und_zu_grosse_dateien(client, as_user, monkeypatch):
    token = pair(client, as_user(MEMBER))
    r = upload(client, token, b"kein gzip")
    assert r.status_code == 422 and "gzip" in r.json()["detail"]
    import nexhub_api.routes.runs as runs
    monkeypatch.setattr(runs, "MAX_PACKED", 100)
    assert upload(client, token, nexlog()).status_code == 413
    assert as_user(ADMIN).get("/api/runs").json() == []


def test_runs_nur_fuer_angemeldete(client):
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs/1").status_code == 401


def test_loeschen(client, as_user, tmp_path):
    member, admin = as_user(MEMBER), as_user(ADMIN)
    token = pair(client, member)
    run_id = upload(client, token, nexlog()).json()["id"]
    other = upload(client, pair(client, admin), nexlog(dungeon="Anderer Dungeon")).json()["id"]
    file = tmp_path / "data" / "runs" / f"{run_id}.nexlog.gz"
    assert file.exists()

    assert member.delete(f"/api/runs/{other}", headers=ORIGIN).status_code == 403
    assert member.get(f"/api/runs/{other}").json()["can_delete"] is False
    assert member.delete(f"/api/runs/{run_id}", headers=ORIGIN).status_code == 204
    assert not file.exists() and member.get(f"/api/runs/{run_id}").status_code == 404
    assert admin.delete(f"/api/runs/{other}", headers=ORIGIN).status_code == 204  # Admins dürfen alles
