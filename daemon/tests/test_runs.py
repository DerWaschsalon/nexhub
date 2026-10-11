"""Dungeon-Runs aus der History des A2Tools-Meters → PNG → Discord-Webhook (nachgebaut)."""
import json
import os
import time

import pytest
from aiohttp import ClientSession, web
from pydantic import ValidationError

from deckbar_daemon import runs as runs_mod
from deckbar_daemon.runs import (DungeonRuns, RunSettings, RunTracker, char_key, mask, parse_fight,
                                 post_discord, render_run)

T0 = 1_791_700_000_000
DUNGEON = 600022


def fight(mob, start_s, dur_s=60, max_hp=1000, dmg=(600, 400), dungeon=DUNGEON, names=("Mo***n", "Gamunex"), **extra):
    """History-Eintrag im Format des Meters (gekürzt)."""
    actors = [{"actorId": i + 1, "nickname": n, "jobId": 14 if i == 0 else 18} for i, n in enumerate(names)]
    skills = [{"actorId": i + 1, "dmg": d} for i, d in enumerate(dmg)]
    return {"id": f"auto_{mob}_{start_s}", "bossName": f"Boss {mob}", "startTimeMs": T0 + start_s * 1000,
            "durationMs": dur_s * 1000, "totalDamage": sum(dmg), "dungeonId": dungeon, "mobCode": mob,
            "isTrain": False, "actors": actors,
            "details": {"maxHp": max_hp, "totalTargetDamage": sum(dmg), "skills": skills}, **extra}


def F(*a, **kw):
    f = parse_fight(fight(*a, **kw), you_actor=2)
    assert f
    return f


def test_mask():
    assert mask("Morgan") == "Mo***n"
    assert mask("Gamunex") == "Ga****x"
    assert mask("MOSS") == "MO*S"
    assert mask("tib") == "t*b"
    assert mask("Qi") == "Q*"
    assert mask("Ironwhisper") == "Ir****r" and mask("SKYRover") == "SK****r"
    assert mask("Mo***n") == "Mo***n"
    assert char_key("Morgan", "ranger") == char_key("Mo***n", "ranger") == "Mo***n|ranger"


def test_parse_fight():
    f = F(1, 0)
    assert f.killed and f.dungeon == DUNGEON and [p.dmg for p in f.players] == [600, 400]
    assert f.players[1].you and f.players[0].cls == "ranger"
    assert not F(1, 0, dmg=(100, 100)).killed
    assert parse_fight(fight(1, 0, isTrain=True)) is None
    assert parse_fight(fight(1, 0, dungeon=0)) is None  # offene Welt
    assert parse_fight({"kaputt": True}) is None


def test_first_run_ends_by_idle_then_end_boss_known():
    tr = RunTracker(idle_ms=15 * 60_000)
    # erster Run: Endboss unbekannt → endet erst nach 15 min Ruhe
    assert tr.add(F(1, 0)) == []
    assert tr.add(F(2, 120, max_hp=3000, dmg=(2000, 1000))) == []
    assert tr.check_idle(T0 + 10 * 60_000) == []
    [run] = tr.check_idle(T0 + 200_000 + 15 * 60_000)
    assert not run.complete and run.kills == 2
    # zweiter Run: Boss 2 (meiste HP) ist jetzt als Endboss bekannt
    assert tr.add(F(1, 3600)) == []
    assert tr.add(F(2, 3700, max_hp=3000, dmg=(100, 100))) == []  # Wipe
    [run] = tr.add(F(2, 3900, max_hp=3000, dmg=(2000, 1000)))
    assert run.complete and len(run.fights) == 3
    b = {x.mob: x for x in run.bosses()}
    assert b[2].attempts == 2 and b[2].killed and b[2].total == 3200


def test_dungeon_change_closes_run():
    tr = RunTracker(idle_ms=15 * 60_000)
    tr.add(F(1, 0))
    [run] = tr.add(F(7, 300, dungeon=600055))
    assert run.dungeon == DUNGEON and tr.run.dungeon == 600055


def test_rename_and_merge():
    tr = RunTracker(idle_ms=60_000)
    tr.add(F(1, 0, names=("Mo***n", "Gamunex")))
    tr.add(F(2, 100, names=("Mo***n", "Ga****x")))  # Meter maskiert manchmal auch den eigenen Namen
    [run] = tr.check_idle(T0 + 10**7)
    run.rename({"Mo***n|ranger": "Morgan"})
    total = run.total()
    assert sorted(p.name for p in total.players.values()) == ["Gamunex", "Morgan"]
    assert total.players["Mo***n|ranger"].dmg == 1200
    assert run.fights[0].players[0].name == "Mo***n"  # Kämpfe selbst bleiben unverändert


def test_render_png():
    tr = RunTracker(idle_ms=60_000)
    for i in range(4):
        tr.add(F(i + 1, i * 100))
    [run] = tr.check_idle(T0 + 10**7)
    png = render_run(run)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000


def test_settings_validation():
    RunSettings(webhook="https://discord.com/api/webhooks/123/abc-DEF_9")
    with pytest.raises(ValidationError):
        RunSettings(webhook="https://example.com/api/webhooks/123/abc")
    assert RunSettings(names={"a|b": "  Kevin ", "c|d": " "}).names == {"a|b": "Kevin"}


async def test_post_discord():
    got = {}

    async def hook(request: web.Request) -> web.Response:
        reader = await request.multipart()
        async for part in reader:
            got[part.name] = (part.filename, await part.read())
        return web.json_response({"id": "1"})

    app = web.Application()
    app.router.add_post("/api/webhooks/1/x", hook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with ClientSession() as s:
            await post_discord(s, f"http://127.0.0.1:{port}/api/webhooks/1/x", "Text", b"\x89PNGxyz", "run.png")
    finally:
        await runner.cleanup()
    payload = json.loads(got["payload_json"][1])
    assert payload["content"] == "Text" and payload["allowed_mentions"] == {"parse": []}
    assert got["files[0]"] == ("run.png", b"\x89PNGxyz")


async def test_start_replays_missed_fights(tmp_path, monkeypatch):
    hist = tmp_path / "a2t" / "history"
    hist.mkdir(parents=True)
    monkeypatch.setattr(runs_mod, "a2tools_dir", lambda: tmp_path / "a2t")
    now_s = int(time.time()) - 3 * 3600
    base = (now_s * 1000 - T0) // 1000
    # alter Run (vor dem letzten Stand) → nur gelernt; neuer Run danach → nachgeholt
    for f in (fight(1, base), fight(2, base + 100, max_hp=3000, dmg=(2000, 1000)),
              fight(1, base + 7200), fight(2, base + 7300, max_hp=3000, dmg=(2000, 1000))):
        (hist / f"{f['id']}.json").write_text(json.dumps(f))
    cfg = tmp_path / "cfg"
    runs = DungeonRuns(cfg)
    runs.last_ms = T0 + (base + 1000) * 1000
    [run] = await runs.start()
    assert run.complete and run.start_ms == T0 + (base + 7200) * 1000
    chars = runs.characters()
    assert [(c["key"], c["count"]) for c in chars] == [("Ga****x|chanter", 4), ("Mo***n|ranger", 4)]
    assert chars[0]["seen"] == "Gamunex" and chars[1]["seen"] == ""
    assert runs.names() == {"Ga****x|chanter": "Gamunex"}


def test_observe_learns_full_names(tmp_path, monkeypatch):
    runs = DungeonRuns(tmp_path)
    runs.observe({"rows": [{"name": "Morgan", "cls": "ranger"}, {"name": "Lu**a", "cls": "assassin"}, {"name": "#1234", "cls": None}]})
    assert runs.names() == {"Mo***n|ranger": "Morgan"} and runs.settings.names == {}
    assert DungeonRuns(tmp_path).learned == {"Mo***n|ranger": "Morgan"}  # übersteht Neustart
    # von Hand Eingetragenes hat Vorrang
    runs.save(RunSettings(names={"Mo***n|ranger": "Rena7o"}))
    runs.observe({"rows": [{"name": "Morgan", "cls": "ranger"}]})
    assert runs.names()["Mo***n|ranger"] == "Rena7o"
    assert (tmp_path / "runs.yaml").stat().st_mode & 0o777 == 0o600
    # Weltboss mit vielen Fremden: Obergrenze
    monkeypatch.setattr(runs_mod, "MAX_LEARNED", 3)
    runs.observe({"rows": [{"name": f"Spieler{i}", "cls": "cleric"} for i in range(5)]})
    assert list(runs.learned.values()) == ["Spieler2", "Spieler3", "Spieler4"]


def test_fight_file_updated_during_fight():
    """Das Meter schreibt die Datei schon im Kampf und danach immer wieder neu (Fehler vom 11.10.)."""
    tr = RunTracker(idle_ms=15 * 60_000)
    tr.known = {DUNGEON: {1: 1000, 2: 3000}}  # Boss 2 ist als Endboss bekannt
    assert tr.add(F(1, 0)) == []
    # Endboss: erster Stand nach 34 s, noch nicht besiegt …
    assert tr.add(F(2, 100, dur_s=34, max_hp=3000, dmg=(500, 300))) == []
    assert len(tr.run.fights) == 2
    # … gleiche Datei, neuer Stand: besiegt → Run zu, Kampf ersetzt statt doppelt
    [run] = tr.add(F(2, 100, dur_s=159, max_hp=3000, dmg=(2000, 1000)))
    assert run.complete and len(run.fights) == 2 and run.kills == 2
    assert {b.mob: b.duration_ms for b in run.bosses()}[2] == 159_000


async def test_poll_waits_for_files_to_settle(tmp_path, monkeypatch):
    hist = tmp_path / "a2t" / "history"
    hist.mkdir(parents=True)
    monkeypatch.setattr(runs_mod, "a2tools_dir", lambda: tmp_path / "a2t")
    monkeypatch.setattr(runs_mod, "SETTLE_S", 0)
    posted = []

    runs = DungeonRuns(tmp_path / "cfg")
    runs.save(RunSettings(enabled=True, webhook="https://discord.com/api/webhooks/1/x"))

    async def fake_post(session, run):
        posted.append(run)
        return True

    monkeypatch.setattr(runs, "post", fake_post)
    runs.last_ms = 0
    await runs.start()
    runs.tracker.known = {DUNGEON: {1: 1000, 2: 3000}}
    base = (int(time.time()) * 1000 - T0) // 1000 - 300

    def write(f, age=10):
        path = hist / f"{f['id']}.json"
        path.write_text(json.dumps(f))
        t = time.time() - age
        os.utime(path, (t, t))

    write(fight(1, base))
    write(fight(2, base + 100, dur_s=30, max_hp=3000, dmg=(500, 300)))
    await runs.poll(None)
    assert runs.tracker.run and not runs.pending
    write(fight(2, base + 100, dur_s=150, max_hp=3000, dmg=(2000, 1000)), age=5)
    await runs.poll(None)
    assert runs.tracker.run is None and len(runs.pending) == 1 and not posted
    # Nachzügler-Update derselben Datei landet im wartenden Run, nicht in einem neuen
    write(fight(2, base + 100, dur_s=152, max_hp=3000, dmg=(2010, 1000)), age=3)
    await runs.poll(None)
    assert runs.tracker.run is None and len(runs.pending) == 1
    monkeypatch.setattr(runs_mod, "SETTLE_RUN_S", 0)
    await runs.poll(None)
    [run] = posted
    assert run.complete and run.kills == 2 and len(run.fights) == 2
    assert {b.mob: b.duration_ms for b in run.bosses()}[2] == 152_000
    # danach geänderte Dateien des Runs erzeugen keinen neuen Run
    write(fight(2, base + 100, dur_s=153, max_hp=3000, dmg=(2011, 1000)), age=2)
    await runs.poll(None)
    assert runs.tracker.run is None and len(posted) == 1


def test_boss_again_starts_new_run():
    tr = RunTracker(idle_ms=15 * 60_000)  # Endboss unbekannt (erster Besuch)
    for i, mob in enumerate((1, 2, 3)):
        assert tr.add(F(mob, i * 60, max_hp=3000 if mob == 3 else 1000, dmg=(2000, 1000))) == []
    [run] = tr.add(F(1, 400))  # Boss 1 schon besiegt → neuer Run
    assert [f.mob for f in run.fights] == [1, 2, 3] and [f.mob for f in tr.run.fights] == [1]
    # Wipe + neuer Versuch am selben Boss bleibt im Run
    tr.add(F(2, 500, dmg=(10, 10)))
    assert tr.add(F(2, 600)) == [] and len(tr.run.fights) == 3


def test_learned_keys_follow_mask_rule(tmp_path):
    # Schlüssel aus der alten Regel (Sterne = volle Länge) werden beim Laden neu gebildet
    (tmp_path / "runs-state.json").write_text(json.dumps(
        {"last_ms": 1, "learned": {"Po*******l|gladiator": "Ironwhisper", "Mo***y|templar": "Monkey"}}))
    runs = DungeonRuns(tmp_path)
    assert runs.learned == {"Ir****r|gladiator": "Ironwhisper", "Mo***y|templar": "Monkey"}


def test_listed_end_boss_closes_first_run(monkeypatch):
    """Endboss aus END_BOSSES beendet schon den ersten Run; dort zählen gelernte HP nicht."""
    monkeypatch.setattr(runs_mod, "is_end_boss", lambda mob: mob == 3)
    tr = RunTracker(idle_ms=15 * 60_000)
    assert tr.add(F(1, 0, max_hp=5000, dmg=(4000, 1000))) == []
    assert tr.add(F(2, 60)) == []
    [run] = tr.add(F(3, 120))
    assert run.complete and [f.mob for f in run.fights] == [1, 2, 3]
    # Boss 1 hat zwar die meisten HP, ist aber nicht der gelistete Endboss
    assert tr.add(F(1, 3600, max_hp=5000, dmg=(4000, 1000))) == []
    assert tr.run and len(tr.run.fights) == 1
