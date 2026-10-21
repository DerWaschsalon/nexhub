"""Öffentlicher Bereich: alles hier ist ohne Login erreichbar.

Nur herausgeben, was geteilt werden darf:
    GET /api/public/info            ist der Login eingerichtet?
    GET /api/public/runs/{token}    ein geteilter Run (Teilen-Link /r/<token>)
    GET /api/public/runs/{token}/fights/{kampf}   ein Kampf daraus im Detail

Geteilte Runs zeigen Eckdaten und Zusammenfassung mit den Namen der Mitspieler, aber kein
Discord-Konto und nicht die Rohdatei. Suchmaschinen sollen sie nicht aufnehmen.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import DB, SettingsDep
from ..models import Run
from .runs import load_fight_detail

router = APIRouter(prefix="/api/public", tags=["öffentlich"])


class Info(BaseModel):
    login: bool  # ist der Discord-Login eingerichtet?


@router.get("/info")
async def info(settings: SettingsDep) -> Info:
    return Info(login=settings.discord_configured)


class SharedRun(BaseModel):
    dungeon: str
    difficulty: str | None
    start_ms: int
    end_ms: int
    complete: bool
    bosses_total: int
    bosses_killed: int
    fights: int
    hits: int
    character: str | None
    summary: dict


async def _shared(db: DB, token: str, response: Response) -> Run:
    run = await db.scalar(select(Run).where(Run.share_token == token)) if len(token) <= 32 else None
    if run is None:
        raise HTTPException(404, "Link ungültig oder zurückgezogen")
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"
    return run


@router.get("/runs/{token}/fights/{fight_id}")
async def shared_fight(token: str, fight_id: str, db: DB, settings: SettingsDep, response: Response) -> dict:
    return await load_fight_detail(settings, await _shared(db, token, response), fight_id)


@router.get("/runs/{token}")
async def shared_run(token: str, db: DB, response: Response) -> SharedRun:
    run = await _shared(db, token, response)
    return SharedRun(dungeon=run.dungeon, difficulty=run.difficulty, start_ms=run.start_ms, end_ms=run.end_ms,
                     complete=run.complete, bosses_total=run.bosses_total, bosses_killed=run.bosses_killed,
                     fights=run.fights, hits=run.hits, character=run.character, summary=run.summary)
