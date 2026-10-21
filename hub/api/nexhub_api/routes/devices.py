"""Geräte: NexBoards per Code koppeln (RFC 8628, „Device Authorization Grant“) und verwalten.

Ablauf:
  1. Daemon: POST /api/devices/pair → geheimer `device_code`, kurzer `user_code` (BCDF-GHJK) und
     die Adresse der Geräte-Seite. Der Daemon zeigt Code und Link an.
  2. Mensch: im Hub unter /hub/geraete den Code bestätigen (POST /api/devices/pair/approve).
  3. Daemon fragt alle `interval` Sekunden nach (POST /api/devices/pair/poll). Nach der Bestätigung
     bekommt er einmalig sein Geräte-Token und meldet sich ab dann mit `Authorization: Bearer …`.

Das Token steht nur im Daemon; der Hub speichert seinen Hash. Entfernen im Hub macht es ungültig.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from ..deps import DB, CurrentDevice, CurrentUser, SettingsDep, hash_token
from ..models import Device, DevicePairing, User

router = APIRouter(prefix="/api/devices", tags=["geräte"])

# Keine Vokale (ergibt keine Wörter), nichts Verwechselbares wie 0/O oder 1/I
ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"
PAIRING_TTL_S = 600
POLL_INTERVAL_S = 5
# Kopplung starten geht ohne Login; mehr offene Versuche nimmt der Hub nicht an
MAX_OPEN_PAIRINGS = 50


def _random_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(8))


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def normalize_code(text: str) -> str:
    """Eingabe des Menschen → gespeicherte Form: Großbuchstaben, ohne Bindestrich und Leerzeichen."""
    return "".join(c for c in text.upper() if c in ALPHABET)


# ---------------------------------------------------------------- Daemon: koppeln

class PairStart(BaseModel):
    name: str = Field("NexBoard", min_length=1, max_length=64)  # Namensvorschlag fürs Gerät
    version: str | None = Field(None, max_length=40)


class PairStarted(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@router.post("/pair")
async def pair_start(body: PairStart, db: DB, settings: SettingsDep) -> PairStarted:
    now = datetime.now(UTC)
    await db.execute(delete(DevicePairing).where(DevicePairing.expires_at < now))
    if (await db.scalar(select(func.count()).select_from(DevicePairing)) or 0) >= MAX_OPEN_PAIRINGS:
        raise HTTPException(429, "Zu viele offene Kopplungen, bitte später noch einmal")
    taken = set(await db.scalars(select(DevicePairing.user_code)))
    user_code = _random_code()
    while user_code in taken:  # bei höchstens 50 offenen Codes praktisch nie
        user_code = _random_code()
    device_code = secrets.token_urlsafe(32)
    db.add(DevicePairing(device_code_hash=hash_token(device_code), user_code=user_code,
                         client_name=body.name.strip(), client_version=body.version,
                         expires_at=now + timedelta(seconds=PAIRING_TTL_S)))
    await db.commit()
    page = f"{settings.hub_base_url}/hub/geraete"
    return PairStarted(device_code=device_code, user_code=format_code(user_code), verification_uri=page,
                       verification_uri_complete=f"{page}?code={format_code(user_code)}",
                       expires_in=PAIRING_TTL_S, interval=POLL_INTERVAL_S)


class PairPoll(BaseModel):
    device_code: str = Field(max_length=100)


class PairResult(BaseModel):
    status: Literal["pending", "approved"]
    token: str | None = None  # nur einmal, bei "approved"
    device_id: int | None = None
    device_name: str | None = None


@router.post("/pair/poll")
async def pair_poll(body: PairPoll, db: DB) -> PairResult:
    pairing = await db.get(DevicePairing, hash_token(body.device_code))
    if pairing is None or _aware(pairing.expires_at) < datetime.now(UTC):
        raise HTTPException(410, "Kopplung abgelaufen oder unbekannt")
    if pairing.approved_by is None:
        return PairResult(status="pending")
    token = secrets.token_urlsafe(32)
    device = Device(user_id=pairing.approved_by, name=pairing.device_name or pairing.client_name,
                    token_hash=hash_token(token), version=pairing.client_version)
    db.add(device)
    await db.delete(pairing)
    await db.commit()
    return PairResult(status="approved", token=token, device_id=device.id, device_name=device.name)


def _aware(dt: datetime) -> datetime:
    # SQLite (Tests) liefert Zeiten ohne Zeitzone zurück
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------- Mensch: bestätigen, verwalten

class PairApprove(BaseModel):
    code: str = Field(max_length=20)
    name: str | None = Field(None, max_length=64)


class Approved(BaseModel):
    name: str


@router.post("/pair/approve")
async def pair_approve(body: PairApprove, user: CurrentUser, db: DB) -> Approved:
    pairing = await db.scalar(select(DevicePairing).where(
        DevicePairing.user_code == normalize_code(body.code), DevicePairing.approved_by.is_(None),
        DevicePairing.expires_at > datetime.now(UTC)))
    if pairing is None:
        raise HTTPException(404, "Code unbekannt oder abgelaufen")
    pairing.approved_by = user.id
    pairing.device_name = (body.name or "").strip() or pairing.client_name
    await db.commit()
    return Approved(name=pairing.device_name)


class DeviceOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_seen_at: datetime | None
    version: str | None


def _out(d: Device) -> DeviceOut:
    return DeviceOut(id=d.id, name=d.name, created_at=d.created_at, last_seen_at=d.last_seen_at, version=d.version)


@router.get("")
async def my_devices(user: CurrentUser, db: DB) -> list[DeviceOut]:
    rows = await db.scalars(select(Device).where(Device.user_id == user.id).order_by(Device.created_at))
    return [_out(d) for d in rows]


# ---------------------------------------------------------------- Gerät: wer bin ich, abkoppeln
# Vor /{device_id}, damit "me" nicht als ID gelesen wird

class DeviceSelf(BaseModel):
    id: int
    name: str
    owner: str  # Anzeigename des Kontos


@router.get("/me")
async def device_me(device: CurrentDevice, db: DB) -> DeviceSelf:
    owner = await db.get(User, device.user_id)
    return DeviceSelf(id=device.id, name=device.name, owner=owner.name if owner else "?")


@router.delete("/me", status_code=204)
async def device_unpair(device: CurrentDevice, db: DB) -> Response:
    """Der Daemon koppelt sich selbst ab (Knopf „Abkoppeln“ in NexBoard)."""
    await db.delete(device)
    await db.commit()
    return Response(status_code=204)


@router.delete("/{device_id}", status_code=204)
async def remove_device(device_id: int, user: CurrentUser, db: DB) -> Response:
    """Eigenes Gerät entfernen; Admins dürfen jedes. Sein Token gilt danach nicht mehr."""
    device = await db.get(Device, device_id)
    if device is None or (device.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Gerät nicht gefunden")
    await db.delete(device)
    await db.commit()
    return Response(status_code=204)
