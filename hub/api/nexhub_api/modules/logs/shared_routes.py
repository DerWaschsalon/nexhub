"""Geteilte Runs, ohne Login erreichbar (Teilen-Link /r/<token>):

    GET /api/public/runs/{token}                  Eckdaten und Zusammenfassung
    GET /api/public/runs/{token}/fights/{kampf}   ein Kampf daraus im Detail

Gezeigt werden die Namen der Mitspieler, aber kein Discord-Konto und nicht die Rohdatei. Suchmaschinen sollen
die Seiten nicht aufnehmen.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from nexproto import dungeon_label
from pydantic import BaseModel
from sqlalchemy import select

from ...deps import DB, SettingsDep
from ...routes.public import not_for_search_engines
from .models import Run
from .routes import load_fight_detail

router = APIRouter(prefix="/api/public", tags=["öffentlich"])


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
    not_for_search_engines(response)
    return run


@router.get("/runs/{token}/fights/{fight_id}")
async def shared_fight(token: str, fight_id: str, db: DB, settings: SettingsDep, response: Response) -> dict:
    return await load_fight_detail(settings, await _shared(db, token, response), fight_id)


@router.get("/runs/{token}")
async def shared_run(token: str, db: DB, response: Response) -> SharedRun:
    run = await _shared(db, token, response)
    return SharedRun(dungeon=dungeon_label(run.dungeon_id, run.dungeon), difficulty=run.difficulty,
                     start_ms=run.start_ms, end_ms=run.end_ms,
                     complete=run.complete, bosses_total=run.bosses_total, bosses_killed=run.bosses_killed,
                     fights=run.fights, hits=run.hits, character=run.character, summary=run.summary)
