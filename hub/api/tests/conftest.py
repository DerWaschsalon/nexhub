"""Testaufbau: echte Migrationen auf SQLite (oder Postgres über TEST_DATABASE_URL), Discord gefälscht."""
from __future__ import annotations

import os
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from nexhub_api.config import Settings
from nexhub_api.db import migrate
from nexhub_api.main import create_app

ADMIN = 111111111111111111
MEMBER = 222222222222222222
STRANGER = 333333333333333333
GUILD = 900000000000000000
ROLE = 910000000000000000
BASE = "http://localhost:8080"


class FakeDiscord:
    """Beantwortet die Discord-Aufrufe des Hubs; `user` bestimmt, wer sich gerade anmeldet."""

    def __init__(self) -> None:
        self.user = ADMIN
        self.roles: dict[int, list[int]] = {MEMBER: [ROLE], STRANGER: [123]}
        self.calls: list[str] = []
        self.token_status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v10")
        self.calls.append(f"{request.method} {path}")
        if path == "/oauth2/token":
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            form = parse_qs(request.content.decode())
            assert form["code_verifier"][0]
            return httpx.Response(200, json={"access_token": "discord-token", "token_type": "Bearer"})
        if path == "/oauth2/token/revoke":
            return httpx.Response(200)
        assert request.headers["authorization"] == "Bearer discord-token"
        if path == "/users/@me":
            return httpx.Response(200, json={"id": str(self.user), "username": f"u{self.user}",
                                             "global_name": "Testname", "avatar": "abc123"})
        if path == f"/users/@me/guilds/{GUILD}/member":
            if self.user not in self.roles:
                return httpx.Response(404, json={"message": "Unknown Guild"})
            return httpx.Response(200, json={"roles": [str(r) for r in self.roles[self.user]]})
        return httpx.Response(404)


@pytest.fixture
def database_url(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/hub.db"
    migrate(url)
    yield url
    if url.startswith("postgresql"):
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text

        async def _clean() -> None:
            engine = create_async_engine(url)
            async with engine.begin() as conn:
                await conn.execute(text("DROP TABLE IF EXISTS sessions, users, alembic_version"))
            await engine.dispose()
        asyncio.run(_clean())


@pytest.fixture
def fake() -> FakeDiscord:
    return FakeDiscord()


@pytest.fixture
def make_client(database_url, fake):
    def _make(**overrides) -> TestClient:
        values = dict(database_url=database_url, hub_base_url=BASE, hub_secret_key="test-geheimnis",
                      discord_client_id="cid", discord_client_secret="csecret",
                      hub_admin_ids=f"{ADMIN}", hub_guild_id=str(GUILD), hub_member_role_id=str(ROLE))
        settings = Settings(**{**values, **overrides})
        app = create_app(settings, http=httpx.AsyncClient(transport=httpx.MockTransport(fake)))
        return TestClient(app, base_url=BASE, follow_redirects=False)
    return _make


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c


def start_login(client: TestClient, next: str = "/") -> dict[str, str]:
    r = client.get("/api/auth/login", params={"next": next})
    assert r.status_code == 302
    return {k: v[0] for k, v in parse_qs(urlsplit(r.headers["location"]).query).items()}


def log_in(client: TestClient, next: str = "/") -> httpx.Response:
    q = start_login(client, next)
    return client.get("/api/auth/callback", params={"code": "c0de", "state": q["state"]})
