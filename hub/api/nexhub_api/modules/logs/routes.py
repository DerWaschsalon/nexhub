"""Runs: NexBoards laden fertige Dungeon-Runs hoch, Angemeldete sehen sie sich an.

    POST   /api/runs               Gerät (Bearer): NexLog hochladen (gzip, siehe proto/README.md)
    GET    /api/runs               alle Runs, neueste zuerst (mit Spieler- und Bossnamen zum Suchen);
                                   ?dungeon_id= und ?since_ms= grenzen ein
    GET    /api/runs/dungeons      je Dungeon-ID: Runs, Bestzeit, Kills, Wipes (?since_ms= für Heute/Woche)
    GET    /api/runs/{id}          Eckdaten und Zusammenfassung
    GET    /api/runs/{id}/overview Tode und stärkste Fähigkeiten über alle Bosskämpfe
    GET    /api/runs/{id}/nexlog   die Datei, so wie sie hochgeladen wurde
    GET    /api/runs/{id}/fights/{kampf}   ein Kampf im Detail (DPS-Kurve, Skills, Tode)
    DELETE /api/runs/{id}          wer hochgeladen hat, oder ein Admin
    POST   /api/runs/{id}/share    Teilen-Link erzeugen (gleiche Rechte wie Löschen)
    DELETE /api/runs/{id}/share    Teilen-Link zurückziehen

Alle Angemeldeten (Admins und Mitglieder) sehen alle Runs. Nach außen nur über einen Teilen-Link;
die öffentliche Ansicht dazu steht in routes/public.py.

Nach einem neuen Upload mit besiegtem Boss meldet der Hub den Link an TheWashBot (`tell_bot`), damit der
Discord-Post zum Lauf auf den Run im Hub zeigt.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import FileResponse
from nexproto import NexLogError, dungeon_label, unpack
from nexproto.nexlog import MAX_PACKED
from nexproto.runreport import RunReport
from pydantic import BaseModel
from sqlalchemy import delete, select

from ...bot_client import tell_bot
from ...config import Settings
from ...deps import DB, CurrentDevice, CurrentUser, SettingsDep
from ...models import User
from . import characters
from .analysis import fight_detail, summarize
from .models import Run, RunCharacter

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
                 response: Response, background: BackgroundTasks) -> Uploaded:
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
    if request.app.state.characters is not None:
        try:
            await characters.create(db, run.id, nexlog)
            background.add_task(request.app.state.characters.run, run.id)
        except Exception:  # der Run ist gespeichert; ohne Profile ist er trotzdem gültig
            await db.rollback()
            log.exception("Run %d: Charakterprofile nicht angelegt", run.id)
    url = f"{settings.hub_base_url}/hub/runs/{run.id}"
    if settings.bot_configured and r.bosses_killed:
        # Für NexBoards, die den Run noch selbst an den Bot schicken; neue melden ihn über /report
        background.add_task(tell_bot, request.app.state.http, settings, "run-link",
                            {"dungeon": r.dungeon, "start_ms": r.start_ms, "url": url})
    return Uploaded(id=run.id, url=url, duplicate=False)


class Forwarded(BaseModel):
    forwarded: bool  # False: der Hub hat keinen Bot oder keinen Discord-Server eingerichtet


@router.post("/{run_id}/report", status_code=202)
async def report(run_id: int, body: RunReport, request: Request, device: CurrentDevice, db: DB,
                 settings: SettingsDep, background: BackgroundTasks) -> Forwarded:
    """Run-Bericht eines hochgeladenen Runs → Discord-Post des Bots, mit Link zum Run im Hub. Einziger Weg
    vom NexBoard nach Discord (Umbau-Konzept: Daemon → Hub → Bot)."""
    run = await db.get(Run, run_id)
    if run is None or run.user_id != device.user_id:
        raise HTTPException(404, "Run nicht gefunden")
    if not settings.bot_configured or settings.hub_guild_id is None:
        return Forwarded(forwarded=False)
    payload = {"guild_id": settings.hub_guild_id, "report": body.model_dump(),
               "url": f"{settings.hub_base_url}/hub/runs/{run.id}"}
    background.add_task(tell_bot, request.app.state.http, settings, "run", payload)
    return Forwarded(forwarded=True)


class RunOut(BaseModel):
    id: int
    dungeon_id: int
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
    players: list[str]  # Namen aus der Zusammenfassung, für Suche und Filter der Liste
    classes: list[str | None]  # Klasse zu players, gleiche Reihenfolge
    bosses: list[str]
    results: list[bool]  # je Bosskampf: getötet


class RunDetail(RunOut):
    size: int
    can_delete: bool  # darf löschen und teilen
    share_url: str | None
    summary: dict


def _out(run: Run, uploader: User) -> dict:
    return dict(id=run.id, dungeon_id=run.dungeon_id, dungeon=dungeon_label(run.dungeon_id, run.dungeon),
                difficulty=run.difficulty,
                start_ms=run.start_ms, end_ms=run.end_ms, complete=run.complete, bosses_total=run.bosses_total,
                bosses_killed=run.bosses_killed, fights=run.fights, hits=run.hits, character=run.character,
                uploader=uploader.name, created_at=run.created_at,
                players=[p["name"] for p in run.summary.get("players", [])],
                classes=[p.get("cls") for p in run.summary.get("players", [])],
                bosses=[b["name"] for b in run.summary.get("bosses", [])],
                results=[bool(b.get("killed")) for b in run.summary.get("bosses", [])])


@router.get("")
async def list_runs(user: CurrentUser, db: DB, limit: int = 100, dungeon_id: int | None = None,
                    since_ms: int | None = None) -> list[RunOut]:
    query = select(Run, User).join(User, User.id == Run.user_id)
    if dungeon_id is not None:
        query = query.where(Run.dungeon_id == dungeon_id)
    if since_ms is not None:
        query = query.where(Run.start_ms >= since_ms)
    rows = await db.execute(query.order_by(Run.start_ms.desc()).limit(min(max(limit, 1), 500)))
    return [RunOut(**_out(run, uploader)) for run, uploader in rows.all()]


class DungeonStat(BaseModel):
    """Ein Dungeon in einer Schwierigkeit (AION 2 gibt jeder Schwierigkeit eine eigene ID)."""
    dungeon_id: int
    dungeon: str
    difficulty: str | None
    runs: int
    complete: int
    fastest_ms: int | None  # schnellster vollständiger Run
    kills: int
    wipes: int
    players: int  # verschiedene Spielernamen
    last_ms: int  # Beginn des neuesten Runs


@router.get("/dungeons")
async def list_dungeons(user: CurrentUser, db: DB, since_ms: int | None = None) -> list[DungeonStat]:
    """Kennzahlen je Dungeon-ID für die Übersicht, neuester zuerst. Liest nur Eckdaten und Zusammenfassungen."""
    query = select(Run.dungeon_id, Run.dungeon, Run.difficulty, Run.start_ms, Run.end_ms, Run.complete, Run.summary)
    if since_ms is not None:
        query = query.where(Run.start_ms >= since_ms)
    stats: dict[int, dict] = {}
    names: dict[int, set[str]] = {}
    for dungeon_id, dungeon, difficulty, start, end, complete, summary in (await db.execute(query)).all():
        s = stats.setdefault(dungeon_id, dict(dungeon_id=dungeon_id, dungeon=dungeon_label(dungeon_id, dungeon),
                                              difficulty=difficulty, runs=0, complete=0, fastest_ms=None,
                                              kills=0, wipes=0, players=0, last_ms=start))
        s["runs"] += 1
        s["difficulty"] = s["difficulty"] or difficulty
        s["last_ms"] = max(s["last_ms"], start)
        if complete:
            s["complete"] += 1
            s["fastest_ms"] = min(s["fastest_ms"] or end - start, end - start)
        for b in summary.get("bosses", []):
            s["kills" if b.get("killed") else "wipes"] += 1
        names.setdefault(dungeon_id, set()).update(p["name"] for p in summary.get("players", []))
    for dungeon_id, s in stats.items():
        s["players"] = len(names[dungeon_id])
    return [DungeonStat(**s) for s in sorted(stats.values(), key=lambda s: -s["last_ms"])]


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


class RunDeath(BaseModel):
    fight: str
    boss: str
    name: str
    cls: str | None
    t_ms: int  # seit Kampfbeginn
    revived_ms: int | None
    skill: int | None  # Ursache vom Radar im NexBoard


class RunSkill(BaseModel):
    code: int | None
    name: str
    player: str
    cls: str | None
    damage: int
    hits: int


class RunOverview(BaseModel):
    deaths: list[RunDeath]
    skills: list[RunSkill]  # stärkste Fähigkeiten über alle Bosskämpfe, je Spieler und Fähigkeit


OVERVIEW_SKILLS = 10


@router.get("/{run_id}/overview")
async def run_overview(run_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> RunOverview:
    """Für die Zusammenfassung eines Runs: liest jeden Bosskampf aus der Datei."""
    run, _ = await _get(db, run_id)
    deaths: list[RunDeath] = []
    skills: dict[tuple[str, str], RunSkill] = {}
    for boss in run.summary.get("bosses", []):
        try:
            detail = await load_fight_detail(settings, run, boss["fight"])
        except HTTPException:
            continue
        classes = {p["name"]: p.get("cls") for p in detail["players"]}
        for d in detail.get("deaths") or []:
            deaths.append(RunDeath(fight=boss["fight"], boss=boss["name"], name=d["name"], cls=classes.get(d["name"]),
                                   t_ms=d["t_ms"], revived_ms=d.get("revived_ms"), skill=d.get("skill")))
        for p in detail["players"]:
            for sk in p.get("skills") or []:
                key = (p["name"], sk["name"])
                got = skills.get(key)
                if got is None:
                    skills[key] = RunSkill(code=sk.get("code"), name=sk["name"], player=p["name"], cls=p.get("cls"),
                                           damage=sk["damage"], hits=sk["hits"])
                else:
                    got.damage += sk["damage"]
                    got.hits += sk["hits"]
    top = sorted(skills.values(), key=lambda s: -s.damage)[:OVERVIEW_SKILLS]
    return RunOverview(deaths=deaths, skills=top)


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


async def load_fight_detail(settings: Settings, run: Run, fight_id: str) -> dict:
    """Kampf-Details aus der abgelegten Datei; dazu die Reihenfolge der Spieler im ganzen Run,
    damit jeder Spieler in allen Kämpfen dieselbe Farbe bekommt."""
    def work() -> dict | None:
        nexlog = unpack(run_file(settings, run.id).read_bytes())
        fight = next((f for f in nexlog.fights if f.id == fight_id), None)
        return fight_detail(nexlog, fight) if fight else None

    detail = await asyncio.to_thread(work)
    if detail is None:
        raise HTTPException(404, "Kampf nicht in diesem Run")
    detail["run_players"] = [p["name"] for p in run.summary.get("players", [])]
    return detail


@router.get("/{run_id}/fights/{fight_id}")
async def get_fight(run_id: int, fight_id: str, user: CurrentUser, db: DB, settings: SettingsDep) -> dict:
    run, _ = await _get(db, run_id)
    return await load_fight_detail(settings, run, fight_id)


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
    # SQLite (Tests) kennt kein ON DELETE CASCADE ohne PRAGMA; Postgres löscht ohnehin mit
    await db.execute(delete(RunCharacter).where(RunCharacter.run_id == run_id))
    await db.delete(run)
    await db.commit()
    run_file(settings, run_id).unlink(missing_ok=True)
    return Response(status_code=204)
