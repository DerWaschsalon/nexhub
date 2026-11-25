"""Geteilte Vergleiche, ohne Login erreichbar (Teilen-Link /v/<token>):

    GET /api/public/vergleich/{token}?lang=de

Gezeigt werden beide Charaktere, aber nicht, wer eingetragen oder geteilt hat.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from ...deps import DB
from ...routes.public import not_for_search_engines
from .models import Comparison
from .routes import ComparisonOut, load_comparison

router = APIRouter(prefix="/api/public", tags=["öffentlich"])


@router.get("/vergleich/{token}")
async def shared_comparison(token: str, request: Request, db: DB, response: Response,
                            lang: str = "en") -> ComparisonOut:
    row = await db.scalar(select(Comparison).where(Comparison.token == token)) if len(token) <= 32 else None
    if row is None:
        raise HTTPException(404, "Link ungültig oder zurückgezogen")
    not_for_search_engines(response)
    return await load_comparison(request, db, row, lang)

