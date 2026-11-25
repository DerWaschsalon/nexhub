"""Tabellen des Moduls Logs: hochgeladene Runs und die Momentaufnahmen ihrer Mitspieler.
Änderungen immer mit Alembic-Migration."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ...models import Base, BigID

# erlaubte Werte von RunCharacter.status und Character.status (in der Datenbank Text)
CharacterStatus = Literal["offen", "ok", "nicht_gefunden", "name_maskiert", "fehler"]


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
