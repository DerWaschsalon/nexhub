"""Datenbankverbindung und Migrationen."""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


def alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.attributes["database_url"] = database_url
    return cfg


def migrate(database_url: str) -> None:
    """Datenbank auf den neuesten Stand bringen (läuft vor dem Start des Webservers)."""
    command.upgrade(alembic_config(database_url), "head")


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as db:
        yield db
