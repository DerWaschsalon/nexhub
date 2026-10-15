"""Discord-Bot-Anbindung: Gruppen-DPS und Run-API gegen einen nachgebauten Bot (TheWashBot-Format)."""
import asyncio

import pytest
from aiohttp import web
from pydantic import ValidationError

from deckbar_daemon.bot import BotSettings, DiscordBot, group_payload, run_payload
from deckbar_daemon.dps import DpsFeed, fight_view
from deckbar_daemon.runs import parse_fight, Run
from deckbar_daemon.state import State

from test_runs import DUNGEON, fight


def view(**kw):
    rows = [
        {"name": "Aria", "cls": "spiritmaster", "dps": 30000, "dmg": 3_000_000, "pct": 40.0, "you": True, "party": True},
        {"name": "Borr", "cls": "templar", "dps": 20000, "dmg": 2_000_000, "pct": 26.7, "you": False, "party": True},
        {"name": "Fremd", "cls": "ranger", "dps": 25000, "dmg": 2_500_000, "pct": 33.3, "you": False, "party": False},
    ]
    base = {"target": "Nuakum", "targetId": 77, "boss": True, "timeMs": 95_400, "hp": 0.0, "rows": rows}
    base.update(kw)
    return fight_view(base)


def test_fight_view_keeps_party_flag_or_none():
    v = view()
    assert v["target_id"] == 77 and v["boss"] and v["time"] == 95
    assert [r["party"] for r in v["rows"]] == [True, True, False]
    old = fight_view({"rows": [{"name": "X", "dps": 1, "dmg": 1}]})  # A2Tools-Stream, altes deckbar-capture
    assert old["rows"][0]["party"] is None


def test_group_payload_only_party_and_filters():
    s = BotSettings()
    p, why = group_payload(view(), s)
    assert why == "" and p["target"] == "Nuakum" and p["duration_s"] == 95
    assert [r["name"] for r in p["party"]] == ["Aria", "Borr"]  # nach DPS, Fremde raus
    assert p["party"][0] == {"name": "Aria", "cls": "spiritmaster", "dps": 30000, "dmg": 3_000_000, "pct": 60.0}
    assert group_payload(view(hp=12.0), s)[1] == "nicht besiegt"
    assert group_payload(view(boss=False), s)[1] == "kein Boss"
    assert group_payload(view(timeMs=5000), s)[1].startswith("zu kurz")
    assert group_payload(view(rows=[{"name": "Solo", "dps": 1, "dmg": 1, "you": True, "party": False}]), s)[1].startswith("Gruppe zu klein")
    assert "deckbar-capture" in group_payload(fight_view({"rows": [{"name": "X", "dps": 1, "dmg": 1}]}), s)[1]
    relaxed = s.model_copy(update={"dps_kills_only": False, "dps_boss_only": False, "dps_min_seconds": 0})
    assert group_payload(view(hp=50.0, boss=False), relaxed)[0] is not None


def test_you_counts_as_party_member():
    rows = [{"name": "Me", "dps": 5, "dmg": 50, "you": True, "party": False},
            {"name": "Mate", "dps": 4, "dmg": 40, "you": False, "party": True}]
    p, _ = group_payload(fight_view({"target": "B", "boss": True, "hp": 0, "timeMs": 60_000, "rows": rows}), BotSettings())
    assert {r["name"] for r in p["party"]} == {"Me", "Mate"}


def test_settings_validation_and_masking(tmp_path):
    with pytest.raises(ValidationError):
        BotSettings(dps_url="ftp://x")
    with pytest.raises(ValidationError):
        BotSettings(runs_token="mit leer")
    bot = DiscordBot(tmp_path)
    bot.update({"dps_url": "http://10.0.0.5:8787/dps/geheim", "runs_url": "https://bot.example/api/aion/fight", "runs_token": "t0k"})
    info = bot.info()
    assert info["settings"]["dps_url"] == "••••••••" and info["settings"]["runs_token"] == "••••••••"
    assert info["targets"] == {"dps": "http://10.0.0.5:8787/…", "runs": "https://bot.example/…"}
    # Platzhalter lassen Geheimnisse stehen
    bot.update({"dps_url": "••••••••", "dps_min_party": 3})
    assert bot.settings.dps_url.endswith("/dps/geheim") and bot.settings.dps_min_party == 3
    assert (tmp_path / "bot.yaml").stat().st_mode & 0o077 == 0
    assert DiscordBot(tmp_path).settings.runs_token == "t0k"


def run_from_history():
    run = Run(DUNGEON)
    run.fights = [parse_fight(fight(2400011, 0, dur_s=60), you_actor=2),
                  parse_fight(fight(2400012, 120, dur_s=90, dmg=(400, 600)), you_actor=2)]
    run.complete = True
    run.rename({"Mo***n|ranger": "Morgan"})
    return run


def test_run_payload_matches_bot_contract():
    p = run_payload(run_from_history())
    assert p["dungeon_id"] == DUNGEON and isinstance(p["dungeon"], str) and p["dungeon"]
    assert p["bosses_total"] == 2 and p["bosses_killed"] == 2 and p["fight_ms"] == 150_000
    names = [x["name"] for x in p["players"]]
    assert names == ["Gamunex", "Morgan"] or names == ["Morgan", "Gamunex"]
    assert all({"name", "damage", "dps"} <= set(x) for x in p["players"])
    g = next(x for x in p["players"] if x["name"] == "Gamunex")
    assert g["damage"] == 1000 and g["dps"] == round(1000 / 150)
    assert [len(b["players"]) for b in p["bosses"]] == [2, 2] and p["bosses"][1]["duration_ms"] == 90_000
    # Prüfung wie im Bot (validate_fight_payload)
    for key in ("bosses_total", "bosses_killed", "start_ms", "fight_ms"):
        assert isinstance(p[key], int)


async def fake_bot():
    got = []

    async def dps(request: web.Request) -> web.Response:
        got.append(("dps", request.match_info["token"], await request.json()))
        return web.json_response({"ok": True})

    async def runs(request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != "Bearer t0k":
            return web.json_response({"error": "unauthorized"}, status=401)
        got.append(("runs", None, await request.json()))
        return web.json_response({"ok": True, "merged": False})

    app = web.Application()
    app.router.add_post("/dps/{token}", dps)
    app.router.add_post("/api/aion/fight", runs)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, site._server.sockets[0].getsockname()[1], got


async def test_sends_to_bot_only_when_enabled(tmp_path):
    runner, port, got = await fake_bot()
    try:
        bot = DiscordBot(tmp_path)
        bot.update({"dps_enabled": True, "dps_url": f"http://127.0.0.1:{port}/dps/abc",
                    "runs_enabled": True, "runs_url": f"http://127.0.0.1:{port}/api/aion/fight", "runs_token": "t0k"})
        await bot.on_fight(view())
        assert got == []  # Modul aus
        bot.enabled = True
        await bot.on_fight(view())
        await bot.on_fight(view())  # derselbe Kampf zweimal (Leerlauf + Spielende) → einmal
        await bot.on_fight(view(hp=40.0))  # nicht besiegt → nichts
        assert [(k, t) for k, t, _ in got] == [("dps", "abc")]
        assert got[0][2]["party"][0]["name"] == "Aria" and bot.result["dps"]["ok"]
        await bot.on_run(run_from_history())
        assert got[-1][0] == "runs" and got[-1][2]["bosses_killed"] == 2 and bot.result["runs"]["ok"]
        bot.update({"runs_token": "falsch"})
        assert not await bot.send_run(run_from_history())
        assert "401" in bot.result["runs"]["text"]
        ok, text = await bot.test_fight()
        assert ok and len(got) == 3
    finally:
        await bot.close()
        await runner.cleanup()


async def test_feed_reports_fight_end_with_last_stand(tmp_path):
    feed = DpsFeed(State(), tmp_path)
    ends = []

    async def listen(f):
        ends.append(f)

    feed.fight_listeners.append(listen)
    snap = {"target": "Boss", "targetId": 5, "boss": True, "timeMs": 30_000, "hp": 50.0,
            "rows": [{"name": "A", "dps": 10, "dmg": 100, "you": True, "party": True}]}
    from deckbar_daemon.dps import compact
    await feed._apply(compact(snap), fight=fight_view(snap))
    snap2 = {**snap, "timeMs": 60_000, "hp": 0.0, "rows": [{**snap["rows"][0], "dmg": 300}]}
    await feed._apply(compact(snap2), fight=fight_view(snap2))
    assert feed.state.values["dps_active"] and not ends
    await feed._apply(None)  # Mitschnitt endet → Kampf vorbei
    await asyncio.sleep(0)  # Zuhörer laufen entkoppelt
    assert len(ends) == 1 and ends[0]["hp"] == 0.0 and ends[0]["rows"][0]["dmg"] == 300


async def test_stopping_feed_stops_capture(tmp_path):
    """Modul DPS-Mitschnitt aus → watch() wird abgebrochen → auch capture.run muss enden."""
    feed = DpsFeed(State(), tmp_path)
    ended = asyncio.Event()

    async def run(*_a):
        try:
            await asyncio.Event().wait()
        finally:
            ended.set()

    feed.capture.run = run
    task = asyncio.ensure_future(feed.watch())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert ended.is_set()
