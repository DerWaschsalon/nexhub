"""Verwaltung: Konten und Systemzustand. Jede Route hier verlangt die Admin-Rolle."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select, text

from ..deps import DB, AdminUser, SettingsDep, require_admin
from ..models import Session, User

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class AccountOut(BaseModel):
    id: int
    discord_id: str
    name: str
    avatar_url: str | None
    role: str
    created_at: datetime
    last_login_at: datetime
    blocked: bool
    sessions: int  # gerade gültige Anmeldungen


class Status(BaseModel):
    version: str
    db_revision: str
    login: bool
    member_check: bool
    accounts: int
    active_sessions: int


@router.get("/users")
async def list_users(db: DB) -> list[AccountOut]:
    active = and_(Session.user_id == User.id, Session.expires_at > datetime.now(UTC))
    rows = await db.execute(
        select(User, func.count(Session.token_hash)).outerjoin(Session, active)
        .group_by(User.id).order_by(User.last_login_at.desc()))
    return [AccountOut(id=u.id, discord_id=str(u.discord_id), name=u.name, avatar_url=u.avatar_url,
                       role=u.role, created_at=u.created_at, last_login_at=u.last_login_at,
                       blocked=u.blocked_at is not None, sessions=n)
            for u, n in rows.all()]


async def _get_user(db: DB, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Konto nicht gefunden")
    return user


@router.post("/users/{user_id}/logout", status_code=204)
async def logout_user(user_id: int, db: DB) -> Response:
    """Alle Sitzungen eines Kontos beenden (z. B. verlorenes Gerät)."""
    await _get_user(db, user_id)
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.commit()
    return Response(status_code=204)


@router.post("/users/{user_id}/block", status_code=204)
async def block_user(user_id: int, db: DB, admin: AdminUser) -> Response:
    user = await _get_user(db, user_id)
    # Admins stehen in der Server-Konfiguration; sie hier zu sperren würde nur verwirren
    if user.role == "admin" or user.id == admin.id:
        raise HTTPException(400, "Admins lassen sich nicht sperren")
    user.blocked_at = datetime.now(UTC)
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.commit()
    return Response(status_code=204)


@router.post("/users/{user_id}/unblock", status_code=204)
async def unblock_user(user_id: int, db: DB) -> Response:
    user = await _get_user(db, user_id)
    user.blocked_at = None
    await db.commit()
    return Response(status_code=204)


@router.get("/status")
async def status(db: DB, settings: SettingsDep) -> Status:
    now = datetime.now(UTC)
    return Status(
        version=settings.hub_version,
        db_revision=await db.scalar(text("SELECT version_num FROM alembic_version")) or "?",
        login=settings.discord_configured,
        member_check=settings.member_check,
        accounts=await db.scalar(select(func.count()).select_from(User)) or 0,
        active_sessions=await db.scalar(
            select(func.count()).select_from(Session).where(Session.expires_at > now)) or 0,
    )
