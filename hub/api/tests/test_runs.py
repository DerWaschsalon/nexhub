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
                    "skills": [{"actorId": 1, "code": 1, "name": "Pfeilhagel", "dmg": boss_dmg // 2, "time": 10,
                                "crit": 4, "back": 5, "perfect": 0, "double": 1},
                               {"actorId": 1, "code": 3, "name": "Gift", "isDot": True, "dmg": boss_dmg // 4, "time": 20},
                               {"actorId": 2, "code": 2, "name": "Schlag", "dmg": boss_dmg // 4, "time": 8}],
                    "deaths": [{"actorId": 2, "tsMs": 40_000, "revivedMs": 52_000}]},
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


def test_teilen_und_zurueckziehen(client, as_user):
    member, admin = as_user(MEMBER), as_user(ADMIN)
    run_id = upload(client, pair(client, member), nexlog()).json()["id"]
    assert member.get(f"/api/runs/{run_id}").json()["share_url"] is None

    url = member.post(f"/api/runs/{run_id}/share", headers=ORIGIN).json()["share_url"]
    assert url.startswith(f"{BASE}/r/") and member.get(f"/api/runs/{run_id}").json()["share_url"] == url
    # Nochmal teilen gibt denselben Link
    assert member.post(f"/api/runs/{run_id}/share", headers=ORIGIN).json()["share_url"] == url

    token = url.rsplit("/", 1)[1]
    public = client.get(f"/api/public/runs/{token}")  # ohne Login
    assert public.status_code == 200 and "noindex" in public.headers["x-robots-tag"]
    body = public.json()
    assert body["dungeon"] == "Ferocious Horn Den" and body["summary"]["players"][1]["name"] == "Moonlin"
    assert "uploader" not in body and "id" not in body and "size" not in body

    assert member.delete(f"/api/runs/{run_id}/share", headers=ORIGIN).json() == {"share_url": None}
    assert client.get(f"/api/public/runs/{token}").status_code == 404
    # Neu teilen gibt einen neuen Link, der alte bleibt tot
    new = admin.post(f"/api/runs/{run_id}/share", headers=ORIGIN).json()["share_url"]
    assert new != url and client.get(f"/api/public/runs/{token}").status_code == 404


def test_teilen_nur_hochladende_oder_admins(client, as_user):
    member, admin = as_user(MEMBER), as_user(ADMIN)
    run_id = upload(client, pair(client, admin), nexlog()).json()["id"]
    assert member.post(f"/api/runs/{run_id}/share", headers=ORIGIN).status_code == 403
    assert member.delete(f"/api/runs/{run_id}/share", headers=ORIGIN).status_code == 403
    assert client.post(f"/api/runs/{run_id}/share").status_code == 401


def test_unbekannter_link(client):
    assert client.get("/api/public/runs/gibtsnicht").status_code == 404
    assert client.get("/api/public/runs/" + "x" * 200).status_code == 404


def test_kampf_details(client, as_user):
    member = as_user(MEMBER)
    run_id = upload(client, pair(client, member), nexlog()).json()["id"]
    d = member.get(f"/api/runs/{run_id}/fights/auto_1").json()
    assert d["name"] == "Boss 1" and d["killed"] and d["duration_ms"] == 100_000
    assert d["run_players"] == ["Testheld", "Moonlin"]  # Farbreihenfolge für alle Kämpfe des Runs
    held, moon = d["players"]
    assert (held["name"], held["cls"], held["damage"], held["dps"]) == ("Testheld", "ranger", 750_000, 7_500)
    assert [(x["name"], x["dot"], x["share"], x["hits"], x["crit"], x["back"], x["double"]) for x in held["skills"]] == \
        [("Pfeilhagel", False, 66.7, 10, 40.0, 50.0, 10.0), ("Gift", True, 33.3, 20, 0.0, 0.0, 0.0)]
    assert d["deaths"] == [{"name": "Moonlin", "t_ms": 40_000, "revived_ms": 52_000}]
    # DPS-Kurve aus den Einzeltreffern: je Sekunde, Länge = Kampfdauer
    series = {p["actor"]: p["damage"] for p in d["timeline"]["players"]}
    assert len(series[1]) == 101 and series[1][0] == 10 and series[2][0] == 5
    # Ohne Einzeltreffer keine Kurve, der Rest geht trotzdem
    assert member.get(f"/api/runs/{run_id}/fights/auto_2").json()["timeline"] is None
    assert member.get(f"/api/runs/{run_id}/fights/gibtsnicht").status_code == 404
    assert client.get(f"/api/runs/{run_id}/fights/auto_1").status_code == 401


def test_kampf_details_faehigkeiten_und_buffs(client, as_user):
    """Was die Kampfdatei über die Summen hinaus hat: Min/Max, Parade, Mehrfachtreffer,
    Spezialisierungen, Zeitpunkte und Buff-Abschnitte."""
    f = fight(1)
    f["targetId"] = 900
    f["details"]["skills"][0].update({"minDmg": 1200, "maxDmg": 90_000, "parry": 2, "multiHitCount": 3,
                                      "multiHitDamage": 7000, "specs": [True, False, False, True, False],
                                      "hitTimestamps": [5200, 200, "x", 700]})
    f["buffs"] = [{"on": 1, "id": 20100, "by": 2, "segs": "-4000,30000,1,0;30000,100000,2,10;kaputt", "up": 100_000},
                  {"on": 900, "id": 790, "by": 1, "segs": "1000,9000,1,1", "up": 8000},
                  {"on": 4711, "id": 1, "by": 0, "segs": "0,1,1,1", "up": 1},     # fremde Figur: weg
                  {"on": [1], "id": 2, "segs": "0,1,1,1"}]                          # kaputt: weg
    log = nexlog()
    from nexproto import unpack
    data = unpack(log).model_dump(mode="json")
    data["fights"][0] = f
    member = as_user(MEMBER)
    run_id = upload(client, pair(client, member), pack(NexLog.model_validate(data))).json()["id"]
    d = member.get(f"/api/runs/{run_id}/fights/auto_1").json()
    s = d["players"][0]["skills"][0]
    assert (s["min"], s["max"], s["avg"], s["parry"], s["multi_hits"], s["multi_damage"]) == \
        (1200, 90_000, 50_000, 20.0, 3, 7000)
    assert s["specs"] == [1, 4] and s["casts"] == [200, 700, 5200]
    assert d["players"][0]["skills"][1]["specs"] == [] and d["players"][0]["skills"][1]["casts"] == []
    assert d["target"] == 900
    assert d["buffs"] == [
        {"actor": 1, "by": 2, "id": 20100, "up": 100_000, "segments": [[-4000, 30000, 1, 0], [30000, 100000, 2, 10]]},
        {"actor": 900, "by": 1, "id": 790, "up": 8000, "segments": [[1000, 9000, 1, 1]]}]


def test_kampf_details_geteilt(client, as_user):
    member = as_user(MEMBER)
    run_id = upload(client, pair(client, member), nexlog()).json()["id"]
    token = member.post(f"/api/runs/{run_id}/share", headers=ORIGIN).json()["share_url"].rsplit("/", 1)[1]
    r = client.get(f"/api/public/runs/{token}/fights/auto_1")
    assert r.status_code == 200 and r.json()["players"][0]["name"] == "Testheld" and "noindex" in r.headers["x-robots-tag"]
    member.delete(f"/api/runs/{run_id}/share", headers=ORIGIN)
    assert client.get(f"/api/public/runs/{token}/fights/auto_1").status_code == 404
