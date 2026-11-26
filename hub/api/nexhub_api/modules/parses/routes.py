"""Parses je Run, gerechnet nur aus der Datenbank (Ranglisten aus fetcher.py, Gilde aus allen Runs):

    GET /api/parses/runs/{run_id}            mit Login
    GET /api/public/parses/shared/{token}    geteilter Run (/r/<token>), ohne Login
    GET /api/parses/device/runs/{run_id}     eigener Run des gekoppelten NexBoards, für das Run-Bild in Discord
    GET /api/parses/legions                  Legionen der Gilde und Vorschläge aus den Momentaufnahmen
    PUT /api/parses/legions                  Legionen der Gilde ersetzen, nur Admins

Nur getötete Bosse. Je Kampf (`fight`) und Spielername:
    eu_at None        Rangliste noch nicht geladen
    eu_n 0            Abyss Logs führt für diesen Boss keine Rangliste
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
from ..bis.abysslogs import REGION
from ..logs.models import Run, RunCharacter
from .calc import GUILD_MIN, guild_bests, percentile
from .models import GuildLegion, ParseBoard

router = APIRouter(prefix="/api/parses", tags=["runs"])
public_router = APIRouter(prefix="/api/public/parses", tags=["öffentlich"])


class Parse(BaseModel):
    eu: int | None
    eu_n: int | None
    eu_at: datetime | None
    guild: int | None
    guild_n: int
    member: bool


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


async def _parses(request: Request, db: DB, run: Run) -> RunParses:
    killed = [b for b in run.summary.get("bosses", []) if b.get("killed")]
    if not killed:
        return RunParses(guild_min=GUILD_MIN, fights={})
    pairs = {(b["mob"], p.get("cls")) for b in killed for p in b.get("players", [])}
    boards = {(b.boss, b.cls): b for b in (await db.scalars(select(ParseBoard).where(
        ParseBoard.region == REGION, ParseBoard.boss.in_({m for m, _ in pairs}),
        ParseBoard.cls.in_({c for _, c in pairs if c})))).all()}
    guild = await _guild(request, db)
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
            out[name] = Parse(eu=percentile(p["dps"], board.dps) if board else None,
                              eu_n=len(board.dps) if board else None,
                              eu_at=_utc(board.fetched_at) if board else None,
                              guild=percentile(p["dps"], mates) if member and len(mates) >= GUILD_MIN else None,
                              guild_n=len(mates), member=member)
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
