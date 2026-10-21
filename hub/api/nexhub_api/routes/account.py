"""Das eigene Konto."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..deps import CurrentUser

router = APIRouter(prefix="/api/me", tags=["konto"])


class Me(BaseModel):
    # Discord-IDs als Text: als Zahl verlieren sie in JavaScript die letzten Stellen
    discord_id: str
    name: str
    avatar_url: str | None
    role: str


@router.get("")
async def me(user: CurrentUser) -> Me:
    return Me(discord_id=str(user.discord_id), name=user.name, avatar_url=user.avatar_url, role=user.role)
