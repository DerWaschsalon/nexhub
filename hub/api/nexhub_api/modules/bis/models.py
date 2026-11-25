"""Tabellen des Moduls BiS-Listen: Warteschlange und Bestand der Top-Spieler. Änderungen immer mit Alembic-Migration."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...models import Base, BigID


class BisQueue(Base):
    """Warteschlange der BiS-Listen (bis/collector.py): Namen aus den Ranglisten von Abyss Logs, die noch
    abgerufen werden. Der Name steht nur hier und nur bis zum Abruf."""

    __tablename__ = "bis_queue"

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    cls: Mapped[str] = mapped_column(String(32))
    player_name: Mapped[str] = mapped_column(String(64))
    raid: Mapped[str] = mapped_column(String(128))
    tier: Mapped[str] = mapped_column(String(16))  # „Hard“ oder „Normal“
    rank: Mapped[int] = mapped_column(Integer, index=True)  # Platz in der Klasse, mischt die Klassen beim Abruf
    combat_power: Mapped[int | None] = mapped_column(BigInteger)
    tries: Mapped[int] = mapped_column(Integer, default=0)


class BisSample(Base):
    """Ein Top-Spieler im Bestand der BiS-Listen: Ausrüstung und Skills in beiden Sprachen (FORMAT von
    aion2.py). Ohne Namen; `character_key` ist ein SHA-256 aus Server und Charakter-ID, damit niemand doppelt
    zählt. Die Zählung für die Bewertung der Armory (census.py) rechnet aus demselben Bestand."""

    __tablename__ = "bis_samples"

    id: Mapped[int] = mapped_column(BigID, primary_key=True)
    cls: Mapped[str] = mapped_column(String(32), index=True)
    character_key: Mapped[str] = mapped_column(String(64), unique=True)
    raid: Mapped[str] = mapped_column(String(128))
    tier: Mapped[str] = mapped_column(String(16))
    combat_power: Mapped[int | None] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSON)
