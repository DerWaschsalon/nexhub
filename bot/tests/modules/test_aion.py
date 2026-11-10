"""AION 2: Run-Annahme, Zusammenführen, Bestenlisten, Bilder, Hub-Link und Termintafel."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import discord
import pytest

from bot.db import Database

Run = dict[str, Any]  # ein gemeldeter Lauf, wie ihn das NexBoard schickt


def test_aion_api_auth_rejects_bad_requests() -> None:

    from aiohttp.test_utils import make_mocked_request

    from bot.db import Database
    from bot.modules.aion2.runs.posts import RunPosts

    async def go() -> Any:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            await db.set(1, "aion_api_token", "secret123")
            await db.set(1, "aion_channel", 999)
            cog = RunPosts.__new__(RunPosts)
            cog.client = type("B", (), {"get_cog": lambda self, name: None})()
            cog.db = db
            cog.api_pending = {}

            # Kein Authorization-Header -> 401, kein Crash durch das String-Slicing
            req = make_mocked_request("POST", "/api/aion/fight")
            resp = await cog.handle_api_fight(req)
            assert resp.status == 401

            # Falscher Token -> 401
            req = make_mocked_request("POST", "/api/aion/fight", headers={"Authorization": "Bearer falsch"})
            resp = await cog.handle_api_fight(req)
            assert resp.status == 401

            await db.close()

    asyncio.run(go())


def test_aion_api_merge_and_embed() -> None:
    from bot.modules.aion2.runs.format import fmt_dps, fmt_num
    from bot.modules.aion2.runs.posts import build_run_embed, merge_players, same_api_run, validate_fight_payload

    assert fmt_num(13_290_000) == "13.29M"
    assert fmt_num(8_080) == "8.1k"
    assert fmt_dps(38_000) == "38.0k/s"

    base: Run = {"dungeon": "Ferocious Horn Den", "bosses_total": 3, "bosses_killed": 3,
                 "start_ms": 1_760_445_123_000, "fight_ms": 350_000,
                 "players": [{"name": "ReZero", "damage": 13_000_000, "dps": 37_000}]}
    assert validate_fight_payload(base) is None
    assert validate_fight_payload({"dungeon": "X"}) is not None
    assert validate_fight_payload({**base, "players": []}) is not None

    # Zweite Meldung desselben Laufs, leicht abweichende Startzeit/Dauer -> trotzdem derselbe Lauf
    report2: Run = {**base, "start_ms": base["start_ms"] + 2_000, "fight_ms": base["fight_ms"] - 1_500,
                   "players": [{"name": "Gamunex", "damage": 8_000_000, "dps": 23_000}]}
    assert same_api_run(base, report2)

    # 20 Minuten später, sonst identisch -> nicht derselbe Lauf
    later: Run = {**base, "start_ms": base["start_ms"] + 20 * 60_000}
    assert not same_api_run(base, later)

    # Merge: gleicher Spielername in zwei Meldungen -> höherer Schaden gewinnt, sortiert absteigend
    reportA: Run = {**base, "players": [{"name": "ReZero", "damage": 13_000_000, "dps": 37_000},
                                        {"name": "Gamunex", "damage": 8_000_000, "dps": 23_000}]}
    reportB: Run = {**base, "players": [{"name": "ReZero", "damage": 13_290_000, "dps": 38_000},  # höher -> gewinnt
                                        {"name": "Haze", "damage": 5_080_000, "dps": 14_500}]}
    players = merge_players([reportA, reportB])
    assert [p["name"] for p in players] == ["ReZero", "Gamunex", "Haze"]
    assert players[0]["damage"] == 13_290_000  # der höhere der beiden gemeldeten Werte

    embed = build_run_embed(base, reporters=2)
    assert "Ferocious Horn Den" in str(embed.title)
    assert "2 NexBoard-Meldung" in str(embed.footer.text)

    assert build_run_embed(base, reporters=2).image.url is None  # Bilder nur als Anhang


def test_aion_leaderboard_rows() -> None:
    from bot.modules.aion2.runs.posts import leaderboard_rows

    bosses = [
        {"name": "Boss 1", "players": [{"name": "ReZero", "damage": 100, "dps": 10}]},
        {"name": "Boss 2", "players": [{"name": "ReZero", "damage": 200, "dps": 20},
                                        {"name": "Gamunex", "damage": 50, "dps": 5}]},
    ]
    players = [{"name": "ReZero", "cls": "ranger"}, {"name": "Gamunex"}]
    rows = leaderboard_rows(bosses, players)
    assert {"boss": "Boss 1", "player": "ReZero", "class": "ranger", "damage": 100, "dps": 10} in rows
    assert {"boss": "Boss 2", "player": "Gamunex", "class": None, "dps": 5, "damage": 50} in rows

    assert leaderboard_rows(bosses, [])[0]["class"] is None  # ohne Klasse: kein Absturz


def test_aion_update_leaderboard_keeps_only_best() -> None:
    import tempfile
    from pathlib import Path

    from bot.db import Database
    from bot.modules.aion2.runs.posts import RunPosts

    async def go() -> Any:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            cog = RunPosts.__new__(RunPosts)
            cog.db = db

            bosses = [{"name": "Boss 1", "players": [{"name": "ReZero", "damage": 100, "dps": 10}]}]
            await cog._update_leaderboard(1, bosses, [])
            row = await db.fetchone("SELECT * FROM aion_leaderboard WHERE guild_id=1 AND boss='Boss 1'")
            assert row is not None and row["dps"] == 10

            # Schlechterer Lauf -> wird NICHT übernommen
            worse = [{"name": "Boss 1", "players": [{"name": "ReZero", "damage": 50, "dps": 5}]}]
            await cog._update_leaderboard(1, worse, [])
            row = await db.fetchone("SELECT * FROM aion_leaderboard WHERE guild_id=1 AND boss='Boss 1'")
            assert row is not None and row["dps"] == 10  # unverändert

            # Besserer Lauf -> wird übernommen
            better = [{"name": "Boss 1", "players": [{"name": "ReZero", "damage": 500, "dps": 50}]}]
            await cog._update_leaderboard(1, better, [])
            row = await db.fetchone("SELECT * FROM aion_leaderboard WHERE guild_id=1 AND boss='Boss 1'")
            assert row is not None and row["dps"] == 50

            await db.close()

    asyncio.run(go())


def test_aion_records_best_time_and_dps_record() -> None:
    from bot.modules.aion2.runs.commands import ranking_embed
    from bot.modules.aion2.runs.format import records_text
    from bot.modules.aion2.runs.posts import RECORDS_FIELD, build_run_embed
    from bot.modules.aion2.runs.records import DungeonKey, RunRecords, RunResult

    def make_run(fight_ms: int, killed: int = 3, difficulty: str | None = "Normal") -> dict[str, Any]:
        return {"dungeon": "Feuertempel", "difficulty": difficulty, "bosses_total": 3,
                "bosses_killed": killed, "start_ms": 0, "fight_ms": fight_ms}

    def make_players(a_dps: float, b_dps: float) -> list[dict[str, Any]]:
        return [{"name": "Anna", "cls": "ranger", "damage": a_dps * 300, "dps": a_dps},
                {"name": "Ben", "cls": None, "damage": b_dps * 300, "dps": b_dps}]

    async def go() -> Any:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            records = RunRecords(db)

            async def saved(run: dict[str, Any], players: list[dict[str, Any]]) -> RunResult:
                result = await records.save(1, run, players)
                assert result is not None  # vollständiger Lauf wird immer gewertet
                return result

            # Unvollständig: nicht gewertet
            assert await records.save(1, make_run(200_000, killed=2), make_players(50, 40)) is None

            first = await saved(make_run(360_000), make_players(30, 20))
            assert first.best_before_ms is None and "Erste Bestzeit" in records_text(first)
            assert first.personal_bests == ()  # erster Run ist keine Bestleistung

            slower = await saved(make_run(400_000), make_players(25, 22))
            assert (slower.place, slower.runs) == (2, 2) and slower.dps_record is None
            assert slower.personal_bests == ("Ben",)
            assert "Platz 2 von 2" in records_text(slower)

            faster = await saved(make_run(330_000), make_players(45, 21))
            assert "Neue Bestzeit!" in records_text(faster) and "6:00" in records_text(faster)
            assert faster.dps_record is not None
            assert faster.dps_record.player == "Anna" and faster.dps_record.previous_dps == 30
            assert faster.personal_bests == ()  # Anna steht schon in der Rekordzeile, Ben unter 22

            # Andere Schwierigkeit zählt getrennt
            hard = await saved(make_run(500_000, difficulty="Hard"), make_players(10, 10))
            assert hard.best_before_ms is None

            normal = DungeonKey(1, "Feuertempel", "Normal")
            times = await records.fastest(normal)
            players = await records.best_players(normal)
            assert [t.fight_ms for t in times] == [330_000, 360_000, 400_000]
            assert [(p.player, p.dps) for p in players] == [("Anna", 45), ("Ben", 22)]
            assert await records.dungeons(1, "feuer") == [DungeonKey(1, "Feuertempel", "Hard"), normal]
            assert await records.dungeons(2, "") == []  # anderer Server

            embed = build_run_embed(make_run(330_000), reporters=1, records=faster)
            assert any(f.name == RECORDS_FIELD for f in embed.fields)
            board = ranking_embed("Feuertempel (Normal)", times, players)
            assert "5:30" in str(board.fields[0].value) and "Anna (ranger)" in str(board.fields[1].value)
            await db.close()

    asyncio.run(go())


def test_aion_leaderboard_page() -> None:
    import tempfile
    from pathlib import Path

    from bot.db import Database
    from bot.modules.aion2.runs.posts import RunPosts

    class FakeGuild:
        id = 1
        name = "Der Waschsalon"

    async def go() -> Any:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()

            cog = RunPosts.__new__(RunPosts)
            cog.db = db
            cog.client = type("B", (), {"get_guild": lambda self, gid: FakeGuild() if gid == 1 else None})()
            bosses = [{"name": "Kromede's Desire", "players": [{"name": "Xqzmepls", "damage": 500, "dps": 50}]}]
            await cog._update_leaderboard(1, bosses, [{"name": "Xqzmepls", "cls": "ranger"}])

            def req(gid: str) -> Any:
                """Nur was page_leaderboard aus der Anfrage liest."""
                return SimpleNamespace(match_info={"guild_id": gid})

            resp = await cog.page_leaderboard(req("1"))
            assert resp.status == 200
            page = str(resp.text)
            assert "Kromede&#x27;s Desire" in page and "Xqzmepls" in page and "ranger" in page
            assert (await cog.page_leaderboard(req("999"))).status == 404  # unbekannte Guild
            assert (await cog.page_leaderboard(req("not-a-number"))).status == 404

            await db.close()

    asyncio.run(go())


def test_aion_api_boss_dps() -> None:
    from bot.modules.aion2.runs.posts import build_run_embed, merge_bosses, validate_fight_payload

    base: Run = {"dungeon": "Ferocious Horn Den", "bosses_total": 2, "bosses_killed": 2,
                 "start_ms": 1_760_445_123_000, "fight_ms": 350_000,
                 "players": [{"name": "ReZero", "damage": 13_000_000, "dps": 37_000}],
                 "bosses": [
                     {"name": "Boss 1", "players": [{"name": "ReZero", "damage": 4_000_000, "dps": 40_000}]},
                     {"name": "Boss 2", "players": [{"name": "ReZero", "damage": 9_000_000, "dps": 35_000}]},
                 ]}
    assert validate_fight_payload(base) is None
    assert validate_fight_payload({**base, "bosses": [{"name": "X"}]}) is not None
    assert validate_fight_payload({**base, "bosses": "nope"}) is not None

    reportB: Run = {**base, "bosses": [
        {"name": "Boss 1", "players": [{"name": "Gamunex", "damage": 3_000_000, "dps": 30_000}]},
        {"name": "Boss 2", "players": [{"name": "ReZero", "damage": 9_500_000, "dps": 36_000}]},  # höher -> gewinnt
    ]}
    bosses = merge_bosses([base, reportB])
    assert [b["name"] for b in bosses] == ["Boss 1", "Boss 2"]
    assert {p["name"] for p in bosses[0]["players"]} == {"ReZero", "Gamunex"}
    assert bosses[1]["players"][0]["damage"] == 9_500_000

    embed = build_run_embed(base, reporters=2, bosses=bosses)
    field_names = [f.name for f in embed.fields]
    assert "🗡️ Boss 1" not in field_names  # Boss-DPS ist jetzt ein Bild, kein Text-Feld mehr

    from PIL import Image

    from bot.modules.aion2.runs.image import WIDTH, render_boss_image

    boss_buf = render_boss_image(bosses[0]["name"], bosses[0]["players"])
    boss_image = Image.open(boss_buf)
    assert boss_image.format == "PNG"
    assert boss_image.size[0] == WIDTH


def test_aion_run_image_renders_valid_png() -> None:
    from PIL import Image

    from bot.modules.aion2.runs.image import WIDTH, render_run_image

    players = [
        {"name": "ReZero", "damage": 13_290_000, "dps": 38_000},
        {"name": "Gamunex", "damage": 8_000_000, "dps": 23_000},
        {"name": "Haze", "damage": 5_080_000, "dps": 14_500},
    ]
    buf = render_run_image("Ferocious Horn Den", "Normal", players, bosses_killed=3, bosses_total=3, fight_ms=350_000)
    image = Image.open(buf)
    assert image.format == "PNG"
    assert image.size[0] == WIDTH

    # keine Spieler (Edge-Case) darf nicht crashen oder durch Null teilen
    empty_buf = render_run_image("Fire Temple", None, [], bosses_killed=0, bosses_total=1, fight_ms=0)
    assert Image.open(empty_buf).size[0] == WIDTH

    # mehr als MAX_ROWS Spieler -> Bild bleibt begrenzt hoch (keine endlose Liste pro Spieler)
    from bot.modules.aion2.runs.image import MAX_ROWS

    many_players = [{"name": f"P{i}", "damage": 1000 - i, "dps": 10} for i in range(30)]
    many_buf = render_run_image("Fire Temple", None, many_players, bosses_killed=1, bosses_total=1, fight_ms=60_000)
    ten_players_buf = render_run_image(
        "Fire Temple", None, many_players[:MAX_ROWS], bosses_killed=1, bosses_total=1, fight_ms=60_000,
    )
    assert Image.open(many_buf).size[1] == Image.open(ten_players_buf).size[1]


def test_aion_api_run_image() -> None:
    """Run-Bild vom NexBoard: nur echtes WebP, von mehreren Meldungen das mit den meisten Spielern."""
    import base64

    from bot.modules.aion2.runs.posts import MAX_IMAGE_BYTES, decode_image, pick_image, validate_fight_payload

    webp = b"RIFF\x10\0\0\0WEBPVP8L" + b"x" * 20
    enc = base64.b64encode(webp).decode()
    assert decode_image(enc) == webp
    assert decode_image(None) is None and decode_image("") is None and decode_image(123) is None
    assert decode_image("kein base64!") is None
    assert decode_image(base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 20).decode()) is None
    assert decode_image(base64.b64encode(b"RIFF\0\0\0\0WEBP" + b"x" * MAX_IMAGE_BYTES).decode()) is None

    base: Run = {"dungeon": "Fire Temple", "bosses_total": 1, "bosses_killed": 1, "start_ms": 1, "fight_ms": 1,
                 "players": [{"name": "A", "damage": 5}]}
    assert validate_fight_payload({**base, "image_webp": enc}) is None
    assert validate_fight_payload({**base, "image_webp": 5}) is not None

    one: Run = {"players": [{"name": "A", "damage": 9}], "image": b"eins"}
    two: Run = {"players": [{"name": "A", "damage": 5}, {"name": "B", "damage": 1}], "image": b"zwei"}
    bare: Run = {"players": [{"name": "A", "damage": 1}, {"name": "B", "damage": 1}, {"name": "C", "damage": 1}],
                 "image": None}
    assert pick_image([one, two, bare]) == b"zwei"
    assert pick_image([bare]) is None


def test_aion_api_posts_nexboard_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mit Bild: ein Embed mit dem WebP, keine eigenen Boss-Bilder; ohne Bild wie früher."""
    import base64

    import bot.modules.aion2.runs.posts as dedup

    webp = b"RIFF\x10\0\0\0WEBPVP8L" + b"x" * 20
    sent: list[tuple[discord.Embed, list[discord.File]]] = []

    async def send(embed: discord.Embed, files: list[discord.File]) -> object:
        sent.append((embed, files))
        return object()

    channel = MagicMock(spec=discord.TextChannel)
    channel.send = send

    client = MagicMock(spec=discord.Client)
    client.get_channel.return_value = channel

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", nothing)  # keine echten Wartezeiten
    cog = dedup.RunPosts.__new__(dedup.RunPosts)
    cog.client, cog.api_pending, cog.api_posted = client, {}, []
    monkeypatch.setattr(cog, "_update_leaderboard", nothing)
    records = MagicMock()
    records.save = nothing
    cog.records = records
    run_: Run = {"dungeon": "Fire Temple", "difficulty": None, "bosses_total": 2, "bosses_killed": 2, "start_ms": 1,
                 "fight_ms": 60_000, "players": [{"name": "A", "damage": 600_000, "dps": 10_000}],
                 "bosses": [{"name": "B1", "players": [{"name": "A", "damage": 300_000}]},
                            {"name": "B2", "players": [{"name": "A", "damage": 300_000}]}],
                 "image": dedup.decode_image(base64.b64encode(webp).decode())}
    asyncio.run(cog._finalize_api_later(dedup.ApiCluster(run_, 1), 0, 5))
    embed, files = sent[-1]
    assert embed.image.url is None  # Bild nur als Anhang, sonst nach dem Bearbeiten doppelt
    assert [f.filename for f in files] == ["aion_run.webp"] and files[0].fp.read() == webp

    asyncio.run(cog._finalize_api_later(dedup.ApiCluster({**run_, "image": None}, 1), 0, 5))
    embed, files = sent[-1]
    assert embed.image.url is None
    assert [f.filename for f in files] == ["aion_run.png", "aion_boss_0.png", "aion_boss_1.png"]


def test_aion_hub_link(monkeypatch: pytest.MonkeyPatch) -> None:
    """Der NexHub meldet einen Run: Link an den wartenden Post, sonst nachträglich an den geposteten."""
    import time

    monkeypatch.setenv("AION_PUBLIC_URL", "https://hub.example.com")

    from bot.modules.aion2.runs.posts import ApiCluster, RunPosts, build_run_embed, same_run_start, with_hub_link

    base: Run = {"dungeon": "Fire Temple", "bosses_total": 4, "bosses_killed": 4,
                 "start_ms": 1_792_616_000_000, "fight_ms": 300_000,
                 "players": [{"name": "Navonex", "damage": 9_000_000, "dps": 30_000}]}
    url = "https://hub.example.com/hub/runs/7"
    assert same_run_start(base, "Fire Temple", base["start_ms"] + 5_000)
    assert not same_run_start(base, "Fire Temple", base["start_ms"] + 10 * 60_000)
    assert not same_run_start(base, "Draupnir", base["start_ms"])

    # Neuer Post mit Link: steht vorn im Analyse-Feld
    embed = build_run_embed(base, reporters=1, guild_id=1, bosses=[{"name": "B"}], hub_url=url)
    field = next(f for f in embed.fields if f.name == "📊 Analyse")
    assert str(field.value).startswith(f"[Im NexHub ansehen]({url})") and "Bestenliste" in str(field.value)
    # Nachträglich: Link vorn ergänzen, doppelt nie
    later = with_hub_link(build_run_embed(base, reporters=1, guild_id=1, bosses=[{"name": "B"}]), url)
    assert [str(f.value) for f in later.fields if f.name == "📊 Analyse"][0].startswith("[Im NexHub ansehen]")
    assert str(with_hub_link(later, url).fields[-1].value).count("NexHub") == 1
    # Ohne Analyse-Feld bekommt der Post eins
    bare = with_hub_link(build_run_embed(base, reporters=1), url)
    assert bare.fields[-1].value == f"[Im NexHub ansehen]({url})"

    cog = RunPosts.__new__(RunPosts)  # ohne Bot/DB/Loop: attach_hub_link braucht nur die Listen
    cog.api_pending, cog.api_posted = {}, []

    cluster = ApiCluster(base, guild_id=1)
    cog.api_pending[1] = [cluster]
    assert asyncio.run(cog.attach_hub_link("Fire Temple", base["start_ms"] + 2_000, url)) == "pending"
    assert cluster.hub_url == url
    # Zweiter Uploader (anderes NexBoard): der erste Link bleibt
    assert asyncio.run(cog.attach_hub_link("Fire Temple", base["start_ms"], url + "8")) == "pending"
    assert cluster.hub_url == url

    edited: list[list[discord.Embed]] = []

    async def edit(embeds: list[discord.Embed]) -> None:
        edited.append(embeds)

    msg = MagicMock(spec=discord.Message)
    msg.embeds = [build_run_embed(base, reporters=1)]
    msg.edit = edit
    cog.api_pending = {}
    cog.api_posted = [(time.time(), base, msg)]
    assert asyncio.run(cog.attach_hub_link("Fire Temple", base["start_ms"], url)) == "edited"
    assert edited[0][0].fields[-1].value == f"[Im NexHub ansehen]({url})"
    assert asyncio.run(cog.attach_hub_link("Fire Temple", base["start_ms"], url)) == "unknown"  # nur einmal ergänzen


def test_termin_tafel_und_pings() -> None:
    from datetime import timezone

    from bot.modules.aion2.schedule import board as tafel
    from bot.modules.aion2.schedule import due_pings as faellige_pings

    def um(text: str) -> float:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()

    jetzt = um("2026-10-07 02:57")
    text = str(tafel(jetzt).description)
    # Zeiten als Discord-Zeitstempel: jeder sieht sie in seiner Zeitzone
    assert f"**Riss** <t:{int(um('2026-10-07 03:00'))}:t>" in text
    assert f"**Wächterin Kaira** <t:{int(um('2026-10-07 04:00'))}:t>" in text
    # Riss und Shugo-Fest in 3 Minuten, Resets nie
    faellig = faellige_pings(jetzt, set())
    assert [n for n, _ in faellig] == ["Riss", "Shugo-Fest"]
    assert faellige_pings(jetzt, set(faellig)) == []  # nicht doppelt
    # läuft gerade: Riss offen bis 03:10
    assert f"läuft, bis <t:{int(um('2026-10-07 03:10'))}:t>" in str(tafel(um("2026-10-07 03:05")).description)


def test_run_report_from_hub_with_link() -> None:
    """accept_report: Run-API und Steuer-Route /control/run (Bericht über den NexHub) teilen die Annahme."""
    from aiohttp.test_utils import TestClient, TestServer
    from nexcore import EventBus, Paths

    from bot.core import BotContext
    from bot.core.host import module_routes
    from bot.core.web import RouteTable, control_app
    from bot.modules.aion2.runs import RunPosts
    from bot.modules.aion2.runs.posts import ApiCluster

    key = "k" * 32
    auth = {"Authorization": f"Bearer {key}"}
    started: list[tuple[ApiCluster, int]] = []
    players = [{"name": "Gamunex", "cls": "chanter", "damage": 1000, "dps": 10}]
    report = {"dungeon": "Fire Temple", "bosses_total": 1, "bosses_killed": 1, "start_ms": 1_000,
              "fight_ms": 100, "players": players}

    async def go() -> None:
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "t.sqlite3")
            await db.connect()
            await db.set(5, "aion_channel", 77)
            client = SimpleNamespace(get_guild=lambda gid: object() if gid == 5 else None)
            runs = RunPosts(BotContext(bus=EventBus(), paths=Paths("test"), db=db, client=client))  # type: ignore[arg-type]
            runs.active = True

            async def finalize(cluster: ApiCluster, _delay: int, channel_id: int) -> None:
                started.append((cluster, channel_id))

            setattr(runs, "_finalize_api_later", finalize)  # Post im Test nicht abschicken
            table = RouteTable()
            module_routes(runs, table)
            async with TestClient(TestServer(control_app(table, key))) as http:
                first = await http.post("/control/run", headers=auth, json={
                    "guild_id": 5, "report": report, "url": "https://hub.example.com/hub/runs/1"})
                assert first.status == 200 and await first.json() == {"ok": True, "merged": False}
                # gleicher Run, zweiter Spieler, direkt über die Run-API-Annahme
                assert await runs.accept_report(5, dict(report)) == (200, {"ok": True, "merged": True})
                await asyncio.sleep(0)
                assert (await http.post("/control/run", headers=auth,
                                        json={"guild_id": 6, "report": report})).status == 400
                assert (await http.post("/control/run", headers=auth,
                                        json={"guild_id": 5, "report": {"dungeon": ""}})).status == 400
                assert (await http.post("/control/run", headers=auth,
                                        json={"guild_id": 5, "report": report, "url": "ftp://x"})).status == 400
            await db.set(5, "aion_channel", None)
            assert (await runs.accept_report(5, dict(report)))[0] == 409
            await db.close()

    asyncio.run(go())
    (cluster, channel_id), = started
    assert channel_id == 77 and len(cluster.reports) == 2
    assert cluster.hub_url is not None and cluster.hub_url.endswith("/runs/1")
