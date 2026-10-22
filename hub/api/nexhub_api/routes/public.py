"""Öffentlicher Bereich: alles hier ist ohne Login erreichbar.

Nur herausgeben, was geteilt werden darf:
    GET /api/public/info            ist der Login eingerichtet? Wer betreibt den Hub (Impressum)?
    GET /api/public/runs/{token}    ein geteilter Run (Teilen-Link /r/<token>)
    GET /api/public/runs/{token}/fights/{kampf}   ein Kampf daraus im Detail
    GET /api/public/vergleich/{token}?lang=de     ein geteilter Vergleich (Teilen-Link /v/<token>)
    GET /api/public/check/{token}                 ein geteilter Build-Check (Teilen-Link /c/<token>)

Geteilte Runs zeigen Eckdaten und Zusammenfassung mit den Namen der Mitspieler, aber kein
Discord-Konto und nicht die Rohdatei. Geteilte Vergleiche zeigen beide Charaktere, aber nicht, wer
eingetragen oder geteilt hat. Suchmaschinen sollen beides nicht aufnehmen.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from nexproto import dungeon_label

from ..deps import DB, SettingsDep
from ..models import BuildCheck, Comparison, Run
from .armory import ComparisonOut, SharedCheck, load_comparison, load_shared_check
from .runs import load_fight_detail

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
    return Info(login=settings.discord_configured, operator=settings.operator, hoster=settings.hub_hoster.strip() or None)


class SharedRun(BaseModel):
    dungeon: str
    difficulty: str | None
    start_ms: int
    end_ms: int
    complete: bool
    bosses_total: int
    bosses_killed: int
    fights: int
    hits: int
    character: str | None
    summary: dict


def _not_for_search_engines(response: Response) -> None:
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"


async def _shared(db: DB, token: str, response: Response) -> Run:
    run = await db.scalar(select(Run).where(Run.share_token == token)) if len(token) <= 32 else None
    if run is None:
        raise HTTPException(404, "Link ungültig oder zurückgezogen")
    _not_for_search_engines(response)
    return run


@router.get("/runs/{token}/fights/{fight_id}")
async def shared_fight(token: str, fight_id: str, db: DB, settings: SettingsDep, response: Response) -> dict:
    return await load_fight_detail(settings, await _shared(db, token, response), fight_id)


@router.get("/runs/{token}")
async def shared_run(token: str, db: DB, response: Response) -> SharedRun:
    run = await _shared(db, token, response)
    return SharedRun(dungeon=dungeon_label(run.dungeon_id, run.dungeon), difficulty=run.difficulty, start_ms=run.start_ms, end_ms=run.end_ms,
                     complete=run.complete, bosses_total=run.bosses_total, bosses_killed=run.bosses_killed,
                     fights=run.fights, hits=run.hits, character=run.character, summary=run.summary)


@router.get("/vergleich/{token}")
async def shared_comparison(token: str, request: Request, db: DB, response: Response,
                            lang: str = "en") -> ComparisonOut:
    row = await db.scalar(select(Comparison).where(Comparison.token == token)) if len(token) <= 32 else None
    if row is None:
        raise HTTPException(404, "Link ungültig oder zurückgezogen")
    _not_for_search_engines(response)
    return await load_comparison(request, db, row, lang)


@router.get("/check/{token}")
async def shared_check(token: str, db: DB, response: Response) -> SharedCheck:
    check = await db.scalar(select(BuildCheck).where(BuildCheck.share_token == token)) if len(token) <= 32 else None
    if check is None or check.result is None:
        raise HTTPException(404, "Link ungültig oder zurückgezogen")
    _not_for_search_engines(response)
    return await load_shared_check(db, check)
