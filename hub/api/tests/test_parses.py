"""Parses: Rechnung (calc.py), Abruf der Ranglisten (fetcher.py), Routen (routes.py)."""
import asyncio
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api.models import User
from nexhub_api.modules.logs.models import Run
from nexhub_api.modules.parses.calc import guild_bests, needed_pairs, percentile
from nexhub_api.modules.parses.fetcher import ParseFetcher
from nexhub_api.modules.parses.models import ParseBoard

from .conftest import MEMBER

NOW_MS = int(time.time() * 1000)
DAY_MS = 86_400_000


def boss(mob: int, players: list[tuple[str, str | None, float]], killed: bool = True, fight: str = "f1") -> dict:
    return {"fight": fight, "name": f"Boss {mob}", "mob": mob, "start_ms": 0, "duration_ms": 120_000,
            "killed": killed, "loot": [],
            "players": [{"name": n, "cls": c, "damage": int(d * 120), "dps": d} for n, c, d in players]}


def summary(*bosses: dict) -> dict:
    return {"fight_ms": 0, "players": [], "bosses": list(bosses)}


def test_parse_grenzen():
    assert percentile(5, []) is None
    assert percentile(100, [10, 20, 30]) == 100
    assert percentile(1, [10, 20, 30]) == 0
    assert percentile(20, [10, 20, 30, 40]) == 50
    assert percentile(40, [10, 20, 30, 40]) == 100


def test_paare_nur_getoetete_bosse_mit_klasse():
    s = summary(boss(1, [("A", "ranger", 100), ("B", None, 50)]), boss(2, [("A", "ranger", 100)], killed=False))
    assert needed_pairs([s]) == {(1, "ranger")}


def test_gilde_bestwert_je_charakter():
    runs = [summary(boss(1, [("A", "ranger", 100), ("B", "ranger", 200)])),
            summary(boss(1, [("A", "ranger", 300), ("A", "gladiator", 50)]))]
    assert guild_bests(runs) == {(1, "ranger"): [200.0, 300.0], (1, "gladiator"): [50.0]}


async def add_run(sessionmaker, s: dict, start_ms: int = NOW_MS, share_token: str | None = None) -> int:
    """Ein Run mit dieser Zusammenfassung, ohne Datei; legt bei Bedarf einen Nutzer an."""
    async with sessionmaker() as db:
        user = await db.scalar(select(User).limit(1))
        if user is None:
            user = User(discord_id=1, username="u1", role="member")
            db.add(user)
            await db.flush()
        run = Run(user_id=user.id, sha256=f"{time.time_ns()}", size=1, dungeon_id=600082, dungeon="Ludra",
                  difficulty=None, start_ms=start_ms, end_ms=start_ms + 1, complete=True,
                  bosses_total=len(s["bosses"]), bosses_killed=0, fights=1, hits=1, character=None, summary=s,
                  share_token=share_token)
        db.add(run)
        await db.commit()
        return run.id


def fetch(database_url, fake, work):
    async def go():
        engine = create_async_engine(database_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.abyss)) as http:
            result = await work(ParseFetcher(sessionmaker, http, pause=0), sessionmaker)
        await engine.dispose()
        return result
    return asyncio.run(go())


async def boards(sessionmaker) -> list[ParseBoard]:
    async with sessionmaker() as db:
        return list((await db.scalars(select(ParseBoard).order_by(ParseBoard.boss))).all())


async def age(sessionmaker, days: float) -> None:
    async with sessionmaker() as db:
        for b in (await db.scalars(select(ParseBoard))).all():
            b.fetched_at = datetime.now(UTC) - timedelta(days=days)
        await db.commit()


def test_abruf_speichert_nur_dps_aufsteigend(fake, database_url):
    fake.abyss.boards = {8001: [f"N{i}" for i in range(250)]}

    async def work(fetcher, sm):
        await add_run(sm, summary(boss(8001, [("A", "ranger", 100)])))
        assert await fetcher.tick() == 1
        assert await fetcher.tick() == 0  # frisch: nicht noch einmal
        return await boards(sm)
    [b] = fetch(database_url, fake, work)
    assert (b.boss, b.cls, b.region, b.total) == (8001, "ranger", "eu", 250)
    assert len(b.dps) == 250 and b.dps == sorted(b.dps)
    assert "N1" not in repr(b.__dict__)
    assert sum("boss=8001" in c for c in fake.abyss.calls) == 3


def test_alter_run_und_wipe_loesen_nichts_aus(fake, database_url):
    async def work(fetcher, sm):
        await add_run(sm, summary(boss(8001, [("A", "ranger", 100)])), start_ms=NOW_MS - 31 * DAY_MS)
        await add_run(sm, summary(boss(8002, [("A", "ranger", 100)], killed=False)))
        return await fetcher.tick()
    assert fetch(database_url, fake, work) == 0


def test_fehler_laesst_alten_stand_stehen(fake, database_url):
    fake.abyss.boards = {8001: [f"N{i}" for i in range(250)]}

    async def work(fetcher, sm):
        await add_run(sm, summary(boss(8001, [("A", "ranger", 100)])))
        async with sm() as db:
            db.add(ParseBoard(boss=8001, cls="ranger", region="eu", total=1, dps=[1.0],
                              fetched_at=datetime.now(UTC) - timedelta(days=2)))
            await db.commit()
        fake.abyss.fail_page = 2
        await fetcher.tick()
        return await boards(sm)
    [b] = fetch(database_url, fake, work)
    assert b.dps == [1.0] and b.total == 1


def test_nicht_gewertet_als_leere_liste(fake, database_url):
    fake.abyss.not_ranked = {8001}

    async def work(fetcher, sm):
        await add_run(sm, summary(boss(8001, [("A", "ranger", 100)])))
        assert await fetcher.tick() == 1
        [b] = await boards(sm)
        assert (b.dps, b.total) == ([], 0)
        await age(sm, 2)
        assert await fetcher.tick() == 0
        await age(sm, 8)
        assert await fetcher.tick() == 1
    fetch(database_url, fake, work)


def test_hoechstens_fuenf_je_takt(fake, database_url):
    async def work(fetcher, sm):
        await add_run(sm, summary(*[boss(9100 + i, [("A", "ranger", 100)], fight=f"f{i}") for i in range(7)]))
        return await fetcher.tick(), await fetcher.tick()
    assert fetch(database_url, fake, work) == (5, 2)


def db_do(database_url, work):
    async def go():
        engine = create_async_engine(database_url)
        result = await work(async_sessionmaker(engine, expire_on_commit=False))
        await engine.dispose()
        return result
    return asyncio.run(go())


def add_board(database_url, boss: int, cls: str, dps: list[float]) -> None:
    async def work(sm):
        async with sm() as db:
            db.add(ParseBoard(boss=boss, cls=cls, region="eu", total=len(dps), dps=dps, fetched_at=datetime.now(UTC)))
            await db.commit()
    db_do(database_url, work)


def new_run(database_url, s: dict, share_token: str | None = None) -> int:
    return db_do(database_url, lambda sm: add_run(sm, s, share_token=share_token))


def test_parse_im_run(as_user, database_url):
    member = as_user(MEMBER)
    add_board(database_url, 1, "ranger", [100, 200, 300, 400])
    run_id = new_run(database_url, summary(boss(1, [("A", "ranger", 250)])))
    body = member.get(f"/api/parses/runs/{run_id}").json()
    p = body["fights"]["f1"]["A"]
    assert (p["eu"], p["eu_n"]) == (50, 4)
    assert p["eu_at"].endswith(("Z", "+00:00"))  # mit Zeitzone, sonst liest der Browser Ortszeit
    assert body["guild_min"] == 10


def test_gilde_erst_ab_zehn(as_user, database_url):
    member = as_user(MEMBER)
    ids = [new_run(database_url, summary(boss(1, [(f"C{i}", "ranger", 100 + i)]))) for i in range(9)]
    p = member.get(f"/api/parses/runs/{ids[-1]}").json()["fights"]["f1"]["C8"]
    assert p["guild"] is None and p["guild_n"] == 9
    ids.append(new_run(database_url, summary(boss(1, [("C9", "ranger", 50)]))))
    p = member.get(f"/api/parses/runs/{ids[8]}").json()["fights"]["f1"]["C8"]
    assert p["guild_n"] == 10 and p["guild"] == 100
    assert member.get(f"/api/parses/runs/{ids[9]}").json()["fights"]["f1"]["C9"]["guild"] == 10


def test_noch_nicht_geladen_und_nicht_gewertet(as_user, database_url):
    member = as_user(MEMBER)
    add_board(database_url, 2, "ranger", [])
    run_id = new_run(database_url, summary(boss(1, [("A", "ranger", 250)], fight="f1"),
                                           boss(2, [("A", "ranger", 250)], fight="f2")))
    fights = member.get(f"/api/parses/runs/{run_id}").json()["fights"]
    assert fights["f1"]["A"]["eu_at"] is None and fights["f1"]["A"]["eu"] is None
    assert fights["f2"]["A"]["eu_n"] == 0 and fights["f2"]["A"]["eu"] is None and fights["f2"]["A"]["eu_at"]


def test_wipe_ohne_klasse_und_doppelter_name(as_user, database_url):
    member = as_user(MEMBER)
    add_board(database_url, 1, "ranger", [100])
    run_id = new_run(database_url, summary(
        boss(1, [("A", "ranger", 250), ("A", "ranger", 120), ("B", None, 90)], fight="f1"),
        boss(3, [("A", "ranger", 250)], killed=False, fight="f2")))
    r = member.get(f"/api/parses/runs/{run_id}")
    assert r.status_code == 200
    fights = r.json()["fights"]
    assert "f2" not in fights
    assert fights["f1"]["B"]["eu"] is None and fights["f1"]["B"]["guild_n"] == 0
    assert set(fights["f1"]) == {"A", "B"}


def test_zugriff(client, as_user, database_url):
    run_id = new_run(database_url, summary(boss(1, [("A", "ranger", 250)])), share_token="t0ken")
    assert client.get(f"/api/parses/runs/{run_id}").status_code == 401
    assert as_user(MEMBER).get("/api/parses/runs/999999").status_code == 404
    r = client.get("/api/public/parses/shared/t0ken")
    assert r.status_code == 200 and "A" in r.json()["fights"]["f1"]
    assert r.headers["X-Robots-Tag"].startswith("noindex")
    assert client.get("/api/public/parses/shared/falsch").status_code == 404
    assert client.get("/api/public/parses/shared/" + "x" * 40).status_code == 404


def test_fehlschlaege_verdraengen_andere_nicht(fake, database_url):
    fake.abyss.failing = {9100 + i for i in range(6)}

    async def work(fetcher, sm):
        await add_run(sm, summary(*[boss(9100 + i, [("A", "ranger", 100)], fight=f"f{i}") for i in range(7)]))
        first = await fetcher.tick()
        calls = len(fake.abyss.calls)
        second, third = await fetcher.tick(), await fetcher.tick()
        return first, second, third, len(fake.abyss.calls) - calls
    first, second, third, calls = fetch(database_url, fake, work)
    # Takt 1: fünf Fehlschläge; Takt 2: der sechste Fehlschlag und die gesunde Rangliste; Takt 3: nichts
    assert (first, second, third) == (0, 1, 0)
    assert calls == 2


def test_gilde_nicht_bei_jedem_aufruf_neu_gerechnet(as_user, database_url, monkeypatch):
    from nexhub_api.modules.parses import routes
    calls = []
    real = routes.guild_bests
    monkeypatch.setattr(routes, "guild_bests", lambda s: calls.append(1) or real(s))
    member = as_user(MEMBER)
    run_id = new_run(database_url, summary(boss(1, [("A", "ranger", 250)])))
    member.get(f"/api/parses/runs/{run_id}")
    member.get(f"/api/parses/runs/{run_id}")
    assert len(calls) == 1
    new_run(database_url, summary(boss(1, [("B", "ranger", 100)])))
    assert member.get(f"/api/parses/runs/{run_id}").json()["fights"]["f1"]["A"]["guild_n"] == 2
    assert len(calls) == 2
