"""Statistik für Admins über alle Module: Runs, Konten, Geräte, Armory, Bestand der BiS-Listen.

    GET /api/admin/stats?days=30
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from ...db import aware
from ...deps import DB, require_admin
from ...models import Device, User
from ..armory.models import Character, ClassCensus
from ..bis.models import BisSample
from ..logs.models import Run
from .days import last_days, per_day

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class ClassPool(BaseModel):
    cls: str
    players: int  # Top-Spieler im Bestand der BiS-Listen
    counted_at: datetime | None  # letzte Zählung für die Bewertung; None: noch keine


class Stats(BaseModel):
    days: list[date]  # der älteste zuerst; die Reihen darunter haben einen Wert je Tag
    runs: list[int]  # hochgeladene Runs
    accounts: list[int]  # neue Konten
    total_runs: int
    total_accounts: int
    characters: int  # Charaktere in der Armory
    devices: int  # gekoppelte NexBoards
    devices_active: int  # davon mit Kontakt im Zeitraum
    devices_by_version: dict[str, int]
    bis: list[ClassPool]


async def _stamps(db: DB, column, since: datetime) -> list[datetime]:
    return [aware(stamp) for stamp in (await db.scalars(select(column).where(column >= since))).all()]


async def _count(db: DB, model) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


@router.get("/stats")
async def stats(db: DB, days: int = Query(30, ge=7, le=365)) -> Stats:
    """Nur aus vorhandenen Tabellen gezählt, eine eigene Erfassung gibt es nicht."""
    now = datetime.now(UTC)
    span = last_days(now.date(), days)
    since = now - timedelta(days=days)
    devices = (await db.scalars(select(Device))).all()
    by_version: dict[str, int] = {}
    for device in devices:
        by_version[device.version or "?"] = by_version.get(device.version or "?", 0) + 1
    pools = dict((await db.execute(select(BisSample.cls, func.count()).group_by(BisSample.cls))).all())
    counted = {c.cls: c.fetched_at for c in (await db.scalars(select(ClassCensus))).all()}
    return Stats(
        days=span,
        runs=per_day(await _stamps(db, Run.created_at, since), span),
        accounts=per_day(await _stamps(db, User.created_at, since), span),
        total_runs=await _count(db, Run), total_accounts=await _count(db, User),
        characters=await _count(db, Character), devices=len(devices),
        devices_active=len([d for d in devices if d.last_seen_at and aware(d.last_seen_at) >= since]),
        devices_by_version=by_version,
        bis=[ClassPool(cls=cls, players=players, counted_at=counted.get(cls))
             for cls, players in sorted(pools.items())],
    )
