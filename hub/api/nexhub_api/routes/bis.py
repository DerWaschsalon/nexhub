"""BiS-Listen: was die Top-Spieler je Klasse tragen, nur mit Login wie die Armory.

    GET /api/bis                          Klassen mit Bestand: Anzahl, davon Hard, neueste Stichprobe
    GET /api/bis/{cls}?lang=de&tier=Hard  Auswertung einer Klasse (bis_stats.py), wahlweise nur ein Modus

Der Bestand kommt vom Sammler (bis_collector.py); dieselben Spieler zählt census.py für die Armory.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from fastapi import APIRouter, HTTPException
from nexproto.classes import CLASS_KEYS
from pydantic import BaseModel
from sqlalchemy import func, select

from ..aion2 import LANGS, localized
from ..bis_collector import pool
from ..bis_stats import MIN_SAMPLE, aggregate
from ..deps import DB, CurrentUser
from ..models import BisSample

router = APIRouter(prefix="/api/bis", tags=["bis"])

class ClassOut(BaseModel):
    cls: str
    size: int
    hard: int
    newest: datetime


class BisOut(BaseModel):
    cls: str
    size: int
    tiers: dict[str, int]  # Spieler je Modus („Hard“, „Normal“), immer über den ganzen Bestand
    raid: str | None
    oldest: datetime | None
    newest: datetime | None
    min_sample: int
    slots: list[dict]
    skills: list[dict]


@router.get("")
async def classes(user: CurrentUser, db: DB) -> list[ClassOut]:
    rows = await db.execute(select(BisSample.cls, BisSample.tier, func.count(), func.max(BisSample.fetched_at))
                            .group_by(BisSample.cls, BisSample.tier))
    out: dict[str, ClassOut] = {}
    for cls, tier, count, newest in rows:
        entry = out.setdefault(cls, ClassOut(cls=cls, size=0, hard=0, newest=newest))
        entry.size += count
        entry.hard += count if tier == "Hard" else 0
        entry.newest = max(entry.newest, newest)
    return [out[cls] for cls in CLASS_KEYS if cls in out]


@router.get("/{cls}")
async def class_stats(cls: str, user: CurrentUser, db: DB, lang: str = "en", tier: str | None = None) -> BisOut:
    if cls not in CLASS_KEYS or lang not in LANGS:
        raise HTTPException(404)
    samples = await pool(db, cls)
    chosen = [s for s in samples if tier is None or s.tier == tier]
    stats = aggregate([localized(s.data, lang) for s in chosen]) if len(chosen) >= MIN_SAMPLE else {}
    times = [s.fetched_at for s in samples]
    raids = Counter(s.raid for s in samples)
    return BisOut(cls=cls, size=len(chosen), tiers=dict(Counter(s.tier for s in samples)),
                  raid=raids.most_common(1)[0][0] if raids else None,
                  oldest=min(times, default=None), newest=max(times, default=None), min_sample=MIN_SAMPLE,
                  slots=stats.get("slots", []), skills=stats.get("skills", []))
