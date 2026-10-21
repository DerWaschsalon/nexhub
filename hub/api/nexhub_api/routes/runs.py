"""Runs: NexBoards laden fertige Dungeon-Runs hoch, Angemeldete sehen sie sich an.

    POST   /api/runs               Gerät (Bearer): NexLog hochladen (gzip, siehe proto/README.md)
    GET    /api/runs               alle Runs, neueste zuerst
    GET    /api/runs/{id}          Eckdaten und Zusammenfassung
    GET    /api/runs/{id}/nexlog   die Datei, so wie sie hochgeladen wurde
    DELETE /api/runs/{id}          wer hochgeladen hat, oder ein Admin
    POST   /api/runs/{id}/share    Teilen-Link erzeugen (gleiche Rechte wie Löschen)
    DELETE /api/runs/{id}/share    Teilen-Link zurückziehen

Alle Angemeldeten (Admins und Mitglieder) sehen alle Runs. Nach außen nur über einen Teilen-Link;
die öffentliche Ansicht dazu steht in routes/public.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from nexproto import NexLogError, unpack
from nexproto.nexlog import MAX_PACKED

from ..analysis import summarize
from ..config import Settings
from ..deps import DB, CurrentDevice, CurrentUser, SettingsDep
from ..models import Run, User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])


def run_file(settings: Settings, run_id: int) -> Path:
    return settings.hub_data_dir / "runs" / f"{run_id}.nexlog.gz"


async def _read_body(request: Request) -> bytes:
    """Body mit Obergrenze lesen: nicht erst alles annehmen und dann ablehnen."""
    if int(request.headers.get("content-length") or 0) > MAX_PACKED:
        raise HTTPException(413, "Datei zu groß")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_PACKED:
            raise HTTPException(413, "Datei zu groß")
    return bytes(data)


class Uploaded(BaseModel):
    id: int
    url: str
    duplicate: bool


@router.post("", status_code=201)
async def upload(request: Request, device: CurrentDevice, db: DB, settings: SettingsDep,
                 response: Response) -> Uploaded:
    data = await _read_body(request)
    digest = hashlib.sha256(data).hexdigest()
    existing = await db.scalar(select(Run).where(Run.user_id == device.user_id, Run.sha256 == digest))
    if existing:
        response.status_code = 200
        return Uploaded(id=existing.id, url=f"{settings.hub_base_url}/hub/runs/{existing.id}", duplicate=True)
    try:
        # Entpacken und Prüfen kostet bei großen Runs einige zehn ms: nicht in der Event-Loop
        nexlog = await asyncio.to_thread(unpack, data)
        summary = await asyncio.to_thread(summarize, nexlog)
    except NexLogError as e:
        raise HTTPException(422, str(e)) from None

    r = nexlog.run
    run = Run(user_id=device.user_id, device_id=device.id, sha256=digest, size=len(data),
              dungeon_id=r.dungeon_id, dungeon=r.dungeon, difficulty=r.difficulty, start_ms=r.start_ms,
              end_ms=r.end_ms, complete=r.complete, bosses_total=r.bosses_total, bosses_killed=r.bosses_killed,
              fights=len(nexlog.fights), hits=sum(len(h.rows) for h in nexlog.hits.values()),
              character=nexlog.you.name if nexlog.you else None, summary=summary)
    db.add(run)
    await db.flush()  # vergibt die ID für den Dateinamen
    path = run_file(settings, run.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    await db.commit()
    log.info("Run %d: %s von Gerät %d (%d Kämpfe, %d KB)", run.id, r.dungeon, device.id, run.fights, len(data) // 1024)
    return Uploaded(id=run.id, url=f"{settings.hub_base_url}/hub/runs/{run.id}", duplicate=False)


class RunOut(BaseModel):
    id: int
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
    uploader: str
    created_at: datetime


class RunDetail(RunOut):
    size: int
    can_delete: bool  # darf löschen und teilen
    share_url: str | None
    summary: dict


def _out(run: Run, uploader: User) -> dict:
    return dict(id=run.id, dungeon=run.dungeon, difficulty=run.difficulty, start_ms=run.start_ms,
                end_ms=run.end_ms, complete=run.complete, bosses_total=run.bosses_total,
                bosses_killed=run.bosses_killed, fights=run.fights, hits=run.hits, character=run.character,
                uploader=uploader.name, created_at=run.created_at)


@router.get("")
async def list_runs(user: CurrentUser, db: DB, limit: int = 100) -> list[RunOut]:
    rows = await db.execute(select(Run, User).join(User, User.id == Run.user_id)
                            .order_by(Run.start_ms.desc()).limit(min(max(limit, 1), 500)))
    return [RunOut(**_out(run, uploader)) for run, uploader in rows.all()]


async def _get(db: DB, run_id: int) -> tuple[Run, User]:
    row = (await db.execute(select(Run, User).join(User, User.id == Run.user_id).where(Run.id == run_id))).first()
    if row is None:
        raise HTTPException(404, "Run nicht gefunden")
    return row[0], row[1]


def share_url(settings: Settings, run: Run) -> str | None:
    return f"{settings.hub_base_url}/r/{run.share_token}" if run.share_token else None


def _may_manage(run: Run, user: User) -> bool:
    return run.user_id == user.id or user.role == "admin"


@router.get("/{run_id}")
async def get_run(run_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> RunDetail:
    run, uploader = await _get(db, run_id)
    return RunDetail(**_out(run, uploader), size=run.size, summary=run.summary,
                     can_delete=_may_manage(run, user), share_url=share_url(settings, run))


class Shared(BaseModel):
    share_url: str | None


@router.post("/{run_id}/share")
async def share(run_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> Shared:
    """Teilen-Link erzeugen; ist schon einer da, bleibt er (zurückziehen und neu erzeugen gibt einen neuen)."""
    run, _ = await _get(db, run_id)
    if not _may_manage(run, user):
        raise HTTPException(403, "Nur wer hochgeladen hat, oder ein Admin")
    if not run.share_token:
        run.share_token, run.shared_at = secrets.token_urlsafe(16), datetime.now(UTC)
        await db.commit()
        log.info("Run %d geteilt von %s", run.id, user.username)
    return Shared(share_url=share_url(settings, run))


@router.delete("/{run_id}/share")
async def unshare(run_id: int, user: CurrentUser, db: DB) -> Shared:
    run, _ = await _get(db, run_id)
    if not _may_manage(run, user):
        raise HTTPException(403, "Nur wer hochgeladen hat, oder ein Admin")
    run.share_token = run.shared_at = None
    await db.commit()
    return Shared(share_url=None)


@router.get("/{run_id}/nexlog")
async def download(run_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> FileResponse:
    run, _ = await _get(db, run_id)
    return FileResponse(run_file(settings, run.id), media_type="application/gzip",
                        filename=f"run-{run.id}.nexlog.json.gz")


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> Response:
    run, _ = await _get(db, run_id)
    if not _may_manage(run, user):
        raise HTTPException(403, "Nur wer hochgeladen hat, oder ein Admin")
    await db.delete(run)
    await db.commit()
    run_file(settings, run_id).unlink(missing_ok=True)
    return Response(status_code=204)
