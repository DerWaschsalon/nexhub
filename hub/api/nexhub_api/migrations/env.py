"""Alembic-Umgebung: asynchron, URL aus db.alembic_config() oder DATABASE_URL."""
from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from nexhub_api.models import Base

config = context.config
url = config.attributes.get("database_url") or os.environ["DATABASE_URL"]


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


asyncio.run(_main())
