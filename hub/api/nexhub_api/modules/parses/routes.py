"""Parses je Run, gerechnet nur aus der Datenbank (Ranglisten aus fetcher.py, Gilde aus allen Runs):

    GET /api/parses/runs/{run_id}            mit Login
    GET /api/public/parses/shared/{token}    geteilter Run (/r/<token>), ohne Login

Nur getötete Bosse. Je Kampf (`fight`) und Spielername:
    eu_at None        Rangliste noch nicht geladen
    eu_n 0            Abyss Logs führt für diesen Boss keine Rangliste
    guild None        weniger als GUILD_MIN Charaktere dieser Klasse an diesem Boss (guild_n)
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select

from ...deps import DB, CurrentUser
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


def _utc(at: datetime) -> datetime:
    """SQLite gibt Zeitpunkte ohne Zone zurück; gespeichert sind sie in UTC."""
    return at if at.tzinfo else at.replace(tzinfo=UTC)


async def _parses(db: DB, run: Run) -> RunParses:
    killed = [b for b in run.summary.get("bosses", []) if b.get("killed")]
    mobs = {b["mob"] for b in killed}
    boards = {(b.boss, b.cls): b for b in (await db.scalars(select(ParseBoard).where(
        ParseBoard.region == REGION, ParseBoard.boss.in_(mobs)))).all()} if mobs else {}
    guild = guild_bests((await db.scalars(select(Run.summary))).all())
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


@router.get("/runs/{run_id}")
async def run_parses(run_id: int, user: CurrentUser, db: DB) -> RunParses:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run nicht gefunden")
    return await _parses(db, run)


@public_router.get("/shared/{token}")
async def shared_parses(token: str, db: DB, response: Response) -> RunParses:
    run = await db.scalar(select(Run).where(Run.share_token == token)) if len(token) <= 32 else None
    if run is None:
        raise HTTPException(404, "Link ungültig oder zurückgezogen")
    not_for_search_engines(response)
    return await _parses(db, run)
