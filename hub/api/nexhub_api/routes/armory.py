"""Armory: Charaktere eintragen und ansehen, nur mit Login. Alle Angemeldeten sehen alle Charaktere.

    GET    /api/armory/search?name=…&region=eu   Charaktere auf der AION-2-Website suchen
    GET    /api/armory                           alle eingetragenen Charaktere, ohne die Daten
    POST   /api/armory                           eigenen Charakter eintragen (Treffer aus der Suche)
    GET    /api/armory/{id}                      Momentaufnahme und Verlauf
    DELETE /api/armory/{id}                      austragen (wer eingetragen hat oder ein Admin)
    POST   /api/armory/{id}/refresh              jetzt neu abrufen (alle, höchstens alle 10 Minuten)
    POST   /api/armory/compare/share             Teilen-Link für einen Vergleich (öffentlich unter /v/<token>)
    POST   /api/armory/{id}/check                Build-Check starten (gegen die Top-Spieler, buildcheck.py)
    GET    /api/armory/{id}/check                letzter Build-Check: Stand, Fortschritt, Ergebnis
    POST   /api/armory/{id}/check/share          Teilen-Link (öffentlich unter /c/<token>); DELETE zieht zurück
    DELETE /api/armory/compare/share/{token}     Teilen-Link zurückziehen (wer geteilt hat, oder ein Admin)

Abruf und Format wie bei den Mitspielern eines Runs (characters.py, routes/characters.py).
"""
from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import defer

from ..aion2 import LANGS, NC, NCError, NotFound, localized, shard_of
from ..armory import Armory
from ..buildcheck import STALE, BuildChecker, aware
from ..config import Settings
from ..deps import DB, CurrentUser, SettingsDep
from ..models import BuildCheck, Character, CharacterDay, Comparison, User
from .characters import CharacterOut, _out
from .runs import Shared

router = APIRouter(prefix="/api/armory", tags=["armory"])

REFRESH_EVERY = timedelta(minutes=10)
PER_USER = 20


class ArmoryOut(CharacterOut):
    owner: str
    mine: bool
    # Aus dem Profil (PROFILE). Den Klassennamen schreibt die Website aus; die Web-Oberfläche leitet
    # daraus Farbe und Symbol ab (modules/logs/classes.ts), damit die Klassentabelle nur dort steht
    class_name: str | None
    server: str | None
    image: str | None


class Day(BaseModel):
    day: date
    combat_power: int | None
    item_level: int | None


class ArmoryDetail(ArmoryOut):
    data: dict | None
    error: str | None
    days: list[Day]
    can_delete: bool


class Hit(BaseModel):
    name: str
    server_id: int
    server: str | None
    level: int | None
    cls: str | None  # Klasse wie im Hub ("ranger")
    character_id: str
    image: str | None
    taken_by: str | None  # schon eingetragen, von wem


class NewCharacter(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    server_id: int
    character_id: str = Field(min_length=1, max_length=128)


def _armory(request: Request) -> Armory:
    armory = request.app.state.armory
    if armory is None:
        raise HTTPException(503, "Charakterprofile sind ausgeschaltet")
    return armory


def _nc(request: Request) -> NC:
    return _armory(request).nc


# Felder der Liste aus dem Profil: Ausgabename → Schlüssel in data["profile"] (aion2.py). In der
# Liste direkt aus dem JSON gelesen, damit sie die Daten (~75 KB je Charakter) nicht laden muss.
PROFILE = {"class_name": "class", "server": "server", "image": "image"}
# Ab FORMAT 2 je Sprache (aion2.py); Klasse, Server und Bild nehmen wir aus der englischen
PROFILE_COLUMNS = [func.coalesce(Character.data["en"]["profile"][key].as_string(),
                                 Character.data["profile"][key].as_string()) for key in PROFILE.values()]


def _armory_out(row: Character, owner: User, user: User, profile: dict) -> dict:
    return dict(**_out(row), owner=owner.name, mine=row.user_id == user.id, **profile)


def _profile_of(row: Character) -> dict:
    p = localized(row.data or {}).get("profile") or {}
    return {out: p.get(key) for out, key in PROFILE.items()}


async def _get(db: DB, character_id: int) -> tuple[Character, User]:
    found = (await db.execute(select(Character, User).join(User, User.id == Character.user_id)
                              .where(Character.id == character_id))).first()
    if found is None:
        raise HTTPException(404, "Charakter nicht in der Armory")
    return found[0], found[1]


@router.get("/search")
async def search(name: str, request: Request, user: CurrentUser, db: DB, region: str = "eu",
                 cls: str | None = None) -> list[Hit]:
    name = name.strip()
    if len(name) < 2:
        raise HTTPException(422, "Mindestens zwei Zeichen")
    try:
        hits = await _nc(request).search(name, region, cls)
    except NotFound as e:
        raise HTTPException(422, str(e)) from e
    except NCError as e:
        raise HTTPException(502, f"AION-2-Website: {e}") from e
    ids = [h["character_id"] for h in hits]
    taken = {(server, cid): owner.name for server, cid, owner in (await db.execute(
        select(Character.server_id, Character.nc_character_id, User).join(User, User.id == Character.user_id)
        .where(Character.nc_character_id.in_(ids)))).all()} if ids else {}
    return [Hit(**h, taken_by=taken.get((h["server_id"], h["character_id"]))) for h in hits]


class Live(BaseModel):
    name: str
    server_id: int
    data: dict  # eine Sprache, Format aus aion2.py; die Klasse steht in data["profile"]["class"]


async def fetch_live(request: Request, name: str, server_id: int, lang: str) -> Live:
    """Beliebigen Charakter jetzt von der Website holen, zum Vergleichen. Wird nicht gespeichert,
    damit sich keine Daten fremder Charaktere ansammeln."""
    nc = _nc(request)
    try:
        character_id = await nc.find(name.strip(), server_id)
        data = await nc.snapshot(server_id, character_id, lang if lang in LANGS else "en")
    except NotFound as e:
        raise HTTPException(404, f"Charakter {e}") from e
    except NCError as e:
        raise HTTPException(502, f"AION-2-Website: {e}") from e
    return Live(name=(data.get("profile") or {}).get("name") or name, server_id=server_id, data=data)


@router.get("/live")
async def live(name: str, server_id: int, request: Request, user: CurrentUser, lang: str = "en") -> Live:
    return await fetch_live(request, name, server_id, lang)


class CompareShare(BaseModel):
    left: int  # Charakter aus der Armory
    server_id: int  # rechts: Server und Name wie in der Adresse der Vergleichsseite
    name: str = Field(min_length=1, max_length=64)


class Side(BaseModel):
    """Linke Seite eines geteilten Vergleichs: nur, was die Ansicht braucht, nicht wer eingetragen hat."""
    name: str
    cls: str | None
    class_name: str | None
    data: dict | None


class ComparisonOut(BaseModel):
    left: Side
    right: Live | None
    right_error: str | None  # rechts nicht gefunden oder Website weg; links steht trotzdem da


def comparison_url(settings: Settings, row: Comparison) -> str:
    return f"{settings.hub_base_url}/v/{row.token}"


async def load_comparison(request: Request, db: DB, row: Comparison, lang: str) -> ComparisonOut:
    """Einen geteilten Vergleich laden: links aus der Armory, rechts live von der Website."""
    left, _ = await _get(db, row.left_id)
    side = Side(name=left.name, cls=left.cls, class_name=_profile_of(left)["class_name"], data=left.data)
    try:
        return ComparisonOut(left=side, right=await fetch_live(request, row.right_name, row.right_server_id, lang),
                             right_error=None)
    except HTTPException as e:
        if e.status_code == 503:  # Charakterprofile ausgeschaltet: die ganze Seite geht nicht
            raise
        return ComparisonOut(left=side, right=None, right_error=e.detail)


@router.post("/compare/share")
async def share_comparison(body: CompareShare, user: CurrentUser, db: DB, settings: SettingsDep) -> Shared:
    """Teilen-Link erzeugen; teilt dasselbe Konto denselben Vergleich noch einmal, bleibt es beim Link."""
    await _get(db, body.left)
    if shard_of(body.server_id) is None:
        raise HTTPException(422, "Server nicht unterstützt")
    name = body.name.strip()
    row = await db.scalar(select(Comparison).where(
        Comparison.user_id == user.id, Comparison.left_id == body.left,
        Comparison.right_server_id == body.server_id, Comparison.right_name == name))
    if row is None:
        row = Comparison(token=secrets.token_urlsafe(16), user_id=user.id, left_id=body.left,
                         right_server_id=body.server_id, right_name=name)
        db.add(row)
        await db.commit()
    return Shared(share_url=comparison_url(settings, row))


@router.delete("/compare/share/{token}")
async def unshare_comparison(token: str, user: CurrentUser, db: DB) -> Shared:
    row = await db.scalar(select(Comparison).where(Comparison.token == token))
    if row is None:
        raise HTTPException(404, "Link ungültig oder schon zurückgezogen")
    if row.user_id != user.id and user.role != "admin":
        raise HTTPException(403, "Nur wer geteilt hat, oder ein Admin")
    await db.delete(row)
    await db.commit()
    return Shared(share_url=None)


@router.get("")
async def list_characters(user: CurrentUser, db: DB) -> list[ArmoryOut]:
    found = await db.execute(select(Character, User, *PROFILE_COLUMNS).join(User, User.id == Character.user_id)
                             .options(defer(Character.data))
                             .order_by(Character.combat_power.desc().nulls_last(), Character.name))
    return [ArmoryOut(**_armory_out(row, owner, user, dict(zip(PROFILE, values))))
            for row, owner, *values in found.all()]


@router.post("", status_code=201)
async def add(body: NewCharacter, request: Request, user: CurrentUser, db: DB,
              background: BackgroundTasks) -> ArmoryOut:
    armory = _armory(request)
    if shard_of(body.server_id) is None:
        raise HTTPException(422, "Server nicht unterstützt")
    owner = await db.scalar(select(User).join(Character, Character.user_id == User.id).where(
        Character.server_id == body.server_id, Character.nc_character_id == body.character_id))
    if owner is not None:
        raise HTTPException(409, f"Schon eingetragen von {owner.name}")
    if await db.scalar(select(func.count()).select_from(Character).where(Character.user_id == user.id)) >= PER_USER:
        raise HTTPException(422, f"Höchstens {PER_USER} Charaktere je Konto")
    row = Character(user_id=user.id, name=body.name.strip(), server_id=body.server_id,
                    nc_character_id=body.character_id, status="offen")
    db.add(row)
    await db.commit()
    background.add_task(armory.refresh, row.id)
    return ArmoryOut(**_armory_out(row, user, user, _profile_of(row)))


@router.get("/{character_id}")
async def get_character(character_id: int, user: CurrentUser, db: DB) -> ArmoryDetail:
    row, owner = await _get(db, character_id)
    days = await db.scalars(select(CharacterDay).where(CharacterDay.character_id == row.id).order_by(CharacterDay.day))
    return ArmoryDetail(**_armory_out(row, owner, user, _profile_of(row)),
                        data=row.data, error=row.error,
                        days=[Day(day=d.day, combat_power=d.combat_power, item_level=d.item_level) for d in days],
                        can_delete=row.user_id == user.id or user.role == "admin")


@router.delete("/{character_id}", status_code=204)
async def remove(character_id: int, user: CurrentUser, db: DB) -> None:
    row, _ = await _get(db, character_id)
    if not _may_manage(row, user):
        raise HTTPException(403, "Nur wer eingetragen hat, oder ein Admin")
    # ausdrücklich, weil SQLite (Tests) ON DELETE CASCADE ohne PRAGMA foreign_keys nicht ausführt
    await db.execute(delete(CharacterDay).where(CharacterDay.character_id == row.id))
    await db.execute(delete(Comparison).where(Comparison.left_id == row.id))
    await db.execute(delete(BuildCheck).where(BuildCheck.character_id == row.id))
    await db.delete(row)
    await db.commit()


class Started(BaseModel):
    started: bool


@router.post("/{character_id}/refresh", status_code=202)
async def refresh(character_id: int, request: Request, user: CurrentUser, db: DB,
                  background: BackgroundTasks) -> Started:
    armory = _armory(request)
    row, _ = await _get(db, character_id)
    if row.status == "offen" or character_id in armory.running:
        raise HTTPException(409, "Wird gerade abgerufen")
    last = aware(row.fetched_at) if row.fetched_at else None
    if last and datetime.now(UTC) - last < REFRESH_EVERY:
        raise HTTPException(429, "Höchstens alle 10 Minuten")
    row.status = "offen"
    await db.commit()
    background.add_task(armory.refresh, row.id)
    return Started(started=True)


def _checker(request: Request) -> BuildChecker:
    _armory(request)  # gleiche Meldung, wenn Charakterprofile ausgeschaltet sind
    return request.app.state.buildcheck


def _may_manage(row: Character, user: User) -> bool:
    return row.user_id == user.id or user.role == "admin"


class CheckOut(BaseModel):
    status: str  # läuft, fertig, fehler
    progress: int
    size: int | None  # so viele Top-Spieler im Ergebnis
    error: str | None
    result: dict | None
    started_at: datetime
    finished_at: datetime | None
    share_url: str | None


def check_url(settings: Settings, check: BuildCheck) -> str | None:
    return f"{settings.hub_base_url}/c/{check.share_token}" if check.share_token else None


async def _check(db: DB, character_id: int) -> BuildCheck:
    check = await db.scalar(select(BuildCheck).where(BuildCheck.character_id == character_id))
    if check is None:
        raise HTTPException(404, "Noch kein Build-Check")
    return check


@router.post("/{character_id}/check", status_code=202)
async def start_check(character_id: int, request: Request, user: CurrentUser, db: DB,
                      background: BackgroundTasks) -> Started:
    checker = _checker(request)
    row, _ = await _get(db, character_id)
    if not row.data:
        raise HTTPException(422, "Der Charakter hat noch keine Daten von der AION-2-Website, erst abrufen")
    check = await db.scalar(select(BuildCheck).where(BuildCheck.character_id == character_id))
    now = datetime.now(UTC)
    if check is None:
        check = BuildCheck(character_id=character_id)
        db.add(check)
    elif check.status == "läuft" and now - aware(check.started_at) < STALE:
        raise HTTPException(409, "Build-Check läuft gerade")
    elif check.status != "läuft" and now - aware(check.started_at) < REFRESH_EVERY:
        raise HTTPException(429, "Höchstens alle 10 Minuten")
    check.status, check.progress, check.error, check.started_at = "läuft", 0, None, now
    await db.commit()
    background.add_task(checker.run, character_id)
    return Started(started=True)


@router.get("/{character_id}/check")
async def get_check(character_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> CheckOut:
    check = await _check(db, character_id)
    status, error = check.status, check.error
    if status == "läuft" and datetime.now(UTC) - aware(check.started_at) >= STALE:
        # ein Neustart des Hubs hat den Lauf beendet; als Fehler gemeldet, damit „Neu prüfen“ erscheint
        status, error = "fehler", "Build-Check abgebrochen (Hub neu gestartet), bitte neu starten"
    return CheckOut(status=status, progress=check.progress, size=(check.result or {}).get("size"),
                    error=error, result=check.result, started_at=check.started_at,
                    finished_at=check.finished_at, share_url=check_url(settings, check))


@router.post("/{character_id}/check/share")
async def share_check(character_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> Shared:
    """Teilen-Link erzeugen; ist schon einer da, bleibt er. Gleiche Rechte wie Austragen."""
    row, _ = await _get(db, character_id)
    if not _may_manage(row, user):
        raise HTTPException(403, "Nur wer eingetragen hat, oder ein Admin")
    check = await _check(db, character_id)
    if check.result is None:
        raise HTTPException(409, "Noch kein Ergebnis")
    if not check.share_token:
        check.share_token = secrets.token_urlsafe(16)
        await db.commit()
    return Shared(share_url=check_url(settings, check))


@router.delete("/{character_id}/check/share")
async def unshare_check(character_id: int, user: CurrentUser, db: DB) -> Shared:
    row, _ = await _get(db, character_id)
    if not _may_manage(row, user):
        raise HTTPException(403, "Nur wer eingetragen hat, oder ein Admin")
    check = await _check(db, character_id)
    check.share_token = None
    await db.commit()
    return Shared(share_url=None)


class SharedCheck(Side):
    result: dict
    finished_at: datetime | None


async def load_shared_check(db: DB, check: BuildCheck) -> SharedCheck:
    """Geteilter Build-Check: der Charakter wie im Vergleich (ohne wer eingetragen hat) und das Ergebnis."""
    row, _ = await _get(db, check.character_id)
    return SharedCheck(name=row.name, cls=row.cls, class_name=_profile_of(row)["class_name"], data=row.data,
                       result=check.result or {}, finished_at=check.finished_at)
