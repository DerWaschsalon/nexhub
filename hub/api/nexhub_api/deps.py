"""Bausteine für Routen: Einstellungen, Datenbank und wer angemeldet ist.

In einer Route reicht ein Parameter mit dem passenden Typ:
    async def seite(user: CurrentUser, db: DB): ...   # nur Angemeldete
    async def verwalten(admin: AdminUser): ...         # nur Admins
    async def hochladen(device: CurrentDevice): ...   # gekoppeltes NexBoard (Bearer-Token)
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .db import get_db
from .discord import Discord
from .models import Device, Session, User

SESSION_COOKIE = "nexhub_session"


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_discord(request: Request) -> Discord:
    return Discord(request.app.state.settings, request.app.state.http)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


SettingsDep = Annotated[Settings, Depends(get_settings)]
DB = Annotated[AsyncSession, Depends(get_db)]
DiscordDep = Annotated[Discord, Depends(get_discord)]


async def current_user(request: Request, db: DB) -> User | None:
    """Konto zum Sitzungscookie, solange die Sitzung gilt und das Konto nicht gesperrt ist."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return await db.scalar(
        select(User).join(Session, Session.user_id == User.id)
        .where(Session.token_hash == hash_token(token), Session.expires_at > datetime.now(UTC),
               User.blocked_at.is_(None)))


async def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
    if user is None:
        raise HTTPException(401, "Nicht angemeldet")
    return user


async def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Nur für Admins")
    return user


async def require_device(request: Request, db: DB) -> Device:
    """Gerät zum Token in `Authorization: Bearer …`; merkt sich Zeit und Version des Kontakts.

    Gehört das Gerät zu einem gesperrten Konto, gilt das Token nicht mehr."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Geräte-Token fehlt", headers={"WWW-Authenticate": "Bearer"})
    device = await db.scalar(
        select(Device).join(User, User.id == Device.user_id)
        .where(Device.token_hash == hash_token(token), User.blocked_at.is_(None)))
    if device is None:
        raise HTTPException(401, "Gerät unbekannt oder entfernt", headers={"WWW-Authenticate": "Bearer"})
    device.last_seen_at = datetime.now(UTC)
    device.version = request.headers.get("x-nexboard-version", device.version or "")[:40] or None
    await db.commit()
    return device


CurrentUser = Annotated[User, Depends(require_user)]
AdminUser = Annotated[User, Depends(require_admin)]
CurrentDevice = Annotated[Device, Depends(require_device)]
