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


class DungeonInfo(Base):
    """Name, Schwierigkeit und Art eines Dungeons laut Abyss Logs (extras.py). Die Runs zeigen sie statt der
    Angaben aus der Aufnahme (state.dungeon_info), solange Abyss Logs die ID kennt."""

    __tablename__ = "dungeon_info"

    dungeon_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tier: Mapped[str | None] = mapped_column(String(60))
    category: Mapped[str | None] = mapped_column(String(60))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ParseBenchmark(Base):
    """DPS-Verteilung der letzten Woche an einem Boss je Klasse und Kampfkraft-Stufe (Abyss Logs /statistics,
    Felder wie abysslogs.STAT_FIELDS). Vergleichswert im Kampfbericht neben dem EU-Parse."""

    __tablename__ = "parse_benchmarks"

    boss: Mapped[int] = mapped_column(Integer, primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cells: Mapped[list] = mapped_column(JSON)
