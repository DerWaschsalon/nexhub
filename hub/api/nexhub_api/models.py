"""Datenbanktabellen. Änderungen immer mit Alembic-Migration (nexhub_api/migrations/versions)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# SQLite (Tests) vergibt automatische IDs nur für INTEGER PRIMARY KEY
BigID = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class User(Base):
    """Ein Discord-Konto, das sich mindestens einmal angemeldet hat."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(64))
    avatar: Mapped[str | None] = mapped_column(String(64))
    # "admin" oder "member"; wird bei jedem Login neu bestimmt
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Von einem Admin gesperrt: kein Login, bestehende Sitzungen gelten nicht mehr
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def name(self) -> str:
        return self.display_name or self.username

    @property
    def avatar_url(self) -> str | None:
        if not self.avatar:
            return None
        return f"https://cdn.discordapp.com/avatars/{self.discord_id}/{self.avatar}.png?size=128"


class Session(Base):
    """Eine Anmeldung im Browser. Der Cookie trägt das Token, hier steht nur sein Hash."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
