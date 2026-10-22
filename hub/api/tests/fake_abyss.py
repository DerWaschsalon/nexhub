"""Nachgebaute Abyss-Logs-API für Tests: Antworten im Format von api.abysslogs.com/v1, Inhalte erfunden."""
from __future__ import annotations

import httpx

HOST = "api.abysslogs.com"


def bosses() -> list[dict]:
    return [{"mobCode": 2350709, "name": "Testboss A", "category": "Transcendence", "tier": "Stage 4"},
            {"mobCode": 2340601, "name": "Testboss B", "category": "Transcendence", "tier": "Stage 4"},
            {"mobCode": 2340001, "name": "Testboss C", "category": "Transcendence", "tier": "Stage 2"},
            {"mobCode": 2300471, "name": "Testboss D", "category": "Dungeon", "tier": "Conquest [Normal]"}]


def entry(name: str, cp: int = 123_000, dps: float = 50_000, duration: float = 120) -> dict:
    return {"rank": 1, "region": "eu", "playerName": name, "classHint": "Ranger", "gearScore": 2600,
            "combatPower": cp, "dps": dps, "totalDamage": int(dps * duration), "combatDuration": duration,
            "encounterId": "", "verified": False, "createdAt": "2026-10-20T19:10:49Z"}


class FakeAbyss:
    """`routes` je Test überschreibbar (Pfad → dict/list = JSON 200, int = Statuscode). `size` Einträge in der
    Rangliste, Namen „Bogenheld“, „Bogenheld2“ …, Kampfkraft passend zu fake_nc.info (123_456)."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.last_query = ""
        self.size = 20
        self.routes: dict[str, object] = {}

    def leaderboard(self) -> dict:
        names = ["Bogenheld"] + [f"Bogenheld{i}" for i in range(2, self.size + 1)]
        rows = [entry(n, dps=90_000 - i * 1000) for i, n in enumerate(names)]
        return {"entries": rows, "total": len(rows), "page": 1, "limit": 100}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        self.last_query = request.url.query.decode()
        default = {"/v1/bosses": bosses(), "/v1/leaderboards": self.leaderboard()}
        answer = self.routes.get(path, default.get(path, 404))
        if isinstance(answer, int):
            return httpx.Response(answer)
        return httpx.Response(200, json=answer)
