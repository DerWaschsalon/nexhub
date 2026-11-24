"""NexHub-Anbindung gegen einen nachgebauten Hub (gleiche Endpunkte wie hub/api, routes/devices.py)."""
import asyncio

import pytest
from aiohttp import web
from pydantic import ValidationError

from deckbar_daemon import hub as hubmod
from deckbar_daemon.feed_buffer import FeedBuffer
from deckbar_daemon.hub import Hub, HubError, loot_drop


async def fake_hub(polls_until_approved: int = 1):
    """Hub, der nach `polls_until_approved` Nachfragen bestätigt; merkt sich, was ankam."""
    seen = {"pair": [], "polls": 0, "auth": [], "deleted": False, "valid": True}

    async def pair(request):
        seen["pair"].append(await request.json())
        return web.json_response({"device_code": "dc", "user_code": "BCDF-GHJK",
                                  "verification_uri": "http://x/hub/geraete",
                                  "verification_uri_complete": "http://x/hub/geraete?code=BCDF-GHJK",
                                  "expires_in": 600, "interval": 0})

    async def poll(request):
        body = await request.json()
        if body["device_code"] != "dc":
            return web.json_response({"detail": "Kopplung abgelaufen"}, status=410)
        seen["polls"] += 1
        if seen["polls"] < polls_until_approved:
            return web.json_response({"status": "pending"})
        return web.json_response({"status": "approved", "token": "geraete-token", "device_id": 1, "device_name": "PC"})

    async def me(request):
        seen["auth"].append((request.headers.get("Authorization"), request.headers.get("X-NexBoard-Version")))
        if not seen["valid"] or request.headers.get("Authorization") != "Bearer geraete-token":
            return web.json_response({"detail": "Gerät unbekannt"}, status=401)
        if request.method == "DELETE":
            seen["deleted"] = True
            return web.Response(status=204)
        return web.json_response({"id": 1, "name": "PC", "owner": "Testheld"})

    app = web.Application()
    app.router.add_post("/api/devices/pair", pair)
    app.router.add_post("/api/devices/pair/poll", poll)
    app.router.add_route("*", "/api/devices/me", me)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}", seen


async def wait_for(cond, timeout=3.0):
    for _ in range(int(timeout / 0.01)):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Bedingung nicht erreicht")


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    monkeypatch.setattr(hubmod, "MIN_POLL_S", 0.0)


async def test_koppeln_von_anfang_bis_ende(tmp_path):
    runner, url, seen = await fake_hub(polls_until_approved=3)
    hub = Hub(tmp_path)
    try:
        hub.update({"url": url + "/", "name": "Gaming-PC"})
        assert hub.settings.url == url  # Schrägstrich am Ende weg
        await hub.start_pairing()
        assert hub.status == "pairing" and hub.pairing["user_code"] == "BCDF-GHJK"
        assert seen["pair"][0]["name"] == "Gaming-PC"
        await wait_for(lambda: hub.status == "paired")
        assert seen["polls"] == 3 and hub.pairing is None
        assert hub.account == {"device": "PC", "owner": "Testheld"}
        assert seen["auth"][-1][1]  # Version geht mit
        # Token steht in hub.yaml (nur für den Besitzer lesbar), nie in info()
        assert (tmp_path / "hub.yaml").stat().st_mode & 0o777 == 0o600
        assert "geraete-token" in (tmp_path / "hub.yaml").read_text()
        assert "geraete-token" not in str(hub.info())
        # Neustart: Token bleibt
        assert Hub(tmp_path).settings.token == "geraete-token"
    finally:
        await hub.close()
        await runner.cleanup()


async def test_abkoppeln_meldet_ab_und_vergisst_das_token(tmp_path):
    runner, url, seen = await fake_hub()
    hub = Hub(tmp_path)
    try:
        hub.update({"url": url})
        await hub.start_pairing()
        await wait_for(lambda: hub.status == "paired")
        await hub.unpair()
        assert seen["deleted"] and hub.status == "unpaired" and hub.settings.token == ""
        assert Hub(tmp_path).settings.token == ""
    finally:
        await hub.close()
        await runner.cleanup()


async def test_im_hub_entfernt(tmp_path):
    runner, url, seen = await fake_hub()
    hub = Hub(tmp_path)
    try:
        hub.update({"url": url})
        await hub.start_pairing()
        await wait_for(lambda: hub.status == "paired")
        seen["valid"] = False
        await hub.check()
        assert hub.status == "unpaired" and "entfernt" in hub.detail and hub.settings.token == ""
    finally:
        await hub.close()
        await runner.cleanup()


async def test_hub_nicht_erreichbar(tmp_path):
    hub = Hub(tmp_path)
    hub.save(hub.settings.model_copy(update={"url": "http://127.0.0.1:9", "token": "t"}))
    try:
        await hub.check()
        assert hub.status == "offline" and hub.settings.token == "t"  # Token bleibt, Hub ist nur weg
        with pytest.raises(HubError, match="nicht erreichbar"):
            await hub.start_pairing()
    finally:
        await hub.close()


async def test_neue_adresse_heisst_neu_koppeln(tmp_path):
    hub = Hub(tmp_path)
    hub.save(hub.settings.model_copy(update={"url": "https://a.example.com", "token": "t"}))
    hub.update({"name": "Anderer Name"})
    assert hub.settings.token == "t"
    hub.update({"url": "https://b.example.com"})
    assert hub.settings.token == "" and hub.status == "unpaired"


@pytest.mark.parametrize("url", ["http://hub.example.com", "ftp://x", "https://hub.example.com/pfad", "kein-url"])
def test_unsichere_oder_falsche_adressen(tmp_path, url):
    with pytest.raises(ValidationError):
        Hub(tmp_path).update({"url": url})


@pytest.mark.parametrize("url", ["https://hub.example.com", "http://localhost:8080", "http://127.0.0.1:8080", ""])
def test_erlaubte_adressen(tmp_path, url):
    assert Hub(tmp_path).update({"url": url}).url == url


async def test_abgelaufener_code(tmp_path):
    runner, url, _ = await fake_hub(polls_until_approved=10**6)
    hub = Hub(tmp_path)
    try:
        hub.update({"url": url})
        await hub.start_pairing()
        # Code abgelaufen: der Hub antwortet auf das nächste Nachfragen mit 410
        hub._poll_task.cancel()
        hub._poll_task = asyncio.create_task(hub._poll("anderer-code", 0, 600))
        await wait_for(lambda: hub.status == "unpaired")
        assert hub.pairing is None and "abgelaufen" in hub.detail
    finally:
        await hub.close()
        await runner.cleanup()


# ---------------------------------------------------------------- Runs hochladen
import json  # noqa: E402

from nexproto import unpack  # noqa: E402

from deckbar_daemon.run_model import Run, parse_fight  # noqa: E402

from test_runs import DUNGEON, fight  # noqa: E402


async def fake_runs_hub(*statuses):
    """Nimmt Runs an (POST /api/runs) und antwortet der Reihe nach mit `statuses` (danach 201)."""
    got, answers = [], list(statuses)

    async def runs(request):
        got.append(await request.read())
        status = answers.pop(0) if answers else 201
        if status == 201:
            return web.json_response({"id": len(got), "url": f"http://hub/hub/runs/{len(got)}", "duplicate": False},
                                     status=201)
        return web.json_response({"detail": "kaputt"}, status=status)

    async def report(request):
        got.append(("report", int(request.match_info["run_id"]), await request.json()))
        return web.json_response({"forwarded": True}, status=202)

    app = web.Application()
    app.router.add_post("/api/runs", runs)
    app.router.add_post("/api/runs/{run_id}/report", report)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}", got


def history_run(root):
    """Zwei Bosskämpfe als Kampfdateien auf der Platte (wie deckbar-capture), Treffer nur zum ersten."""
    hist = root / "aion2" / "history"
    hist.mkdir(parents=True)
    (root / "aion2" / "hits").mkdir()
    raw = [fight(2400011, 0, dur_s=60), fight(2400012, 120, dur_s=90, dmg=(400, 600))]
    for f in raw:
        (hist / f"{f['id']}.json").write_text(json.dumps(f))
    (root / "aion2" / "hits" / f"{raw[0]['id']}.json").write_text(json.dumps({
        "version": 1, "fight": raw[0]["id"], "target": 5, "start_ms": raw[0]["startTimeMs"],
        "columns": ["t_ms", "actor", "owner", "skill", "damage", "multi", "flags"], "flags": {"crit": 1},
        "rows": [[100, 1, 0, 1, 600, 0, 1], [200, 2, 0, 2, 400, 0, 0]]}))
    run = Run(DUNGEON)
    run.fights = [parse_fight(f) for f in raw]
    run.complete = True
    run.rename({"Mo***n|ranger": "Morgan"})
    return run, hist


def uploading_hub(tmp_path, url):
    hub = Hub(tmp_path / "cfg", outbox=tmp_path / "outbox")
    (tmp_path / "cfg").mkdir(exist_ok=True)
    hub.save(hub.settings.model_copy(update={"url": url, "token": "geraete-token", "upload": True}))
    hub.enabled = True
    return hub


async def test_run_wird_als_nexlog_hochgeladen(tmp_path):
    runner, url, got = await fake_runs_hub()
    hub = uploading_hub(tmp_path, url)
    run, hist = history_run(tmp_path)
    hub.history_dir = lambda: hist
    tod = {"t_ms": run.start_ms + 1000, "name": "Morgan", "skill": 1801120, "warning": "Todesmal", "lead_ms": 4100}
    hub.deaths = lambda start_ms, end_ms: [tod] if start_ms <= tod["t_ms"] <= end_ms else []
    # Würfel-Beute aus dem Feed des Mitschnitts: nur „steht zum Würfeln“ zählt, auch kurz nach dem letzten Boss
    loot = FeedBuffer("lootRoll", loot_drop)
    hub.loot = loot.between
    opened = {"type": "open", "rollId": "ab", "itemId": 110430050, "count": 1, "endsAt": 0}
    won = {"type": "won", "rollId": "ab", "itemId": 110430050, "player": {"serverId": 2302, "name": "Morgan"}}
    earlier = {"type": "open", "rollId": "cd", "itemId": 7, "count": 1, "endsAt": 0}
    for at, roll in ((run.end_ms + 5_000, opened), (run.end_ms + 9_000, won), (run.start_ms - 60_000, earlier)):
        await loot.on_capture("plugin_feed", {"event": "lootRoll", "data": roll, "at": at})
    await loot.on_capture("plugin_feed", {"event": "deathRecap", "data": opened, "at": run.end_ms})  # andere Art
    try:
        await hub.on_fight({"rows": [{"name": "Gamunex", "cls": "chanter", "you": True}, {"name": "Morgan"}]})
        await hub.publish(run)
        assert hub.info()["outbox"] == 1
        await hub.flush_outbox()
        assert hub.info()["outbox"] == 0 and hub.last_upload["ok"] and hub.last_upload["url"].endswith("/runs/1")

        log = unpack(got[0])
        assert log.run.dungeon_id == DUNGEON and log.run.bosses_total == 2 and log.run.complete
        assert log.you.name == "Gamunex" and log.names == {"Mo***n|ranger": "Morgan"}
        assert [f.id for f in log.fights] == [f.id for f in run.fights]
        assert list(log.hits) == [run.fights[0].id] and len(log.hits[run.fights[0].id].rows) == 2
        assert [d.model_dump() for d in log.deaths] == [tod]  # Todesursachen vom Radar
        # nur der Gegenstand dieses Runs, ohne den Namen der Gewinnerin
        assert [d.model_dump() for d in log.loot] == [{"t_ms": run.end_ms + 5_000, "item_id": 110430050, "count": 1}]
    finally:
        await hub.close()
        await runner.cleanup()


async def test_ohne_einstellung_oder_kopplung_wird_nichts_verpackt(tmp_path):
    hub = uploading_hub(tmp_path, "http://127.0.0.1:9")
    run, hist = history_run(tmp_path)
    hub.history_dir = lambda: hist
    hub.update({"upload": False})
    await hub.publish(run)
    hub.update({"upload": True})
    hub.enabled = False  # Modul aus
    await hub.publish(run)
    assert not (tmp_path / "outbox").exists()


async def test_fehlschlag_bleibt_im_postausgang(tmp_path):
    runner, url, got = await fake_runs_hub(503)
    hub = uploading_hub(tmp_path, url)
    run, hist = history_run(tmp_path)
    hub.history_dir = lambda: hist
    try:
        await hub.publish(run)
        await hub.flush_outbox()
        assert hub.info()["outbox"] == 1 and not hub.last_upload["ok"] and hub._failures == 1
        await hub.flush_outbox()  # zweiter Versuch klappt
        assert hub.info()["outbox"] == 0 and len(got) == 2 and hub._failures == 0
    finally:
        await hub.close()
        await runner.cleanup()


async def test_hub_nicht_erreichbar_behaelt_den_run(tmp_path):
    hub = uploading_hub(tmp_path, "http://127.0.0.1:9")
    run, hist = history_run(tmp_path)
    hub.history_dir = lambda: hist
    try:
        await hub.publish(run)
        await hub.flush_outbox()
        assert hub.info()["outbox"] == 1 and "nicht erreichbar" in hub.last_upload["text"]
    finally:
        await hub.close()


async def test_abgelehnter_run_wird_beiseitegelegt(tmp_path):
    runner, url, got = await fake_runs_hub(422)
    hub = uploading_hub(tmp_path, url)
    run, hist = history_run(tmp_path)
    hub.history_dir = lambda: hist
    try:
        await hub.publish(run)
        await hub.flush_outbox()
        assert hub.info()["outbox"] == 0 and len(list((tmp_path / "outbox" / "abgelehnt").iterdir())) == 1
        assert "lehnt" in hub.last_upload["text"]
        await hub.flush_outbox()
        assert len(got) == 1  # nicht noch einmal geschickt
    finally:
        await hub.close()
        await runner.cleanup()


def test_postausgang_hat_eine_obergrenze(tmp_path, monkeypatch):
    monkeypatch.setattr(hubmod, "OUTBOX_MAX_BYTES", 250)
    hub = Hub(tmp_path, outbox=tmp_path / "outbox")
    for start in (1, 2, 3):
        hub._enqueue(f"{start}-600022.nexlog.gz", b"x" * 100)
    assert [p.name for p in hub._queued()] == ["2-600022.nexlog.gz", "3-600022.nexlog.gz"]


async def test_fehlende_kampfdatei(tmp_path):
    hub = uploading_hub(tmp_path, "http://127.0.0.1:9")
    run, hist = history_run(tmp_path)
    (hist / f"{run.fights[1].id}.json").unlink()
    hub.history_dir = lambda: hist
    await hub.publish(run)
    assert hub.info()["outbox"] == 0 and "nicht verpackt" in hub.last_upload["text"]


async def test_run_bericht_geht_nach_dem_upload_an_den_hub(tmp_path, monkeypatch):
    from deckbar_daemon import run_image as runs_mod

    monkeypatch.setattr(runs_mod, "render_run", lambda r: b"RIFF\0\0\0\0WEBPbild")
    runner, url, got = await fake_runs_hub()
    hub = uploading_hub(tmp_path, url)
    hub.save(hub.settings.model_copy(update={"discord": True}))
    run, hist = history_run(tmp_path)
    hub.history_dir = lambda: hist
    try:
        await hub.publish(run)
        assert sorted(p.name.split(".", 1)[1] for p in (tmp_path / "outbox").iterdir()) == ["nexlog.gz", "report.json"]
        await hub.flush_outbox()
        kind, run_id, report = got[1]
        assert (kind, run_id) == ("report", 1) and report["dungeon_id"] == DUNGEON and report["image_webp"]
        assert list((tmp_path / "outbox").iterdir()) == []  # beides weg
    finally:
        await runner.cleanup()
        await hub.close()


def test_discord_schalter_aus_der_web_ui(tmp_path):
    """Der Schalter „In Discord posten“ (web/js/modules/hub.js) speichert `discord` und zeigt ihn wieder an."""
    hub = Hub(tmp_path)
    assert hub.info()["settings"]["discord"] is False
    hub.update({"upload": True, "discord": True, "token": "darf-nicht-durch"})
    assert hub.info()["settings"]["discord"] is True
    again = Hub(tmp_path)
    assert again.settings.discord is True and again.settings.token == ""
    hub.update({"discord": False})
    assert Hub(tmp_path).settings.discord is False


async def test_api_stand_und_kennung_gehen_mit(tmp_path):
    from nexproto.hubapi import API_HEADER, HUB_API, REQUEST_ID_HEADER

    headers = []

    async def runs(request):
        headers.append(("run", request.headers.get(API_HEADER), request.headers.get(REQUEST_ID_HEADER)))
        return web.json_response({"id": 1, "url": "http://hub/hub/runs/1", "duplicate": False}, status=201)

    async def report(request):
        headers.append(("report", request.headers.get(API_HEADER), request.headers.get(REQUEST_ID_HEADER)))
        return web.json_response({"forwarded": True}, status=202)

    app = web.Application()
    app.router.add_post("/api/runs", runs)
    app.router.add_post("/api/runs/{run_id}/report", report)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    hub = uploading_hub(tmp_path, f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}")
    hub._enqueue("1-600022.nexlog.gz", b"x")
    hub._enqueue_report("1-600022", "{}")
    try:
        await hub.flush_outbox()
        (_, api, rid), (kind, _, report_rid) = headers
        assert api == str(HUB_API) and len(rid) == 12
        assert kind == "report" and report_rid == rid  # Upload und Bericht tragen dieselbe Kennung
    finally:
        await hub.close()
        await runner.cleanup()


async def test_veraltetes_nexboard_behaelt_die_runs(tmp_path):
    runner, url, _ = await fake_runs_hub(426)
    hub = uploading_hub(tmp_path, url)
    hub._enqueue("1-600022.nexlog.gz", b"x")
    try:
        await hub.flush_outbox()
        assert hub.info()["outbox"] == 1 and hub._failures == 0  # kein Wiederholen im Minutentakt
        assert hub.last_upload["text"] == "kaputt"  # Text des Hubs, dort steht „bitte aktualisieren“
    finally:
        await hub.close()
        await runner.cleanup()


async def test_hub_meldet_veraltetes_nexboard(tmp_path):
    async def me(request):
        return web.json_response({"detail": "NexBoard ist zu alt für diesen Hub, bitte aktualisieren"}, status=426)

    app = web.Application()
    app.router.add_get("/api/devices/me", me)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    hub = uploading_hub(tmp_path, f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}")
    try:
        await hub.check()
        assert hub.status == "offline" and "aktualisieren" in hub.detail
        assert hub.settings.token == "geraete-token"  # Kopplung bleibt, nach dem Update geht es weiter
    finally:
        await hub.close()
        await runner.cleanup()
