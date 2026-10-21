"""Öffentlicher Bereich: alles hier ist ohne Login erreichbar.

Nur herausgeben, was geteilt werden darf. Geteilte Runs kommen später als eigene Route dazu
(z. B. GET /api/public/runs/{freigabe}), sobald es Runs gibt.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..deps import SettingsDep

router = APIRouter(prefix="/api/public", tags=["öffentlich"])


class Info(BaseModel):
    login: bool  # ist der Discord-Login eingerichtet?


@router.get("/info")
async def info(settings: SettingsDep) -> Info:
    return Info(login=settings.discord_configured)
