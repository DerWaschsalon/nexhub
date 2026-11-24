"""Regeln der Bewertung und des Upgrade-Plans als Zahlen, für die Seite „Wie wir bewerten“.

    GET /api/rating/rules   nur mit Login

Die Seite erklärt die Rechnung in Worten; die Zahlen dazu stehen nur im Code (rating.py, upgrades.py,
bis_collector.py) und kommen von hier, damit die Erklärung nicht veraltet.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..abysslogs import REGION
from ..bis_collector import POOL_SIZE
from ..deps import CurrentUser
from ..rating import BOUNDS
from ..upgrades import DEFAULT_GOAL, GOALS, MAX_REROLLS, TIER_BEST, TIER_GOOD

router = APIRouter(prefix="/api/rating", tags=["armory"])


class Bound(BaseModel):
    letter: str
    low: float  # Note ab diesem Anteil am besten Stück, in Prozent


class Rules(BaseModel):
    bounds: list[Bound]  # von der besten Note abwärts
    region: str
    pool_size: int  # so viele Top-Spieler je Klasse höchstens
    goals: list[str]
    default_goal: str
    max_rerolls: int
    tier_best: float  # Stufen der Ziele: Anteil am Zugewinn des besten Ziels
    tier_good: float


@router.get("/rules")
async def rules(user: CurrentUser) -> Rules:
    return Rules(bounds=[Bound(letter=letter, low=low) for letter, low in BOUNDS], region=REGION.upper(),
                 pool_size=POOL_SIZE, goals=list(GOALS), default_goal=DEFAULT_GOAL, max_rerolls=MAX_REROLLS,
                 tier_best=TIER_BEST, tier_good=TIER_GOOD)
