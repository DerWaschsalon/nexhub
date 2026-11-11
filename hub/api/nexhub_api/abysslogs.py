"""Abyss Logs (abysslogs.com): DPS-Ranglisten der Community, Quelle der Top-Spieler für die Zählung
(census.py).

Die API ist inoffiziell und nicht dokumentiert (aus dem JS-Bundle der Seite gelesen). Ändert sie sich,
bleibt die letzte Zählung stehen. Die Rangliste nennt keinen Server; den löst census.py über die NC-Suche.
"""
from __future__ import annotations

import httpx

HOST = "api.abysslogs.com"
API = f"https://{HOST}/v1"
REGION = "eu"
MIN_SECONDS = 30  # kürzere Kämpfe sind Messfehler (Einträge mit 0,01 s und Riesen-DPS)
TIERS = ("Hard", "Normal")  # Hard vor Normal
# Hub-Klasse → Anzeigename bei Abyss Logs, wo er abweicht (sonst groß geschrieben)
CLASS_NAMES = {"spiritmaster": "Elementalist"}


class AbyssError(Exception):
    pass


def abyss_class(cls: str) -> str:
    return CLASS_NAMES.get(cls, cls.capitalize())


async def _get(http: httpx.AsyncClient, path: str, params: dict) -> object:
    try:
        r = await http.get(f"{API}{path}", params=params, timeout=15)
    except httpx.HTTPError as e:
        raise AbyssError(f"Abyss Logs nicht erreichbar ({type(e).__name__})") from e
    if r.status_code == 400 and "not ranked" in r.text:
        return {"entries": []}  # nicht jeder Boss hat eine Rangliste
    if r.status_code >= 400:
        raise AbyssError(f"Abyss Logs: HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise AbyssError("Abyss Logs: Antwort kein JSON") from None


async def raids(http: httpx.AsyncClient) -> list[tuple[str, str, list[int]]]:
    """Raids als (Name, Schwierigkeit, Bosse), der neueste zuerst. Hard und Normal desselben Raids
    haben verschiedene dungeonIds; zusammen gehören sie über die Namen ihrer Bosse."""
    rows = await _get(http, "/bosses", {"region": REGION})
    if not isinstance(rows, list):
        raise AbyssError("Abyss Logs: Bossliste unbekannt")
    by_dungeon: dict[int, list[dict]] = {}
    for b in rows:
        if isinstance(b, dict) and b.get("category") == "Raid" and b.get("tier") in TIERS:
            by_dungeon.setdefault(b["dungeonId"], []).append(b)
    out = []
    order: dict[frozenset, int] = {}  # Raid in der Reihenfolge seines neuesten Eintrags
    for dungeon in sorted(by_dungeon, reverse=True):
        bosses = by_dungeon[dungeon]
        key = frozenset(b["name"] for b in bosses)
        order.setdefault(key, len(order))
        # benannt nach dem Endboss: der mit der höchsten Kennung
        final = max(bosses, key=lambda b: b["mobCode"])["name"]
        out.append((order[key], final, bosses[0]["tier"], [b["mobCode"] for b in bosses]))
    # darin Hard vor Normal
    out.sort(key=lambda r: (r[0], TIERS.index(r[2])))
    return [(name, tier, codes) for _, name, tier, codes in out]


async def leaderboard(http: httpx.AsyncClient, cls: str, boss: int) -> list[dict]:
    """Bestenliste einer Klasse (Anzeigename, siehe abyss_class) an einem Boss."""
    body = await _get(http, "/leaderboards", {"region": REGION, "class": cls, "boss": boss, "limit": 100})
    entries = body.get("entries") if isinstance(body, dict) else None
    if not isinstance(entries, list):
        raise AbyssError("Abyss Logs: Rangliste unbekannt")
    return [e for e in entries if isinstance(e, dict) and e.get("playerName")]


def best_per_name(entries: list[dict]) -> list[dict]:
    """Je Name der beste echte Kampf, stärkste zuerst."""
    best: dict[str, dict] = {}
    for e in entries:
        if (e.get("combatDuration") or 0) < MIN_SECONDS:
            continue
        name = e["playerName"]
        if name not in best or e.get("dps", 0) > best[name].get("dps", 0):
            best[name] = e
    return sorted(best.values(), key=lambda e: e.get("dps", 0), reverse=True)


async def top_players(http: httpx.AsyncClient, cls: str, wanted: int) -> tuple[str, list[dict]]:
    """Top-Spieler einer Klasse im neuesten Raid, der genug Einträge hat (Hard vor Normal).
    Gibt die Bezeichnung der Gruppe („Raid · Hard“) und die Einträge zurück, stärkste zuerst."""
    for name, tier, bosses in await raids(http):
        entries = [e for boss in bosses for e in await leaderboard(http, abyss_class(cls), boss)]
        players = best_per_name(entries)
        if len(players) >= wanted:
            return f"{name} · {tier}", players
    raise AbyssError("Abyss Logs: kein Raid mit genug Einträgen")
