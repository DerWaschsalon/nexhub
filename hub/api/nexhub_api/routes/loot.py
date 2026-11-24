"""Beute: Dropraten je Boss aus der Würfel-Beute der hochgeladenen Runs (loot.py), nur mit Login.

    GET /api/loot   Dungeons mit ihren Bossen und Gegenständen

Gerechnet wird beim Aufruf aus den Zusammenfassungen der Runs; es sind wenige hundert Zeilen.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import DB, CurrentUser
from ..loot import MIN_KILLS, table
from ..models import Run

router = APIRouter(prefix="/api/loot", tags=["runs"])


class Item(BaseModel):
    item_id: int
    drops: int  # Siege, bei denen der Gegenstand zum Würfeln stand
    kills: int
    one_in: float | None  # None: zu wenig Siege für eine Rate
    one_in_low: float | None
    one_in_high: float | None


class Boss(BaseModel):
    mob: int
    name: str
    kills: int
    items: list[Item]


class Dungeon(BaseModel):
    dungeon_id: int
    dungeon: str
    difficulty: str | None
    runs: int  # Runs, deren Aufnahme Beute meldet
    bosses: list[Boss]


class Loot(BaseModel):
    min_kills: int
    dungeons: list[Dungeon]


@router.get("")
async def loot(user: CurrentUser, db: DB) -> Loot:
    rows = (await db.execute(select(Run.dungeon_id, Run.dungeon, Run.difficulty, Run.summary)
                             .order_by(Run.start_ms))).all()
    by_dungeon: dict[int, list] = {}
    for row in rows:
        if row.summary.get("loot_tracked"):
            by_dungeon.setdefault(row.dungeon_id, []).append(row)
    dungeons = [Dungeon(dungeon_id=dungeon_id, dungeon=runs[-1].dungeon, difficulty=runs[-1].difficulty,
                        runs=len(runs), bosses=[Boss(**b) for b in table([r.summary for r in runs])])
                for dungeon_id, runs in by_dungeon.items()]
    return Loot(min_kills=MIN_KILLS, dungeons=sorted(dungeons, key=lambda d: d.dungeon))
