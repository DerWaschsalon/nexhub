"""Parses: Rechnung (calc.py), Abruf der Ranglisten (fetcher.py), Routen (routes.py)."""
import asyncio
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api.models import User
from nexhub_api.modules.logs.models import Run, RunCharacter
from nexhub_api.modules.parses.calc import guild_bests, needed_pairs, percentile
from nexhub_api.modules.parses.fetcher import ParseFetcher
from nexhub_api.modules.parses.models import ParseBoard

from .conftest import ADMIN, MEMBER
from .test_devices import ORIGIN

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
    runs = [summary(boss(1, [("A", "ranger", 100), ("B", "ranger", 200), ("X", "ranger", 900)])),
            summary(boss(1, [("A", "ranger", 300), ("A", "gladiator", 50)]))]
    assert guild_bests(runs, {"A", "B"}) == {(1, "ranger"): [200.0, 300.0], (1, "gladiator"): [50.0]}


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
    assert b.cp == [123_456] * 250
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


def add_board(database_url, boss: int, cls: str, dps: list[float], cp: list[int] | None = None) -> None:
    async def work(sm):
        async with sm() as db:
            db.add(ParseBoard(boss=boss, cls=cls, region="eu", total=len(dps), dps=dps, cp=cp,
                              fetched_at=datetime.now(UTC)))
            await db.commit()
    db_do(database_url, work)


def new_run(database_url, s: dict, share_token: str | None = None, legion: str | None = "Gilde") -> int:
    """Run mit Momentaufnahmen aller Spieler in `legion` (None: keine Momentaufnahmen)."""
    async def work(sm):
        run_id = await add_run(sm, s, share_token=share_token)
        if legion is not None:
            names = {p["name"] for b in s["bosses"] for p in b["players"]}
            async with sm() as db:
                db.add_all(snapshot(run_id, n, legion) for n in names)
                await db.commit()
        return run_id
    return db_do(database_url, work)


def snapshot(run_id: int, name: str, legion: str, at: datetime | None = None, cp: int | None = None) -> RunCharacter:
    return RunCharacter(run_id=run_id, name=name, status="ok", fetched_at=at or datetime.now(UTC), combat_power=cp,
                        data={"v": 2, "en": {"profile": {"name": name, "guild": legion}}, "de": {}})


def set_legions(as_user, *names: str) -> dict:
    r = as_user(ADMIN).put("/api/parses/legions", json={"legions": list(names)}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


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
    set_legions(as_user, "Gilde")
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


def test_parses_fuers_run_bild_des_nexboards(client, as_user, database_url):
    from .test_devices import bearer, pair

    token = pair(client, as_user(MEMBER))
    add_board(database_url, 1, "ranger", [100, 200, 300, 400])
    run_id = new_run(database_url, summary(
        boss(1, [("A", "ranger", 150)], fight="f1"),            # erster Versuch, schwächer
        boss(1, [("A", "ranger", 350)], fight="f2"),            # zweiter Kill am selben Boss zählt
        boss(2, [("A", "ranger", 100)], killed=False, fight="f3")))
    r = client.get(f"/api/parses/device/runs/{run_id}", headers=bearer(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"bosses": {"1": {"A": {"eu": 75, "guild": None}}}}
    assert client.get(f"/api/parses/device/runs/{run_id}").status_code == 401
    assert client.get("/api/parses/device/runs/999999", headers=bearer(token)).status_code == 404


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
    monkeypatch.setattr(routes, "guild_bests", lambda *a: calls.append(1) or real(*a))
    set_legions(as_user, "Gilde")
    member = as_user(MEMBER)
    run_id = new_run(database_url, summary(boss(1, [("A", "ranger", 250)])))
    member.get(f"/api/parses/runs/{run_id}")
    member.get(f"/api/parses/runs/{run_id}")
    assert len(calls) == 1
    new_run(database_url, summary(boss(1, [("B", "ranger", 100)])))
    assert member.get(f"/api/parses/runs/{run_id}").json()["fights"]["f1"]["A"]["guild_n"] == 2
    assert len(calls) == 2


def test_gilde_nur_mitglieder_der_legionen(as_user, database_url):
    """Randoms aus der Gruppe zählen nicht und bekommen keinen Gildenwert; Mitglied ist, wer in seiner jüngsten
    Momentaufnahme in einer eingetragenen Legion ist, auch wenn der neue Run noch keine Momentaufnahme hat."""
    set_legions(as_user, "taubenschlag", "Neu")
    member = as_user(MEMBER)
    for i in range(10):
        new_run(database_url, summary(boss(1, [(f"G{i}", "ranger", 100 + i), (f"R{i}", "ranger", 1000)])),
                legion="Taubenschlag")
    # die Randoms R0..R9 sind in ihrer jüngsten Momentaufnahme in einer anderen Legion
    async def randoms(sm):
        async with sm() as db:
            db.add(Run(**{c: getattr(await db.get(Run, 1), c) for c in ("user_id", "dungeon_id", "dungeon",
                   "difficulty", "start_ms", "end_ms", "complete", "bosses_total", "bosses_killed", "fights",
                   "hits", "summary", "size")}, sha256="randoms", character=None))
            await db.flush()
            later = datetime.now(UTC) + timedelta(minutes=1)
            run = await db.scalar(select(Run).where(Run.sha256 == "randoms"))
            db.add_all(snapshot(run.id, f"R{i}", "Andere", later) for i in range(10))
            await db.commit()
    db_do(database_url, randoms)
    run_id = new_run(database_url, summary(boss(1, [("G9", "ranger", 105), ("R0", "ranger", 1000)])), legion=None)
    fights = member.get(f"/api/parses/runs/{run_id}").json()["fights"]["f1"]
    assert fights["G9"]["member"] and fights["G9"]["guild_n"] == 10 and fights["G9"]["guild"] == 60
    assert not fights["R0"]["member"] and fights["R0"]["guild"] is None


def test_ohne_legionen_kein_gildenwert(as_user, database_url):
    member = as_user(MEMBER)
    ids = [new_run(database_url, summary(boss(1, [(f"C{i}", "ranger", 100 + i)]))) for i in range(10)]
    p = member.get(f"/api/parses/runs/{ids[-1]}").json()["fights"]["f1"]["C9"]
    assert p["guild"] is None and p["guild_n"] == 0 and not p["member"]


def test_legionen_pflegen(client, as_user, database_url):
    new_run(database_url, summary(boss(1, [("A", "ranger", 1), ("B", "ranger", 1)])), legion="Taubenschlag")
    new_run(database_url, summary(boss(1, [("C", "ranger", 1)])), legion="Katzen")
    assert client.get("/api/parses/legions").status_code == 401
    member = as_user(MEMBER)
    assert member.put("/api/parses/legions", json={"legions": ["X"]}, headers=ORIGIN).status_code == 403
    body = member.get("/api/parses/legions").json()
    assert body == {"legions": [], "known": [{"name": "Taubenschlag", "characters": 2},
                                             {"name": "Katzen", "characters": 1}]}
    assert set_legions(as_user, " Taubenschlag ", "taubenschlag", "Neu")["legions"] == ["Neu", "Taubenschlag"]
    assert set_legions(as_user)["legions"] == []
    assert as_user(ADMIN).put("/api/parses/legions", json={"legions": [""]}, headers=ORIGIN).status_code == 422


def test_rangliste_ohne_kampfkraft_wird_neu_geholt(fake, database_url):
    fake.abyss.boards = {8001: [f"N{i}" for i in range(20)]}

    async def work(fetcher, sm):
        await add_run(sm, summary(boss(8001, [("A", "ranger", 100)])))
        async with sm() as db:
            db.add(ParseBoard(boss=8001, cls="ranger", region="eu", total=1, dps=[1.0], cp=None,
                              fetched_at=datetime.now(UTC)))
            await db.commit()
        assert await fetcher.tick() == 1
        return await boards(sm)
    [b] = fetch(database_url, fake, work)
    assert len(b.cp) == 20


def add_snapshot(database_url, run_id: int, name: str, cp: int, at: datetime | None = None) -> None:
    async def work(sm):
        async with sm() as db:
            await db.execute(delete(RunCharacter).where(RunCharacter.run_id == run_id, RunCharacter.name == name))
            db.add(snapshot(run_id, name, "Gilde", at, cp=cp))
            await db.commit()
    db_do(database_url, work)


def test_eu_nur_im_cp_bereich(as_user, database_url):
    """250.000 CP: es zählen die Einträge von 245.000 bis 255.000, nicht die schwachen 200.000er davor."""
    member = as_user(MEMBER)
    dps = [float(10 * i) for i in range(1, 31)]                          # 10 … 300
    cp = [200_000] * 10 + [245_000, 255_000] + [250_000] * 18            # erste 10 außerhalb
    add_board(database_url, 1, "ranger", dps, cp)
    run_id = new_run(database_url, summary(boss(1, [("A", "ranger", 200), ("B", "ranger", 200), ("C", "ranger", 200)])),
                     legion=None)
    add_snapshot(database_url, run_id, "A", 250_000)
    add_snapshot(database_url, run_id, "B", 300_000)
    p = member.get(f"/api/parses/runs/{run_id}").json()["fights"]["f1"]
    # A: 20 Einträge im Bereich (110 … 300), 10 davon ≤ 200
    assert (p["A"]["eu"], p["A"]["eu_n"], p["A"]["eu_cp"], p["A"]["eu_few"]) == (50, 20, 250_000, False)
    # B: niemand im Bereich: kein Wert
    assert (p["B"]["eu"], p["B"]["eu_n"], p["B"]["eu_few"]) == (None, 0, True)
    # C: Kampfkraft unbekannt: gegen alle 30
    assert (p["C"]["eu"], p["C"]["eu_n"], p["C"]["eu_cp"]) == (66, 30, None)


def test_cp_aus_frueherem_run_wenn_der_neue_noch_fehlt(as_user, database_url):
    member = as_user(MEMBER)
    add_board(database_url, 1, "ranger", [float(i) for i in range(1, 21)], [250_000] * 20)
    old = new_run(database_url, summary(boss(1, [("A", "ranger", 5)])), legion=None)
    add_snapshot(database_url, old, "A", 251_000)
    run_id = new_run(database_url, summary(boss(1, [("A", "ranger", 10)])), legion=None)
    p = member.get(f"/api/parses/runs/{run_id}").json()["fights"]["f1"]["A"]
    assert (p["eu"], p["eu_cp"]) == (50, 251_000)
    add_snapshot(database_url, run_id, "A", 400_000, datetime.now(UTC) - timedelta(days=1))  # dieser Run zählt vor
    assert member.get(f"/api/parses/runs/{run_id}").json()["fights"]["f1"]["A"]["eu_few"] is True


def test_beste_parses_der_gilde_seit(as_user, database_url):
    set_legions(as_user, "Gilde")
    member = as_user(MEMBER)
    add_board(database_url, 1, "ranger", [float(i) for i in range(1, 21)])
    first = new_run(database_url, summary(boss(1, [("A", "ranger", 5), ("B", "ranger", 18)])))
    new_run(database_url, summary(boss(1, [("A", "ranger", 15)])))
    new_run(database_url, summary(boss(1, [("Random", "ranger", 20)])), legion="Andere")
    top = member.get(f"/api/parses/top?since_ms={NOW_MS - DAY_MS}").json()
    assert [(t["name"], t["eu"]) for t in top] == [("B", 90), ("A", 75)]
    assert top[0]["run_id"] == first and top[0]["boss"] == "Boss 1" and top[0]["cls"] == "ranger"
    assert member.get(f"/api/parses/top?since_ms={NOW_MS + DAY_MS}").json() == []


def test_bestenliste_ab_lila(as_user, database_url):
    """Je Mitglied der beste Parse ab 75 über alle Runs; /top und /hall lesen das Verzeichnis aus hall.py."""
    from nexhub_api.modules.parses.hall import HallOfFame

    set_legions(as_user, "Gilde")
    member = as_user(MEMBER)
    assert member.get("/api/parses/hall").json() == {"computed_at": None, "entries": []}
    add_board(database_url, 1, "ranger", [float(i) for i in range(1, 21)])
    new_run(database_url, summary(boss(1, [("A", "ranger", 16), ("B", "ranger", 14), ("C", "ranger", 20)])))
    new_run(database_url, summary(boss(1, [("A", "ranger", 18)])))
    new_run(database_url, summary(boss(1, [("R", "ranger", 20)])), legion="Andere")

    async def work(sm):
        return await HallOfFame(member.app.state, sm).tick()
    index = db_do(database_url, work)
    assert sorted((e.name, e.eu) for e in index.entries) == [("A", 80), ("A", 90), ("B", 70), ("C", 100)]
    body = member.get("/api/parses/hall").json()
    assert [(e["name"], e["eu"]) for e in body["entries"]] == [("C", 100), ("A", 90)] and body["computed_at"]
    top = member.get(f"/api/parses/top?since_ms={NOW_MS - DAY_MS}").json()
    assert [(t["name"], t["eu"]) for t in top] == [("C", 100), ("A", 90), ("B", 70)]
