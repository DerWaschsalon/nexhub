"""Parses je Run, gerechnet nur aus der Datenbank (Ranglisten aus fetcher.py, Gilde aus allen Runs):

    GET /api/parses/runs/{run_id}            mit Login
    GET /api/public/parses/shared/{token}    geteilter Run (/r/<token>), ohne Login
    GET /api/parses/device/runs/{run_id}     eigener Run des gekoppelten NexBoards, für das Run-Bild in Discord

Nur getötete Bosse. Je Kampf (`fight`) und Spielername:
    eu_at None        Rangliste noch nicht geladen
    eu_n 0            Abyss Logs führt für diesen Boss keine Rangliste
    guild None        weniger als GUILD_MIN Charaktere dieser Klasse an diesem Boss (guild_n)
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from ...deps import DB, CurrentDevice, CurrentUser
from ...routes.public import not_for_search_engines
from ..bis.abysslogs import REGION
from ..logs.models import Run
from .calc import GUILD_MIN, guild_bests, percentile
from .models import ParseBoard

router = APIRouter(prefix="/api/parses", tags=["runs"])
public_router = APIRouter(prefix="/api/public/parses", tags=["öffentlich"])


class Parse(BaseModel):
    eu: int | None
    eu_n: int | None
    eu_at: datetime | None
    guild: int | None
    guild_n: int


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


def _utc(at: datetime) -> datetime:
    """SQLite gibt Zeitpunkte ohne Zone zurück; gespeichert sind sie in UTC."""
    return at if at.tzinfo else at.replace(tzinfo=UTC)


async def _guild(request: Request, db: DB) -> dict[tuple[int, str], list[float]]:
    """Gildenbestwerte, im Speicher gehalten, bis ein Run dazukommt oder gelöscht wird (Anzahl und höchste ID).
    So liest nicht jeder Aufruf einer Kampfseite alle Runs."""
    key = tuple((await db.execute(select(func.count(), func.max(Run.id)).select_from(Run))).one())
    cached = getattr(request.app.state, "parses_guild", None)
    if cached is None or cached[0] != key:
        cached = (key, guild_bests((await db.scalars(select(Run.summary))).all()))
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
            mates = guild.get((b["mob"], p.get("cls")), [])
            out[name] = Parse(eu=percentile(p["dps"], board.dps) if board else None,
                              eu_n=len(board.dps) if board else None,
                              eu_at=_utc(board.fetched_at) if board else None,
                              guild=percentile(p["dps"], mates) if len(mates) >= GUILD_MIN else None,
                              guild_n=len(mates))
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
