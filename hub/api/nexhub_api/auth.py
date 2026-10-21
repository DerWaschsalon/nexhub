"""Login über Discord (Authorization Code + PKCE) und Sitzungen in der Datenbank.

Ablauf: /api/auth/login setzt einen signierten Kurzzeit-Cookie mit state und PKCE-Verifier und
leitet zu Discord. /api/auth/callback prüft beides, legt Konto und Sitzung an und gibt den
Discord-Token sofort zurück. Wer weder Admin noch Mitglied ist, kommt nicht hinein.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .db import get_db
from .discord import Discord, DiscordError, DiscordUser
from .models import Session, User

log = logging.getLogger(__name__)

STATE_COOKIE = "nexhub_oauth"
SESSION_COOKIE = "nexhub_session"
STATE_MAX_AGE = 600

router = APIRouter(prefix="/api/auth")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_discord(request: Request) -> Discord:
    return Discord(request.app.state.settings, request.app.state.http)


SettingsDep = Annotated[Settings, Depends(get_settings)]
DB = Annotated[AsyncSession, Depends(get_db)]


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.hub_secret_key, salt="nexhub-oauth")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def safe_next(target: str | None) -> str:
    """Nur Pfade auf dem Hub selbst, nie fremde Adressen (auch nicht //host oder /\\host)."""
    if not target or not target.startswith("/") or target.startswith(("//", "/\\")):
        return "/"
    return target


def _fail(settings: Settings, code: str, **extra: str) -> RedirectResponse:
    resp = RedirectResponse(f"/?{urlencode({'fehler': code, **extra})}", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/api/auth")
    return resp


@router.get("/login")
async def login(settings: SettingsDep, discord: Annotated[Discord, Depends(get_discord)],
                next: str = "/") -> RedirectResponse:
    if not settings.discord_configured:
        raise HTTPException(503, "Discord-Login ist auf diesem Server noch nicht eingerichtet")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    resp = RedirectResponse(discord.authorize_url(state, challenge), status_code=302)
    resp.set_cookie(STATE_COOKIE, _serializer(settings).dumps({"s": state, "v": verifier, "n": safe_next(next)}),
                    max_age=STATE_MAX_AGE, path="/api/auth", httponly=True,
                    secure=settings.secure_cookies, samesite="lax")
    return resp


async def _role_for(settings: Settings, discord: Discord, token: str, user: DiscordUser) -> str | None:
    if user.id in settings.hub_admin_ids:
        return "admin"
    if settings.member_check:
        roles = await discord.get_member_roles(token, settings.hub_guild_id)
        if roles and settings.hub_member_role_id in roles:
            return "member"
    return None


@router.get("/callback")
async def callback(request: Request, settings: SettingsDep, db: DB,
                   discord: Annotated[Discord, Depends(get_discord)],
                   code: str | None = None, state: str | None = None,
                   error: str | None = None) -> RedirectResponse:
    try:
        saved = _serializer(settings).loads(request.cookies.get(STATE_COOKIE, ""), max_age=STATE_MAX_AGE)
    except BadSignature:
        return _fail(settings, "abgelaufen")
    if error:
        return _fail(settings, "abgebrochen")
    if not code or not state or not secrets.compare_digest(state, saved["s"]):
        return _fail(settings, "ungueltig")

    try:
        token = await discord.exchange_code(code, saved["v"])
        try:
            duser = await discord.get_user(token)
            role = await _role_for(settings, discord, token, duser)
        finally:
            await discord.revoke(token)
    except DiscordError as e:
        log.warning("Login fehlgeschlagen: %s", e)
        return _fail(settings, "discord")

    if role is None:
        log.info("Login abgelehnt: Discord-ID %s ist nicht freigeschaltet", duser.id)
        return _fail(settings, "nicht_freigeschaltet", id=str(duser.id))

    now = datetime.now(UTC)
    user = await db.scalar(select(User).where(User.discord_id == duser.id))
    if user is None:
        user = User(discord_id=duser.id)
        db.add(user)
    user.username, user.display_name, user.avatar = duser.username, duser.global_name, duser.avatar
    user.role, user.last_login_at = role, now
    await db.flush()

    token = secrets.token_urlsafe(32)
    max_age = settings.hub_session_days * 86400
    db.add(Session(token_hash=_hash(token), user_id=user.id, expires_at=now + timedelta(seconds=max_age)))
    await db.execute(delete(Session).where(Session.expires_at < now))
    await db.commit()
    log.info("Login: %s (%s, %s)", duser.username, duser.id, role)

    resp = RedirectResponse(saved["n"], status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/api/auth")
    resp.set_cookie(SESSION_COOKIE, token, max_age=max_age, path="/", httponly=True,
                    secure=settings.secure_cookies, samesite="lax")
    return resp


async def current_user(request: Request, db: DB) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return await db.scalar(
        select(User).join(Session, Session.user_id == User.id)
        .where(Session.token_hash == _hash(token), Session.expires_at > datetime.now(UTC)))


async def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
    if user is None:
        raise HTTPException(401, "Nicht angemeldet")
    return user


def check_origin(request: Request, settings: SettingsDep) -> None:
    """Schutz vor fremden Seiten, die im Namen des Browsers etwas auslösen (CSRF)."""
    if request.headers.get("origin") != settings.origin:
        raise HTTPException(403, "Fremde Herkunft")


@router.post("/logout", status_code=204, dependencies=[Depends(check_origin)])
async def logout(request: Request, db: DB, settings: SettingsDep) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await db.execute(delete(Session).where(Session.token_hash == _hash(token)))
        await db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp
