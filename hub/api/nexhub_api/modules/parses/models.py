"""Tabellen des Moduls Parses: zwischengespeicherte Ranglisten von Abyss Logs und die Legionen der Gilde.
Änderungen immer mit Alembic-Migration."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...models import Base, BigID


class ParseBoard(Base):
    """Rangliste einer Klasse an einem Boss (fetcher.py): nur die DPS-Bestwerte je Spieler, aufsteigend sortiert,
    mit der Kampfkraft dazu, ohne Namen. Leere Liste: Abyss Logs führt für diesen Boss keine Rangliste."""

    __tablename__ = "parse_boards"
    __table_args__ = (UniqueConstraint("boss", "cls", "region"),)

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    boss: Mapped[int] = mapped_column(Integer)  # NPC-ID (mob), bei Abyss Logs mobCode
    cls: Mapped[str] = mapped_column(String(32))  # Hub-Klasse
    region: Mapped[str] = mapped_column(String(8))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total: Mapped[int] = mapped_column(Integer)  # Einträge laut Abyss Logs, vor dem Bestwert je Name
    dps: Mapped[list] = mapped_column(JSON)
    # Kampfkraft zum selben Eintrag wie dps (gleiche Reihenfolge, 0 = unbekannt). None: vor Revision 0018 geladen
    cp: Mapped[list | None] = mapped_column(JSON)


class GuildLegion(Base):
    """Eine Legion, die im Gildenvergleich zählt. Admins pflegen die Liste (routes.py), etwa nach einem
    Wechsel der Legion. Leer: kein Gildenvergleich."""

    __tablename__ = "guild_legions"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
