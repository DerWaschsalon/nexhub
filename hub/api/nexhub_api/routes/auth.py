"""Login über Discord (Authorization Code + PKCE) und Abmelden.

Ablauf: /api/auth/login setzt einen signierten Kurzzeit-Cookie mit state und PKCE-Verifier und
leitet zu Discord. /api/auth/callback prüft beides, legt Konto und Sitzung an und gibt den
Discord-Token sofort zurück. Wer weder Admin noch Mitglied ist, kommt nicht hinein; Fehler
landen als ?fehler=… auf der Login-Seite.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import delete, select

from ..config import Settings
from ..deps import DB, SESSION_COOKIE, DiscordDep, SettingsDep, hash_token
from ..discord import Discord, DiscordError, DiscordUser
from ..models import Session, User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

STATE_COOKIE = "nexhub_oauth"
STATE_MAX_AGE = 600
LOGIN_PAGE = "/login"
DEFAULT_NEXT = "/hub"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.hub_secret_key, salt="nexhub-oauth")


def safe_next(target: str | None) -> str:
    """Nur Pfade auf dem Hub selbst, nie fremde Adressen (auch nicht //host oder /\\host)."""
    if not target or not target.startswith("/") or target.startswith(("//", "/\\")):
        return DEFAULT_NEXT
    return target


def _fail(code: str, **extra: str) -> RedirectResponse:
    resp = RedirectResponse(f"{LOGIN_PAGE}?{urlencode({'fehler': code, **extra})}", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/api/auth")
    return resp


async def _role_for(settings: Settings, discord: Discord, token: str, user: DiscordUser) -> str | None:
    """Admin per ID aus der Konfiguration, Mitglied per Rolle auf dem Discord-Server, sonst None."""
    if user.id in settings.hub_admin_ids:
        return "admin"
    if settings.member_check:
        roles = await discord.get_member_roles(token, settings.hub_guild_id)
        if roles and settings.hub_member_role_id in roles:
            return "member"
    return None


@router.get("/login")
async def login(settings: SettingsDep, discord: DiscordDep, next: str = DEFAULT_NEXT) -> RedirectResponse:
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


@router.get("/callback")
async def callback(request: Request, settings: SettingsDep, db: DB, discord: DiscordDep,
                   code: str | None = None, state: str | None = None,
                   error: str | None = None) -> RedirectResponse:
    try:
        saved = _serializer(settings).loads(request.cookies.get(STATE_COOKIE, ""), max_age=STATE_MAX_AGE)
    except BadSignature:
        return _fail("abgelaufen")
    if error:
        return _fail("abgebrochen")
    if not code or not state or not secrets.compare_digest(state, saved["s"]):
        return _fail("ungueltig")

    try:
        token = await discord.exchange_code(code, saved["v"])
        try:
            duser = await discord.get_user(token)
            role = await _role_for(settings, discord, token, duser)
        finally:
            await discord.revoke(token)
    except DiscordError as e:
        log.warning("Login fehlgeschlagen: %s", e)
        return _fail("discord")

    if role is None:
        log.info("Login abgelehnt: Discord-ID %s ist nicht freigeschaltet", duser.id)
        return _fail("nicht_freigeschaltet", id=str(duser.id))

    user = await db.scalar(select(User).where(User.discord_id == duser.id))
    if user and user.blocked_at:
        log.info("Login abgelehnt: %s ist gesperrt", duser.id)
        return _fail("gesperrt")
    if user is None:
        user = User(discord_id=duser.id)
        db.add(user)
    now = datetime.now(UTC)
    user.username, user.display_name, user.avatar = duser.username, duser.global_name, duser.avatar
    user.role, user.last_login_at = role, now
    await db.flush()

    session_token = secrets.token_urlsafe(32)
    max_age = settings.hub_session_days * 86400
    db.add(Session(token_hash=hash_token(session_token), user_id=user.id,
                   expires_at=now + timedelta(seconds=max_age)))
    # Bei der Gelegenheit abgelaufene Sitzungen aller Konten aufräumen
    await db.execute(delete(Session).where(Session.expires_at < now))
    await db.commit()
    log.info("Login: %s (%s, %s)", duser.username, duser.id, role)

    resp = RedirectResponse(saved["n"], status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/api/auth")
    resp.set_cookie(SESSION_COOKIE, session_token, max_age=max_age, path="/", httponly=True,
                    secure=settings.secure_cookies, samesite="lax")
    return resp


@router.post("/logout", status_code=204)
async def logout(request: Request, db: DB) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await db.execute(delete(Session).where(Session.token_hash == hash_token(token)))
        await db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp
