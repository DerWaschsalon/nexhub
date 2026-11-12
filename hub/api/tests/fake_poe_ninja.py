"""Nachgebaute poe.ninja-API für Tests. Antworten aus data/poe_ninja/: gekürzte echte Antworten vom
12.11.2026 (Dateiname <spiel>_<art>_<kategorie>.json bzw. <spiel>_leagues.json). Kategorien ohne Datei
liefern eine leere Übersicht. ETag wie bei poe.ninja: passt `If-None-Match`, kommt 304."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

HOST = "poe.ninja"
DATA = Path(__file__).parent / "data" / "poe_ninja"
# Pfad der Übersicht → Art wie in poe_ninja.overview
KINDS = {"exchange/current/overview": "exchange", "stash/current/item/overview": "stash"}
PRIMARY = {"poe1": "chaos", "poe2": "divine"}


def sample(name: str) -> Any:
    return json.loads((DATA / f"{name}.json").read_text())


class FakePoeNinja:
    """`overviews` je „<spiel>/<art>/<kategorie>“ eine Antwort oder ein Statuscode; `requests` alle Anfragen."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.overviews: dict[str, Any] = {path.stem.replace("_", "/"): json.loads(path.read_text())
                                          for path in DATA.glob("poe?_*_*.json")}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        game, _, rest = request.url.path.strip("/").partition("/api/economy/")
        if rest == "leagues":
            return self.reply(request, sample(f"{game}_leagues"))
        kind = KINDS.get(rest)
        if kind is None:
            return httpx.Response(404)
        found = self.overviews.get(f"{game}/{kind}/{request.url.params['type']}")
        if isinstance(found, int):
            return httpx.Response(found)
        empty = {"core": {"items": [], "rates": {}, "primary": PRIMARY[game]}, "lines": [], "items": []}
        return self.reply(request, empty if found is None else found)

    @staticmethod
    def reply(request: httpx.Request, data: Any) -> httpx.Response:
        body = json.dumps(data).encode()
        etag = f'W/"{hashlib.md5(body).hexdigest()}"'
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"etag": etag})
        return httpx.Response(200, content=body, headers={"etag": etag, "content-type": "application/json",
                                                          "cache-control": "public, max-age=1800"})
