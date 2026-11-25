"""Sichttest-Instanz des Hubs: eine Wegwerf-Datenbank mit Beispieldaten und die API auf Port 8000.

    cd hub/api && uv run python ../tools/sichttest.py [ordner]      (Standard: /tmp/nexhub-sichttest)
    cd hub/web && npx vite dev --port 8080 --strictPort             (leitet /api an Port 8000 weiter)

Discord, die AION-2-Website, Abyss Logs und MetaBot sind die Nachbauten aus den Tests (tests/conftest.py),
es geht also nichts ins Netz. Drin sind: ein Admin-Konto, ein gekoppeltes Gerät, ein Run (mit Beute), ein
Armory-Charakter mit vier Teilen, Zählung und Würfeltabellen dazu (ein Teil je Gruppe des Upgrade-Plans).

Anmelden im Browser: Das Skript schreibt das Sitzungs-Cookie nach <ordner>/cookie.txt und gibt die Zeile für
die Browser-Konsole aus (`document.cookie = '…; path=/'`), dann http://localhost:8080/hub öffnen.
Nur zum Ansehen beim Entwickeln, nie gegen echte Daten.
"""
from __future__ import annotations

import asyncio
import copy
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import uvicorn
from fastapi.testclient import TestClient
from nexhub_api.modules.bis import collector as bis_collector
from nexhub_api.modules.armory import census as census_module
from nexhub_api.aion2 import NC
from nexhub_api.modules.bis.collector import BisCollector
from nexhub_api.modules.armory.census import Census
from nexhub_api.config import Settings
from nexhub_api.db import migrate
from nexhub_api.main import create_app
from nexhub_api.modules.armory.models import Character, ClassCensus, ItemRolls
from nexhub_api.modules.bis import routes as bis_route
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests import test_rating, test_upgrades
from tests.conftest import ADMIN, BASE, GUILD, ROLE, FakeDiscord, log_in
from tests.test_armory import NEW
from tests.test_bis import collect_all, with_top_rangers
from tests.test_devices import ORIGIN, pair
from tests.test_runs import nexlog, upload

PORT = 8000
LOOT = [{"t_ms": 1_792_000_405_000, "item_id": 110430050, "count": 1},
        {"t_ms": 1_792_000_406_000, "item_id": 120880011, "count": 1}]
# Ausrüstung des Beispielcharakters: je ein Teil zum Würfeln (weit weg, knapp dran), fertig, nur zu binden
HALF_BOUND = test_rating.shield(("Combat Speed", "5%"), ("Weapon Damage Boost", "3%"), ("Might", "10"),
                                ("Multi-hit Chance", "4%"))
GEAR = {"SubHand": ("Testschild", test_upgrades.WEAK), "Boots": ("Teststiefel", test_upgrades.CLOSE),
        "MainHand": ("Testbogen", test_rating.TOP), "Helmet": ("Testhelm", HALF_BOUND)}


def settings_for(folder: Path) -> Settings:
    url = f"sqlite+aiosqlite:///{folder / 'hub.db'}"
    return Settings(database_url=url, hub_base_url=BASE, hub_secret_key="sichttest", discord_client_id="cid",
                    discord_client_secret="csecret", hub_admin_ids=f"{ADMIN}", hub_guild_id=str(GUILD),
                    hub_member_role_id=str(ROLE), hub_web_dir=None, hub_data_dir=str(folder / "data"),
                    hub_aion2_enabled=True, hub_aion2_pause=0)


def small_pools() -> None:
    """Fünf statt 200 Top-Spieler genügen, und der Sammler läuft nicht nebenher."""
    census_module.MIN_SAMPLE = bis_collector.POOL_SIZE = 5
    census_module.METABOT_PAUSE = 0
    bis_route.MIN_SAMPLE = 3

    async def idle(self: BisCollector) -> None:
        return None
    BisCollector.run = idle  # type: ignore[method-assign]


def seed_over_api(app, folder: Path) -> None:
    """Anmelden, Gerät koppeln, Run hochladen, Charakter eintragen: über die API wie im echten Betrieb."""
    with TestClient(app, base_url=BASE, follow_redirects=False) as browser:
        log_in(browser)
        device = TestClient(app, base_url=BASE, follow_redirects=False)  # ohne Sitzung, wie ein NexBoard
        upload(device, pair(device, browser), nexlog(loot=LOOT))
        browser.post("/api/armory", json=NEW, headers=ORIGIN)
        cookie = "; ".join(f"{name}={value}" for name, value in browser.cookies.items())
    (folder / "cookie.txt").write_text(cookie)
    print(f"Im Browser auf {BASE} in der Konsole:\n  document.cookie = '{cookie}; path=/'")


async def seed_rating(url: str, fake: FakeDiscord) -> None:
    """Bestand der BiS-Listen und Zählung über die Nachbauten, dann die Ausrüstung für den Upgrade-Plan."""
    engine = create_async_engine(url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    with_top_rangers(fake)
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
        await collect_all(BisCollector(sessionmaker, NC(http, 0), http))
        await Census(sessionmaker, http).count("ranger")
    async with sessionmaker() as db:
        await give_gear(db)
        await db.commit()
    await engine.dispose()


async def give_gear(db) -> None:
    """Dem Beispielcharakter die Teile aus GEAR geben, mit passender Zählung und Würfeltabellen."""
    census = test_rating.census()
    for slot in GEAR:
        census["slots"][slot] = census["slots"][test_rating.SLOT]
        census["tops"][slot] = census["tops"][test_rating.SLOT]
    row = await db.get(Character, 1)
    data = copy.deepcopy(row.data)
    for lang in ("en", "de"):
        template = data[lang]["equipment"][0]
        data[lang]["equipment"] = [piece(template, slot, name, source) for slot, (name, source) in GEAR.items()]
    row.data, row.cls = data, "ranger"
    counted = await db.get(ClassCensus, "ranger")
    counted.data, counted.fetched_at = census, datetime.now(UTC)
    for name, _ in GEAR.values():
        rolls = await db.get(ItemRolls, name) or ItemRolls(name=name)
        rolls.data, rolls.fetched_at = test_rating.TABLE, datetime.now(UTC)
        db.add(rolls)


def piece(template: dict, slot: str, name: str, source: dict) -> dict:
    item = copy.deepcopy(template)
    item["slot_name"], item["name"] = slot, name
    item["detail"]["sub"] = [{"id": s["name"], "name": s["name"], "value": s["value"]} for s in source["detail"]["sub"]]
    item["detail"]["skills"] = []
    item["detail"]["soul_bind_rate"] = 50.0 if source is HALF_BOUND else 100.0
    return item


def main() -> None:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/nexhub-sichttest")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "hub.db").unlink(missing_ok=True)
    settings = settings_for(folder)
    migrate(settings.database_url)
    small_pools()
    fake = FakeDiscord()
    fake.user = ADMIN

    def new_app():
        return create_app(settings, http=httpx.AsyncClient(transport=httpx.MockTransport(fake)))

    seed_over_api(new_app(), folder)
    asyncio.run(seed_rating(settings.database_url, fake))
    uvicorn.run(new_app(), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
