"""Tabellen des Moduls Armory: eingetragene Charaktere, ihr Verlauf, geteilte Vergleiche und die Daten
ihrer Bewertung.
Änderungen immer mit Alembic-Migration."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ...models import Base, BigID
from ..logs.models import Snapshot


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


class ClassCensus(Base):
    """Zählung der Top-Spieler einer Klasse (census.py): je Platz, wie viele welche Zeile der
    Seelenbindung tragen, und der größte Wert je Zeile (rating.count_players/add_tops). Keine Namen."""

    __tablename__ = "class_census"

    cls: Mapped[str] = mapped_column(String(32), primary_key=True)
    group_label: Mapped[str] = mapped_column(String(300))  # woher die Spieler stammen („Raid · Hard“)
    data: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ItemRolls(Base):
    """Würfeltabelle eines Gegenstands von MetaBot.GG (metabot.py), je englischem Namen; `data` leer,
    wenn MetaBot den Gegenstand nicht kennt (dann erst nach einer Woche neu fragen)."""

    __tablename__ = "item_rolls"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    data: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
