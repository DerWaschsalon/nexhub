"""Charakterprofile zu einem Run (Momentaufnahmen aus characters.py), nur mit Login.

    GET  /api/runs/{id}/characters            alle Spieler des Runs mit Status, ohne die Daten (mit
                                              armory_id, wenn der Spieler in der Armory steht)
    GET  /api/runs/{id}/characters/{char}     eine Momentaufnahme
    POST /api/runs/{id}/characters/refresh    fehler/nicht_gefunden neu holen (wer hochgeladen hat
                                              oder ein Admin, höchstens alle 10 Minuten)

Geteilte Links (routes/public.py) zeigen keine Profile.
"""
from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import DB, CurrentUser
from ..models import Character, RunCharacter
from .runs import _get, _may_manage

router = APIRouter(prefix="/api/runs", tags=["characters"])

REFRESH_EVERY = 600  # Sekunden je Run; der Hub läuft mit einem Prozess, das reicht im Speicher
_refreshed: dict[int, float] = {}


class CharacterOut(BaseModel):
    id: int
    name: str
    cls: str | None
    server_id: int
    status: str
    combat_power: int | None
    item_level: int | None
    fetched_at: datetime | None
    armory_id: int | None = None  # derselbe Charakter in der Armory (routes/armory.py)


class CharacterDetail(CharacterOut):
    data: dict | None
    error: str | None


def _out(row: RunCharacter) -> dict:
    return dict(id=row.id, name=row.name, cls=row.cls, server_id=row.server_id, status=row.status,
                combat_power=row.combat_power, item_level=row.item_level, fetched_at=row.fetched_at)


@router.get("/{run_id}/characters")
async def list_characters(run_id: int, user: CurrentUser, db: DB) -> list[CharacterOut]:
    await _get(db, run_id)
    found = (await db.scalars(select(RunCharacter).where(RunCharacter.run_id == run_id)
                              .order_by(RunCharacter.name))).all()
    # Namen sind je Server eindeutig
    armory = {(server, name): cid for cid, server, name in (await db.execute(
        select(Character.id, Character.server_id, Character.name).where(
            Character.name.in_([row.name for row in found])))).all()}
    return [CharacterOut(**_out(row), armory_id=armory.get((row.server_id, row.name))) for row in found]


@router.get("/{run_id}/characters/{char_id}")
async def get_character(run_id: int, char_id: int, user: CurrentUser, db: DB) -> CharacterDetail:
    row = await db.scalar(select(RunCharacter).where(RunCharacter.run_id == run_id, RunCharacter.id == char_id))
    if row is None:
        raise HTTPException(404, "Spieler nicht in diesem Run")
    armory_id = await db.scalar(select(Character.id).where(Character.server_id == row.server_id,
                                                           Character.name == row.name))
    return CharacterDetail(**_out(row), armory_id=armory_id, data=row.data, error=row.error)


class Started(BaseModel):
    started: int


@router.post("/{run_id}/characters/refresh", status_code=202)
async def refresh(run_id: int, request: Request, user: CurrentUser, db: DB, background: BackgroundTasks) -> Started:
    run, _ = await _get(db, run_id)
    if not _may_manage(run, user):
        raise HTTPException(403, "Nur wer hochgeladen hat, oder ein Admin")
    fetcher = request.app.state.characters
    if fetcher is None:
        raise HTTPException(503, "Charakterprofile sind ausgeschaltet")
    if time.monotonic() - _refreshed.get(run_id, -REFRESH_EVERY) < REFRESH_EVERY:
        raise HTTPException(429, "Höchstens alle 10 Minuten")
    _refreshed[run_id] = time.monotonic()
    rows = (await db.scalars(select(RunCharacter).where(
        RunCharacter.run_id == run_id, RunCharacter.status.in_(("fehler", "nicht_gefunden"))))).all()
    for row in rows:
        row.status, row.error = "offen", None
    await db.commit()
    background.add_task(fetcher.run, run_id)
    return Started(started=len(rows))
