"""Parses je Run, gerechnet nur aus der Datenbank (Ranglisten aus fetcher.py, Gilde aus allen Runs):

    GET /api/parses/runs/{run_id}            mit Login
    GET /api/public/parses/shared/{token}    geteilter Run (/r/<token>), ohne Login
    GET /api/parses/device/runs/{run_id}     eigener Run des gekoppelten NexBoards, für das Run-Bild in Discord
    GET /api/parses/top?since_ms=            bester EU-Parse je Gildenmitglied seit since_ms (Startseite)
    GET /api/parses/hall                     Bestenliste ab Lila über alle Runs

/top und /hall lesen aus dem Verzeichnis aller Parses der Gilde, das hall.py alle 5 Minuten im Hintergrund rechnet
(state.parses_index); neue Runs erscheinen dort also mit bis zu 5 Minuten Verzug.
    GET /api/parses/legions                  Legionen der Gilde und Vorschläge aus den Momentaufnahmen
    PUT /api/parses/legions                  Legionen der Gilde ersetzen, nur Admins

Nur getötete Bosse. Je Kampf (`fight`) und Spielername:
    eu_at None        Rangliste noch nicht geladen
    eu_n 0            Abyss Logs führt für diesen Boss keine Rangliste
    eu_cp             eigene Kampfkraft: EU nur gegen Einträge mit cp ± CP_RANGE (eu_n zählt nur die).
                      None: Kampfkraft unbekannt oder Rangliste noch ohne, EU gegen alle Einträge
    eu_few True       weniger als EU_MIN Einträge im CP-Bereich: kein EU-Wert
    bench             DPS-Verteilung der letzten Woche bei Abyss Logs für Klasse und Kampfkraft (extras.py); None ohne
    member False      nicht in einer Legion der Gilde (Random aus der Gruppe): kein Gildenwert
    guild None        nicht in der Gilde oder weniger als GUILD_MIN Charaktere dieser Klasse an diesem Boss (guild_n)
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, NamedTuple

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete, func, select

from ...aion2 import localized
from ...deps import DB, AdminUser, CurrentDevice, CurrentUser
from ...routes.public import not_for_search_engines
from ..bis.abysslogs import REGION, abyss_class
from ..logs.models import Run, RunCharacter
from ..logs.routes import dungeon_names
from .calc import EU_MIN, GUILD_MIN, guild_bests, in_cp_range, percentile
from .models import GuildLegion, ParseBenchmark, ParseBoard

router = APIRouter(prefix="/api/parses", tags=["runs"])
public_router = APIRouter(prefix="/api/public/parses", tags=["öffentlich"])


class Bench(BaseModel):
    """Klassenstatistik wie bei Abyss Logs: DPS-Verteilung der letzten Woche für Klasse und Kampfkraft-Stufe an
    einem Boss, und wo der Spieler darin steht."""
    pct: int  # geschätzter Platz in der Verteilung, 0 bis 100 (zwischen den Stützpunkten gerade verbunden)
    lowest: float
    top75: float  # untere 25 % liegen darunter
    median: float
    top25: float
    top10: float
    highest: float
    week_before_median: float | None
    samples: int  # Kämpfe
    characters: int
    cp_floor: int | None  # Kampfkraft-Stufe; None: über alle Kampfkraft
    cp_ceil: int | None


BENCH_MIN = 20  # Kämpfe in der Kampfkraft-Stufe, sonst die Verteilung über alle Kampfkraft


def bench_pct(dps: float, c: dict) -> int:
    """Platz eines DPS-Werts in der Verteilung aus ihren Stützpunkten (Tiefstwert 0, untere 25 % 25, Median 50,
    Top 25 % 75, Top 10 % 90, Höchstwert 100), dazwischen linear."""
    points = [(c.get("lowest"), 0), (c.get("top75"), 25), (c["median"], 50), (c.get("top25"), 75),
              (c.get("top10"), 90), (c.get("highest"), 100)]
    points = [(float(v), p) for v, p in points if isinstance(v, int | float)]
    if dps <= points[0][0]:
        return points[0][1]
    for (v1, p1), (v2, p2) in zip(points, points[1:], strict=False):
        if dps <= v2:
            return int(p1 + (p2 - p1) * (dps - v1) / (v2 - v1)) if v2 > v1 else p2
    return 100


def _bench(cells: list[dict], cls: str | None, cp: int | None, dps: float) -> Bench | None:
    if not cls:
        return None
    mine = [c for c in cells if c.get("classHint") == abyss_class(cls)]
    near = [c for c in mine if cp and c.get("bracketCeil") and c["bracketFloor"] <= cp < c["bracketCeil"]
            and (c.get("samples") or 0) >= BENCH_MIN]
    c = near[0] if near else next((c for c in mine if not c.get("bracketCeil")), None)
    if c is None:
        return None
    m = c["median"]
    return Bench(pct=bench_pct(dps, c), lowest=c.get("lowest") or 0, top75=c.get("top75") or m, median=m,
                 top25=c.get("top25") or m, top10=c.get("top10") or m, highest=c.get("highest") or m,
                 week_before_median=c.get("weekBeforeMedian"), samples=c.get("samples") or 0,
                 characters=c.get("characters") or 0, cp_floor=c["bracketFloor"] if near else None,
                 cp_ceil=c["bracketCeil"] if near else None)


class Parse(BaseModel):
    eu: int | None
    eu_n: int | None
    eu_at: datetime | None
    eu_cp: int | None
    eu_few: bool
    guild: int | None
    guild_n: int
    member: bool
    bench: Bench | None = None


class RunParses(BaseModel):
    guild_min: int
    fights: dict[str, dict[str, Parse]]


class BossParse(BaseModel):
    eu: int | None
    guild: int | None


class DeviceParses(BaseModel):
    """Je Boss (mob als Text) und Spielername nur die Zahlen, die das Run-Bild zeigt. Hat ein Boss mehrere
    getötete Kämpfe im Run, gilt der mit dem höheren DPS des Spielers."""
    bosses: dict[str, dict[str, BossParse]]


LegionName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class Legions(BaseModel):
    legions: list[LegionName] = Field(max_length=20)


class KnownLegion(BaseModel):
    name: str
    characters: int


class LegionsOut(BaseModel):
    legions: list[str]
    known: list[KnownLegion]  # Legionen aus den Momentaufnahmen, die meisten Charaktere zuerst


def _utc(at: datetime) -> datetime:
    """SQLite gibt Zeitpunkte ohne Zone zurück; gespeichert sind sie in UTC."""
    return at if at.tzinfo else at.replace(tzinfo=UTC)


async def _character_legions(db: DB) -> dict[str, str]:
    """Legion je Charaktername laut seiner jüngsten Momentaufnahme ("" ohne Legion)."""
    rows = await db.execute(select(RunCharacter.name, RunCharacter.data).where(
        RunCharacter.status == "ok", RunCharacter.data.is_not(None)).order_by(RunCharacter.fetched_at))
    return {name: (localized(data).get("profile") or {}).get("guild") or "" for name, data in rows.all()}


class Guild(NamedTuple):
    members: frozenset[str]
    bests: dict[tuple[int, str], list[float]]


async def _guild(request: Request, db: DB) -> Guild:
    """Mitglieder und Gildenbestwerte, im Speicher gehalten, bis sich Runs (Anzahl, höchste ID), Momentaufnahmen
    (Anzahl, jüngste) oder die Legionen ändern. So liest nicht jeder Aufruf einer Kampfseite alle Runs."""
    legions = frozenset(n.casefold() for n in (await db.scalars(select(GuildLegion.name))).all())
    key = (tuple((await db.execute(select(func.count(), func.max(Run.id)).select_from(Run))).one()),
           tuple((await db.execute(select(func.count(), func.max(RunCharacter.fetched_at))
                                   .where(RunCharacter.status == "ok"))).one()),
           legions)
    cached = getattr(request.app.state, "parses_guild", None)
    if cached is None or cached[0] != key:
        members = frozenset(n for n, legion in (await _character_legions(db)).items() if legion.casefold() in legions) \
            if legions else frozenset()
        cached = (key, Guild(members, guild_bests((await db.scalars(select(Run.summary))).all(), members)))
        request.app.state.parses_guild = cached
    return cached[1]


async def _combat_power(db: DB, run: Run, names: set[str]) -> dict[str, int]:
    """Kampfkraft je Spieler: aus der Momentaufnahme dieses Runs, sonst (noch nicht geladen) die jüngste bekannte."""
    rows = await db.execute(select(RunCharacter.name, RunCharacter.combat_power, RunCharacter.run_id).where(
        RunCharacter.status == "ok", RunCharacter.combat_power.is_not(None), RunCharacter.name.in_(names))
        .order_by(RunCharacter.fetched_at))
    latest: dict[str, int] = {}
    this_run: dict[str, int] = {}
    for name, cp, run_id in rows.all():
        latest[name] = cp
        if run_id == run.id:
            this_run[name] = cp
    return latest | this_run


def _eu(dps: float, cp: int | None, board: ParseBoard | None) -> dict:
    if board is None:
        return {"eu": None, "eu_n": None, "eu_at": None, "eu_cp": cp, "eu_few": False}
    at = _utc(board.fetched_at)
    if cp and board.cp is not None:
        ranked = in_cp_range(board.dps, board.cp, cp)
        few = bool(board.dps) and len(ranked) < EU_MIN
        return {"eu": None if few else percentile(dps, ranked), "eu_n": len(ranked), "eu_at": at, "eu_cp": cp,
                "eu_few": few}
    return {"eu": percentile(dps, board.dps), "eu_n": len(board.dps), "eu_at": at, "eu_cp": None, "eu_few": False}


async def _parses(request: Request, db: DB, run: Run) -> RunParses:
    killed = [b for b in run.summary.get("bosses", []) if b.get("killed")]
    if not killed:
        return RunParses(guild_min=GUILD_MIN, fights={})
    pairs = {(b["mob"], p.get("cls")) for b in killed for p in b.get("players", [])}
    boards = {(b.boss, b.cls): b for b in (await db.scalars(select(ParseBoard).where(
        ParseBoard.region == REGION, ParseBoard.boss.in_({m for m, _ in pairs}),
        ParseBoard.cls.in_({c for _, c in pairs if c})))).all()}
    guild = await _guild(request, db)
    cps = await _combat_power(db, run, {p["name"] for b in killed for p in b.get("players", [])})
    benches = {b.boss: b.cells for b in (await db.scalars(select(ParseBenchmark).where(
        ParseBenchmark.boss.in_({b["mob"] for b in killed})))).all()}
    fights: dict[str, dict[str, Parse]] = {}
    for b in killed:
        best: dict[str, dict] = {}  # derselbe Name doppelt (Relog): der stärkere Eintrag
        for p in b.get("players", []):
            if p["name"] not in best or p["dps"] > best[p["name"]]["dps"]:
                best[p["name"]] = p
        out = fights.setdefault(b["fight"], {})
        for name, p in best.items():
            board = boards.get((b["mob"], p.get("cls")))
            mates = guild.bests.get((b["mob"], p.get("cls")), [])
            member = name in guild.members
            out[name] = Parse(**_eu(p["dps"], cps.get(name), board),
                              guild=percentile(p["dps"], mates) if member and len(mates) >= GUILD_MIN else None,
                              guild_n=len(mates), member=member,
                              bench=_bench(benches.get(b["mob"], []), p.get("cls"), cps.get(name), p["dps"]))
    return RunParses(guild_min=GUILD_MIN, fights=fights)


def _by_boss(run: Run, parses: RunParses) -> DeviceParses:
    dps = {(b["fight"], p["name"]): p["dps"] for b in run.summary.get("bosses", []) for p in b.get("players", [])}
    mobs = {b["fight"]: str(b["mob"]) for b in run.summary.get("bosses", [])}
    best: dict[str, dict[str, tuple[float, BossParse]]] = {}
    for fight, players in parses.fights.items():
        out = best.setdefault(mobs[fight], {})
        for name, p in players.items():
            value = dps.get((fight, name), 0)
            if name not in out or value > out[name][0]:
                out[name] = (value, BossParse(eu=p.eu, guild=p.guild))
    return DeviceParses(bosses={mob: {n: bp for n, (_, bp) in names.items()} for mob, names in best.items()})


@router.get("/device/runs/{run_id}")
async def device_run_parses(run_id: int, request: Request, device: CurrentDevice, db: DB) -> DeviceParses:
    """Parses des eben hochgeladenen Runs für das NexBoard (Bearer-Token), nur für eigene Runs."""
    run = await db.get(Run, run_id)
    if run is None or run.user_id != device.user_id:
        raise HTTPException(404, "Run nicht gefunden")
    return _by_boss(run, await _parses(request, db, run))


class TopParse(BaseModel):
    name: str
    cls: str | None
    eu: int
    boss: str
    fight: str
    run_id: int
    dungeon: str
    start_ms: int  # Beginn des Runs


class Hall(BaseModel):
    computed_at: datetime | None  # None: noch nicht gerechnet (kurz nach dem Start des Hubs)
    entries: list[TopParse]


class ParseIndex(NamedTuple):
    computed_at: datetime
    entries: list[TopParse]  # jeder EU-Parse eines Gildenmitglieds an einem getöteten Boss


HALL_MIN_EU = 75  # Lila und besser
HALL_COUNT = 5


TOP_RUNS = 200  # Sicherung: so viele Runs liest /top höchstens


@router.get("/top")
async def top_parses(request: Request, user: CurrentUser, db: DB, since_ms: int, limit: int = 10) -> list[TopParse]:
    """Je Mitglied der Gilde der beste EU-Parse in Runs ab since_ms, bester zuerst."""
    index: ParseIndex | None = getattr(request.app.state, "parses_index", None)
    if index is not None:
        entries = [e for e in index.entries if e.start_ms >= since_ms]
    else:  # gleich nach dem Start: direkt rechnen, begrenzt
        runs = (await db.scalars(select(Run).where(Run.start_ms >= since_ms).order_by(Run.start_ms.desc())
                                 .limit(TOP_RUNS))).all()
        entries = await member_parses(request, db, runs)
    return best_per_member(entries)[:min(max(limit, 1), 50)]


@router.get("/hall")
async def hall(request: Request, user: CurrentUser) -> Hall:
    """Je Mitglied der beste Parse ab Lila über alle Runs, die besten HALL_COUNT."""
    index: ParseIndex | None = getattr(request.app.state, "parses_index", None)
    if index is None:
        return Hall(computed_at=None, entries=[])
    return Hall(computed_at=index.computed_at, entries=best_per_member(index.entries, HALL_MIN_EU)[:HALL_COUNT])


def best_per_member(entries: list[TopParse], min_eu: int = 0) -> list[TopParse]:
    """Je Name der beste Parse (mindestens min_eu), bester zuerst; bei Gleichstand der frühere Run."""
    best: dict[str, TopParse] = {}
    for e in entries:
        if e.eu >= min_eu and (e.name not in best or (e.eu, -e.start_ms) > (best[e.name].eu, -best[e.name].start_ms)):
            best[e.name] = e
    return sorted(best.values(), key=lambda t: (-t.eu, t.start_ms, t.name))


async def member_parses(request: Request, db: DB, runs) -> list[TopParse]:
    """Alle EU-Parses der Mitglieder der Gilde in `runs`."""
    guild = await _guild(request, db)
    info = getattr(request.app.state, "dungeon_info", None) or {}
    out: list[TopParse] = []
    for run in runs:
        parses = await _parses(request, db, run)
        bosses = {b["fight"]: b for b in run.summary.get("bosses", [])}
        for fight, players in parses.fights.items():
            boss = bosses[fight]
            for name, p in players.items():
                if name not in guild.members or p.eu is None:
                    continue
                cls = next((q.get("cls") for q in boss.get("players", []) if q["name"] == name), None)
                out.append(TopParse(name=name, cls=cls, eu=p.eu, boss=boss["name"], fight=fight, run_id=run.id,
                                    dungeon=dungeon_names(run.dungeon_id, run.dungeon, None, info)[0],
                                    start_ms=run.start_ms))
    return out


@router.get("/legions")
async def get_legions(user: CurrentUser, db: DB) -> LegionsOut:
    known: dict[str, int] = {}
    for legion in (await _character_legions(db)).values():
        if legion:
            known[legion] = known.get(legion, 0) + 1
    return LegionsOut(legions=sorted((await db.scalars(select(GuildLegion.name))).all(), key=str.casefold),
                      known=[KnownLegion(name=n, characters=c)
                             for n, c in sorted(known.items(), key=lambda kv: (-kv[1], kv[0].casefold()))[:30]])


@router.put("/legions")
async def put_legions(body: Legions, admin: AdminUser, db: DB) -> LegionsOut:
    """Die Liste ersetzen. Groß- und Kleinschreibung zählt beim Vergleich nicht, doppelte fallen weg."""
    await db.execute(delete(GuildLegion))
    db.add_all(GuildLegion(name=n) for n in {n.casefold(): n for n in reversed(body.legions)}.values())
    await db.commit()
    return await get_legions(admin, db)


@router.get("/runs/{run_id}")
async def run_parses(run_id: int, request: Request, user: CurrentUser, db: DB) -> RunParses:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run nicht gefunden")
    return await _parses(request, db, run)


@public_router.get("/shared/{token}")
async def shared_parses(token: str, request: Request, db: DB, response: Response) -> RunParses:
    run = await db.scalar(select(Run).where(Run.share_token == token)) if len(token) <= 32 else None
    if run is None:
        raise HTTPException(404, "Link ungültig oder zurückgezogen")
    not_for_search_engines(response)
    return await _parses(request, db, run)
