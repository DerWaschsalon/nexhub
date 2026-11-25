"""Öffentlicher Bereich des Kerns, ohne Login:

    GET /api/public/info            ist der Login eingerichtet? Wer betreibt den Hub (Impressum)?

Was Module öffentlich zeigen (geteilte Runs und Vergleiche, Termine), steht in ihren shared_routes.py bzw.
routes.py, ebenfalls unter /api/public.
"""
from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from ..deps import SettingsDep

router = APIRouter(prefix="/api/public", tags=["öffentlich"])


class Operator(BaseModel):
    name: str
    address: list[str]
    email: str | None


class Info(BaseModel):
    login: bool  # ist der Discord-Login eingerichtet?
    operator: Operator | None  # Impressum, aus HUB_OPERATOR_* in .env
    hoster: str | None


@router.get("/info")
async def info(settings: SettingsDep) -> Info:
    return Info(login=settings.discord_configured, operator=settings.operator,
                hoster=settings.hub_hoster.strip() or None)


def not_for_search_engines(response: Response) -> None:
    """Für geteilte Seiten der Module: nicht aufnehmen, nicht zwischenspeichern."""
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"
