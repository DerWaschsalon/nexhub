"""Charakterprofile zu einem Run (Momentaufnahmen aus characters.py), nur mit Login.

    GET  /api/runs/{id}/characters            alle Spieler des Runs mit Status, ohne die Daten (mit
                                              armory_id, wenn der Spieler in der Armory steht)
    GET  /api/runs/{id}/characters/{char}     eine Momentaufnahme
    POST /api/runs/{id}/characters/refresh    fehler/nicht_gefunden neu holen (wer hochgeladen hat
                                              oder ein Admin, höchstens alle 10 Minuten)
    POST /api/runs/{id}/characters/{char}/details   Werte je Gegenstand nachladen (alle Angemeldeten,
                                              je Spieler höchstens alle 10 Minuten; characters.load_details)

Geteilte Links (routes/public.py) zeigen keine Profile.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...deps import DB, CurrentUser
from .characters import has_item_ids
from .models import CharacterStatus, RunCharacter
from .routes import _get, _may_manage

router = APIRouter(prefix="/api/runs", tags=["characters"])

REFRESH_EVERY = 600  # Sekunden je Run bzw. Spieler; der Hub läuft mit einem Prozess, das reicht im Speicher
_refreshed: dict[int, float] = {}
_details: dict[int, float] = {}


class CharacterOut(BaseModel):
    id: int
    name: str
    cls: str | None
    server_id: int
    status: CharacterStatus
    combat_power: int | None
    item_level: int | None
    fetched_at: datetime | None
    armory_id: int | None = None  # derselbe Charakter in der Armory (siehe armory_ids)


class CharacterDetail(CharacterOut):
    data: dict | None
    error: str | None


def _out(row: RunCharacter) -> dict:
    return dict(id=row.id, name=row.name, cls=row.cls, server_id=row.server_id, status=row.status,
                combat_power=row.combat_power, item_level=row.item_level, fetched_at=row.fetched_at)


Key = tuple[int, str]  # (Server, Name): Namen sind je Server eindeutig
Lookup = Callable[[AsyncSession, list[Key]], Awaitable[dict[Key, int]]]


async def armory_ids(request: Request, db: DB, rows: Sequence[RunCharacter]) -> dict[Key, int]:
    """Dieselben Charaktere in der Armory. Die Suche legt das Modul Armory in state.armory_ids ab; ohne es
    gibt es keine Verweise."""
    lookup: Lookup | None = getattr(request.app.state, "armory_ids", None)
    return await lookup(db, [(row.server_id, row.name) for row in rows]) if lookup else {}


@router.get("/{run_id}/characters")
async def list_characters(run_id: int, request: Request, user: CurrentUser, db: DB) -> list[CharacterOut]:
    await _get(db, run_id)
    found = (await db.scalars(select(RunCharacter).where(RunCharacter.run_id == run_id)
                              .order_by(RunCharacter.name))).all()
    armory = await armory_ids(request, db, found)
    return [CharacterOut(**_out(row), armory_id=armory.get((row.server_id, row.name))) for row in found]


@router.get("/{run_id}/characters/{char_id}")
async def get_character(run_id: int, char_id: int, request: Request, user: CurrentUser,
                        db: DB) -> CharacterDetail:
    row = await db.scalar(select(RunCharacter).where(RunCharacter.run_id == run_id, RunCharacter.id == char_id))
    if row is None:
        raise HTTPException(404, "Spieler nicht in diesem Run")
    armory_id = (await armory_ids(request, db, [row])).get((row.server_id, row.name))
    return CharacterDetail(**_out(row), armory_id=armory_id, data=row.data, error=row.error)


class RefreshStarted(BaseModel):
    started: int


@router.post("/{run_id}/characters/refresh", status_code=202)
async def refresh(run_id: int, request: Request, user: CurrentUser, db: DB,
                  background: BackgroundTasks) -> RefreshStarted:
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
    return RefreshStarted(started=len(rows))


@router.post("/{run_id}/characters/{char_id}/details", status_code=202)
async def load_details(run_id: int, char_id: int, request: Request, user: CurrentUser, db: DB,
                       background: BackgroundTasks) -> RefreshStarted:
    fetcher = request.app.state.characters
    if fetcher is None:
        raise HTTPException(503, "Charakterprofile sind ausgeschaltet")
    row = await db.scalar(select(RunCharacter).where(RunCharacter.run_id == run_id, RunCharacter.id == char_id))
    if row is None:
        raise HTTPException(404, "Spieler nicht in diesem Run")
    if row.status != "ok" or not has_item_ids(row.data):
        raise HTTPException(409, "Für diese Momentaufnahme nicht möglich (zu alt oder nicht geladen)")
    if char_id in fetcher.loading:
        raise HTTPException(409, "Wird gerade geladen")
    if time.monotonic() - _details.get(char_id, -REFRESH_EVERY) < REFRESH_EVERY:
        raise HTTPException(429, "Höchstens alle 10 Minuten")
    _details[char_id] = time.monotonic()
    row.data = {**row.data, "details": {"state": "laden"}}
    await db.commit()
    background.add_task(fetcher.details, row.id)
    return RefreshStarted(started=1)
