"""Bausteine für Routen: Einstellungen, Datenbank und wer angemeldet ist.

In einer Route reicht ein Parameter mit dem passenden Typ:
    async def seite(user: CurrentUser, db: DB): ...   # nur Angemeldete
    async def verwalten(admin: AdminUser): ...         # nur Admins
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
from .models import Session, User

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


CurrentUser = Annotated[User, Depends(require_user)]
AdminUser = Annotated[User, Depends(require_admin)]
