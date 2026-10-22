"""Armory: Charaktere eintragen und ansehen, nur mit Login. Alle Angemeldeten sehen alle Charaktere.

    GET    /api/armory/search?name=…&region=eu   Charaktere auf der AION-2-Website suchen
    GET    /api/armory                           alle eingetragenen Charaktere, ohne die Daten
    POST   /api/armory                           eigenen Charakter eintragen (Treffer aus der Suche)
    GET    /api/armory/{id}                      Momentaufnahme und Verlauf
    DELETE /api/armory/{id}                      austragen (wer eingetragen hat oder ein Admin)
    POST   /api/armory/{id}/refresh              jetzt neu abrufen (alle, höchstens alle 10 Minuten)

Abruf und Format wie bei den Mitspielern eines Runs (characters.py, routes/characters.py).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import defer

from ..aion2 import NC, NCError, NotFound, shard_of
from ..armory import Armory
from ..deps import DB, CurrentUser
from ..models import Character, CharacterDay, User
from .characters import CharacterOut, _out

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
PROFILE_COLUMNS = [Character.data["profile"][key].as_string() for key in PROFILE.values()]


def _armory_out(row: Character, owner: User, user: User, profile: dict) -> dict:
    return dict(**_out(row), owner=owner.name, mine=row.user_id == user.id, **profile)


def _profile_of(row: Character) -> dict:
    p = (row.data or {}).get("profile") or {}
    return {out: p.get(key) for out, key in PROFILE.items()}


async def _get(db: DB, character_id: int) -> tuple[Character, User]:
    found = (await db.execute(select(Character, User).join(User, User.id == Character.user_id)
                              .where(Character.id == character_id))).first()
    if found is None:
        raise HTTPException(404, "Charakter nicht in der Armory")
    return found[0], found[1]


@router.get("/search")
async def search(name: str, request: Request, user: CurrentUser, db: DB, region: str = "eu") -> list[Hit]:
    name = name.strip()
    if len(name) < 2:
        raise HTTPException(422, "Mindestens zwei Zeichen")
    try:
        hits = await _nc(request).search(name, region)
    except NotFound as e:
        raise HTTPException(422, str(e)) from e
    except NCError as e:
        raise HTTPException(502, f"AION-2-Website: {e}") from e
    ids = [h["character_id"] for h in hits]
    taken = {(server, cid): owner.name for server, cid, owner in (await db.execute(
        select(Character.server_id, Character.nc_character_id, User).join(User, User.id == Character.user_id)
        .where(Character.nc_character_id.in_(ids)))).all()} if ids else {}
    return [Hit(**h, taken_by=taken.get((h["server_id"], h["character_id"]))) for h in hits]


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
    if row.user_id != user.id and user.role != "admin":
        raise HTTPException(403, "Nur wer eingetragen hat, oder ein Admin")
    # ausdrücklich, weil SQLite (Tests) ON DELETE CASCADE ohne PRAGMA foreign_keys nicht ausführt
    await db.execute(delete(CharacterDay).where(CharacterDay.character_id == row.id))
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
    if row.fetched_at and datetime.now(UTC) - row.fetched_at.replace(tzinfo=row.fetched_at.tzinfo or UTC) < REFRESH_EVERY:
        raise HTTPException(429, "Höchstens alle 10 Minuten")
    row.status = "offen"
    await db.commit()
    background.add_task(armory.refresh, row.id)
    return Started(started=True)
