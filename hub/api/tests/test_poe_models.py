"""Tabellen für Path of Exile: Anlegen per Migration, Eindeutigkeit der Preiszeilen."""
import asyncio
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api.models import PoeItem, PoePrice, PoeWatch, User


def item(**over) -> PoeItem:
    fields = dict(game="poe1", league="Standard", key="divine-orb", name="Divine Orb", category="Currency",
                  price=150.0, unit="chaos", updated_at=datetime.now(timezone.utc))
    return PoeItem(**{**fields, **over})


def test_poe_tables_exist(database_url):
    async def go():
        engine = create_async_engine(database_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            user = User(discord_id=1, username="u1", role="member")
            session.add_all([user, item(), PoePrice(game="poe1", league="Standard", key="divine-orb",
                                                    day=date(2026, 11, 12), price=150.0)])
            await session.commit()
            session.add(PoeWatch(user_id=user.id, game="poe1", key="divine-orb", name="Divine Orb"))
            await session.commit()
            watch = (await session.scalars(select(PoeWatch))).one()
            assert watch.threshold == 20
            assert watch.created_at is not None
            assert (await session.scalars(select(PoeItem))).one().listings is None
            assert (await session.scalars(select(PoePrice))).one().price == 150.0
            session.add(item(price=1.0))
            with pytest.raises(IntegrityError):
                await session.commit()
        await engine.dispose()
    asyncio.run(go())
