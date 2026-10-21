"""Datenbanktabellen. Änderungen immer mit Alembic-Migration (nexhub_api/migrations/versions)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
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


class Device(Base):
    """Ein gekoppeltes NexBoard (Daemon auf einem PC). Gehört genau einem Konto."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    # SHA-256 des Geräte-Tokens; das Token kennt nur der Daemon
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[str | None] = mapped_column(String(40))  # NexBoard-Version beim letzten Kontakt


class DevicePairing(Base):
    """Ein laufender Kopplungsversuch (RFC 8628): der Daemon fragt mit `device_code` nach,
    bis jemand im Hub den kurzen `user_code` bestätigt hat. Nach 10 Minuten verfallen."""

    __tablename__ = "device_pairings"

    device_code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_code: Mapped[str] = mapped_column(String(8), unique=True)  # ohne Bindestrich gespeichert
    client_name: Mapped[str] = mapped_column(String(64))  # Vorschlag des Daemons
    client_version: Mapped[str | None] = mapped_column(String(40))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Gesetzt, sobald ein Konto den Code bestätigt hat
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_name: Mapped[str | None] = mapped_column(String(64))


class Run(Base):
    """Ein hochgeladener Dungeon-Run. Die Datei (NexLog) liegt unverändert unter
    `<HUB_DATA_DIR>/runs/<id>.nexlog.gz`; hier stehen Eckdaten und eine Zusammenfassung."""

    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("user_id", "sha256"),)  # dieselbe Datei nur einmal je Konto

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)  # Bytes, gepackt
    dungeon_id: Mapped[int] = mapped_column(Integer)
    dungeon: Mapped[str] = mapped_column(String(120))
    difficulty: Mapped[str | None] = mapped_column(String(40))
    start_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    end_ms: Mapped[int] = mapped_column(BigInteger)
    complete: Mapped[bool] = mapped_column(Boolean)
    bosses_total: Mapped[int] = mapped_column(Integer)
    bosses_killed: Mapped[int] = mapped_column(Integer)
    fights: Mapped[int] = mapped_column(Integer)
    hits: Mapped[int] = mapped_column(Integer)
    character: Mapped[str | None] = mapped_column(String(64))  # wer aufgenommen hat
    summary: Mapped[dict] = mapped_column(JSON)  # analysis.summarize()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

