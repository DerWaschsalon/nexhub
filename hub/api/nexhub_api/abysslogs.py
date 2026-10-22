"""Abyss Logs (abysslogs.com): DPS-Ranglisten der Community, Quelle der Top-Spieler im Build-Check.

Die API ist inoffiziell und nicht dokumentiert (aus dem JS-Bundle der Seite gelesen, Stand 22.10.2026).
Ändert sie sich, schlägt nur der Build-Check mit einer Meldung fehl. Abgefragt wird nur auf Klick.
Die Rangliste nennt keinen Server; den löst der Build-Check über die NC-Suche auf.
"""
from __future__ import annotations

import re

import httpx

HOST = "api.abysslogs.com"
API = f"https://{HOST}/v1"
REGION = "eu"
MIN_SECONDS = 30  # kürzere Kämpfe sind Messfehler (Einträge mit 0,01 s und Riesen-DPS)
CP_RANGE = 0.15  # Vergleich mit Spielern ähnlicher Kampfkraft: ±15 %
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
    if r.status_code >= 400:
        raise AbyssError(f"Abyss Logs: HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise AbyssError("Abyss Logs: Antwort kein JSON") from None


def _stage(tier: str) -> int:
    found = re.search(r"\d+", tier or "")
    return int(found.group()) if found else 0


async def top_bosses(http: httpx.AsyncClient) -> list[int]:
    """Bosse der höchsten Transzendenz-Stufe, dort trennen sich die Besten am deutlichsten."""
    rows = await _get(http, "/bosses", {"region": REGION})
    if not isinstance(rows, list):
        raise AbyssError("Abyss Logs: Bossliste unbekannt")
    bosses = [b for b in rows if isinstance(b, dict) and b.get("category") == "Transcendence"]
    if not bosses:
        raise AbyssError("Abyss Logs: keine Transzendenz-Bosse")
    top = max(_stage(b.get("tier")) for b in bosses)
    return [b["mobCode"] for b in bosses if _stage(b.get("tier")) == top]


async def leaderboard(http: httpx.AsyncClient, cls: str, boss: int) -> list[dict]:
    """Bestenliste einer Klasse an einem Boss (Anzeigename der Klasse, siehe abyss_class)."""
    body = await _get(http, "/leaderboards", {"region": REGION, "class": cls, "boss": boss, "limit": 100})
    entries = body.get("entries") if isinstance(body, dict) else None
    if not isinstance(entries, list):
        raise AbyssError("Abyss Logs: Rangliste unbekannt")
    return [e for e in entries if isinstance(e, dict) and e.get("playerName")]


def pick_group(entries: list[dict], own_cp: int) -> list[dict]:
    """Je Name der beste Kampf, nur echte Kämpfe und ähnliche Kampfkraft, stärkste zuerst. Ohne
    Begrenzung: nicht jeder Name lässt sich auflösen, dann rückt der nächste nach."""
    low, high = own_cp * (1 - CP_RANGE), own_cp * (1 + CP_RANGE)
    best: dict[str, dict] = {}
    for e in entries:
        if (e.get("combatDuration") or 0) < MIN_SECONDS or not low <= (e.get("combatPower") or 0) <= high:
            continue
        name = e["playerName"]
        if name not in best or e.get("dps", 0) > best[name].get("dps", 0):
            best[name] = e
    return sorted(best.values(), key=lambda e: e.get("dps", 0), reverse=True)
