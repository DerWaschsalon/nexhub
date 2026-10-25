"""Datenbanktabellen. Änderungen immer mit Alembic-Migration (nexhub_api/migrations/versions)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
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
    # Geteilt: wer den Link /r/<share_token> kennt, sieht den Run ohne Login. None = nicht geteilt
    share_token: Mapped[str | None] = mapped_column(String(32), unique=True)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))



class Snapshot:
    """Momentaufnahme eines Charakters von der AION-2-Website, gefüllt von characters.fill().
    Gemeinsam für Mitspieler eines Runs (RunCharacter) und die Armory (Character).

    status: offen, ok, nicht_gefunden, name_maskiert, fehler. `data` ist das Format aus aion2.py."""

    name: Mapped[str] = mapped_column(String(64))
    cls: Mapped[str | None] = mapped_column(String(32))
    server_id: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), index=True)
    nc_character_id: Mapped[str | None] = mapped_column(String(128))
    combat_power: Mapped[int | None] = mapped_column(BigInteger)
    item_level: Mapped[int | None] = mapped_column(Integer)
    data: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(200))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunCharacter(Snapshot, Base):
    """Ein Mitspieler, so wie er zur Zeit des Runs aussah (characters.py)."""

    __tablename__ = "run_characters"
    __table_args__ = (UniqueConstraint("run_id", "name"),)

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)


class Character(Snapshot, Base):
    """Ein Charakter in der Armory: eingetragen von einem Konto, täglich neu abgerufen (armory.py).
    Jeder Charakter gehört höchstens einem Konto."""

    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("server_id", "nc_character_id"),)

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CharacterDay(Base):
    """Verlauf in der Armory: je Charakter und Tag Kampfkraft und Item-Level des letzten Abrufs."""

    __tablename__ = "character_days"
    __table_args__ = (UniqueConstraint("character_id", "day"),)

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    combat_power: Mapped[int | None] = mapped_column(BigInteger)
    item_level: Mapped[int | None] = mapped_column(Integer)


class Comparison(Base):
    """Geteilter Vergleich: wer den Link /v/<token> kennt, sieht ihn ohne Login. Gespeichert ist nur, wer
    mit wem verglichen wird; die Werte holt der Hub beim Öffnen (der rechte live von der Website)."""

    __tablename__ = "comparisons"

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    token: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    left_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    right_server_id: Mapped[int] = mapped_column(Integer)
    right_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BuildCheck(Base):
    """Letzter Build-Check eines Armory-Charakters (buildcheck.py). `result` ist die Auswertung aus
    evaluation.py, ohne Namen der Top-Spieler. Geteilt: wer /c/<share_token> kennt, sieht ihn ohne Login."""

    __tablename__ = "build_checks"

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(16))  # läuft, fertig, fehler
    progress: Mapped[int] = mapped_column(Integer, default=0)  # Profile der Gruppe schon geholt
    error: Mapped[str | None] = mapped_column(String(200))
    result: Mapped[dict | None] = mapped_column(JSON)
    share_token: Mapped[str | None] = mapped_column(String(32), unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
