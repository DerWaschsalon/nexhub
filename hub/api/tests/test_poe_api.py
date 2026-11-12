"""API der Merkliste (angemeldet) und der Bot-Abfragen (/api/internal, Schlüssel) für Path of Exile."""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexhub_api import main
from nexhub_api.models import PoeItem, PoePrice
from nexhub_api.poe_prices import TZ, PoePrices

from .conftest import ADMIN, MEMBER, log_in
from .test_devices import ORIGIN

LEAGUE = "Standard"
KEY = "x" * 32
POE = {"hub_poe_enabled": True, "hub_poe1_league": LEAGUE, "bot_control_key": KEY}
AUTH = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture(autouse=True)
def no_background_poe(monkeypatch):
    """Abruf und Tagespost laufen hier nicht neben dem Hub her; die Tests tragen ihre Preise selbst ein."""
    async def idle(*args, **kwargs) -> None:
        return None
    monkeypatch.setattr(PoePrices, "run", idle)
    monkeypatch.setattr(main, "poe_daily_posts", idle)


def sign_in(client) -> None:
    log_in(client)
    client.headers.update(ORIGIN)  # Schutz vor fremden Seiten: ändernde Anfragen brauchen den Origin


def seed(database_url, *items: PoeItem | PoePrice) -> None:
    async def go():
        engine = create_async_engine(database_url)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            db.add_all(items)
            await db.commit()
        await engine.dispose()
    asyncio.run(go())


def item(name="Divine Orb", price=150.0, key=None, **over) -> PoeItem:
    fields = dict(game="poe1", league=LEAGUE, key=key or name.lower().replace(" ", "-"), name=name,
                  category="Currency", price=price, unit="chaos", updated_at=datetime.now(UTC))
    return PoeItem(**{**fields, **over})


def test_watch_roundtrip(database_url, make_client, fake, as_user):
    seed(database_url, item())
    fake.user = MEMBER
    with make_client(**POE) as c:
        sign_in(c)
        found = c.get("/api/poe/search", params={"game": "poe1", "q": "divine"}).json()
        assert found == [{"key": "divine-orb", "name": "Divine Orb", "category": "Currency", "icon": None,
                          "price": 150.0, "unit": "chaos"}]
        r = c.post("/api/poe/watches", json={"game": "poe1", "key": "divine-orb"})
        assert r.status_code == 201 and r.json()["threshold"] == 20
        assert c.post("/api/poe/watches", json={"game": "poe1", "key": "divine-orb"}).status_code == 409
        assert c.post("/api/poe/watches", json={"game": "poe1", "key": "nope"}).status_code == 404
        data = c.get("/api/poe/watches", params={"game": "poe1"}).json()
        assert data["league"] == LEAGUE and data["unit"] == "chaos"
        (entry,) = data["watches"]
        assert entry["price"] == 150.0 and entry["threshold"] == 20 and entry["change_24h"] is None
        assert entry["url"].endswith("/divine-orb") and entry["days"] == []
        assert c.patch(f"/api/poe/watches/{entry['id']}", json={"threshold": 35}).json()["threshold"] == 35
        assert c.patch(f"/api/poe/watches/{entry['id']}", json={"threshold": 0}).status_code == 422
        assert c.delete(f"/api/poe/watches/{entry['id']}").status_code == 204
        assert c.get("/api/poe/watches", params={"game": "poe1"}).json()["watches"] == []


def test_watch_changes_and_days(database_url, make_client, fake):
    today = datetime.now(TZ).date()
    seed(database_url, item(price=150.0),
         PoePrice(game="poe1", league=LEAGUE, key="divine-orb", day=today - timedelta(days=1), price=100.0),
         PoePrice(game="poe1", league=LEAGUE, key="divine-orb", day=today - timedelta(days=7), price=300.0),
         PoePrice(game="poe1", league=LEAGUE, key="divine-orb", day=today - timedelta(days=60), price=500.0),
         PoePrice(game="poe1", league="Alt", key="divine-orb", day=today, price=1.0))
    fake.user = MEMBER
    with make_client(**POE) as c:
        sign_in(c)
        c.post("/api/poe/watches", json={"game": "poe1", "key": "divine-orb"})
        (entry,) = c.get("/api/poe/watches", params={"game": "poe1"}).json()["watches"]
        assert entry["change_24h"] == 50.0 and entry["change_7d"] == -50.0
        assert [d["price"] for d in entry["days"]] == [500.0, 300.0, 100.0]


def test_watches_are_private(database_url, make_client, fake):
    seed(database_url, item())
    fake.user = MEMBER
    with make_client(**POE) as member, make_client(**POE) as admin:
        sign_in(member)
        wid = member.post("/api/poe/watches", json={"game": "poe1", "key": "divine-orb"}).json()["id"]
        fake.user = ADMIN
        sign_in(admin)
        assert admin.get("/api/poe/watches", params={"game": "poe1"}).json()["watches"] == []
        assert admin.delete(f"/api/poe/watches/{wid}").status_code == 404
        assert admin.patch(f"/api/poe/watches/{wid}", json={"threshold": 5}).status_code == 404
        assert len(member.get("/api/poe/watches", params={"game": "poe1"}).json()["watches"]) == 1


def test_search_special_chars(database_url, make_client, fake):
    seed(database_url, item("Winter's Bite", key="winters-bite"), item("100% Juice", key="juice"),
         item("Divine Orb"))
    fake.user = MEMBER
    with make_client(**POE) as c:
        sign_in(c)
        names = lambda q: [i["name"] for i in c.get("/api/poe/search", params={"game": "poe1", "q": q}).json()]
        assert names("winter's") == ["Winter's Bite"]
        assert names("%") == ["100% Juice"]
        assert names("_") == []
        assert names("\\") == []


def test_search_limit(database_url, make_client, fake):
    seed(database_url, *(item(f"Orb {n}", key=f"orb-{n}") for n in range(30)))
    fake.user = MEMBER
    with make_client(**POE) as c:
        sign_in(c)
        assert len(c.get("/api/poe/search", params={"game": "poe1", "q": "orb"}).json()) == 20


def test_internal_needs_key(make_client):
    with make_client(**POE) as c:
        url, params = "/api/internal/poe/price", {"game": "poe1", "q": "x"}
        assert c.get(url, params=params).status_code == 401
        assert c.get(url, params=params, headers={"Authorization": "Bearer falsch"}).status_code == 401
        assert c.get(url, params=params, headers={"Authorization": f"Basic {KEY}"}).status_code == 401
        assert c.get(url, params=params, headers={"Authorization": f"bearer {KEY}"}).status_code == 404
        assert c.get(url, params=params, headers=AUTH).status_code == 404  # Schlüssel stimmt, nichts gefunden
        assert c.get("/api/internal/poe/complete", params=params, headers=AUTH).status_code == 200
    with make_client(**{**POE, "bot_control_key": ""}) as c:
        assert c.get(url, params=params, headers={"Authorization": "Bearer "}).status_code == 401


def test_internal_price_best_match(database_url, make_client):
    seed(database_url, item("Divine Orb Shard", 5.0), item("Greater Divine Orb", 900.0), item("Divine Orb", 150.0),
         item("Divine Orb Fragment", 7.0))
    with make_client(**POE) as c:
        r = c.get("/api/internal/poe/price", params={"game": "poe1", "q": "divine orb"}, headers=AUTH).json()
        assert r["name"] == "Divine Orb" and r["price"] == 150.0 and r["league"] == LEAGUE
        assert set(r) == {"name", "price", "unit", "change_24h", "change_7d", "league", "url", "icon"}
        r = c.get("/api/internal/poe/price", params={"game": "poe1", "q": "divine"}, headers=AUTH).json()
        assert r["name"] == "Divine Orb"  # Anfang vor enthält; unter den Anfängen der höchste Preis
        names = c.get("/api/internal/poe/complete", params={"game": "poe1", "q": "orb"}, headers=AUTH).json()
        assert "Divine Orb" in names and all(isinstance(n, str) for n in names)


def test_disabled_is_404(make_client, fake):
    fake.user = MEMBER
    with make_client(bot_control_key=KEY) as c:
        sign_in(c)
        assert c.get("/api/poe/search", params={"game": "poe1", "q": "a"}).status_code == 404
        assert c.get("/api/poe/watches", params={"game": "poe1"}).status_code == 404
        assert c.get("/api/internal/poe/price", params={"game": "poe1", "q": "a"}, headers=AUTH).status_code == 404
