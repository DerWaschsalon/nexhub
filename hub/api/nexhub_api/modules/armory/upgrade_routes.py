"""Upgrade-Plan eines Armory-Charakters: welche Teile man in welcher Reihenfolge neu würfelt (upgrades.py).

    GET /api/armory/{id}/upgrades?goal=S%2B&lang=de   nur mit Login, wie die Armory selbst
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ...deps import DB, CurrentUser
from .routes import character_or_404, rating_inputs
from .upgrades import DEFAULT_GOAL, plan

router = APIRouter(prefix="/api/armory", tags=["armory"])

Goal = Literal["S+", "BiS"]
Lang = Literal["en", "de"]


class Piece(BaseModel):
    slot: str
    name: str | None
    icon: str | None
    grade: str | None
    score: float | None  # None: ohne Würfeltabelle gibt es keine Note
    letter: str | None


class Unreachable(Piece):
    reason: Literal["no_rolls", "too_far"]


class Target(BaseModel):
    name: str
    gain_lo: float
    gain_hi: float


class Step(BaseModel):
    line: str
    chance: float  # Prozent je Versuch
    tries: float  # Versuche im Mittel
    skill_only: bool
    tiers: dict[Literal["best", "good", "fine"], list[Target]]


class Card(Piece):
    steps: list[Step]
    after: tuple[float, float]  # Note bei Pech und bei Glück
    mean: float
    after_letter: str
    tries: float
    per_try: float  # Notenpunkte je Versuch, danach ist sortiert


class UpgradePlan(BaseModel):
    goal: Goal
    group: str
    cards: list[Card]
    bind: list[Piece]
    done: list[Piece]
    unreachable: list[Unreachable]
    arcana: list[Piece]


@router.get("/{character_id}/upgrades")
async def upgrades(character_id: int, user: CurrentUser, db: DB, goal: Goal = DEFAULT_GOAL,
                   lang: Lang = "en") -> UpgradePlan | None:
    """None, solange es für die Klasse keine Zählung gibt (wie `ratings` in der Armory)."""
    row, _ = await character_or_404(db, character_id)
    inputs = await rating_inputs(db, row)
    return UpgradePlan(**plan(*inputs, lang, goal)) if inputs else None
