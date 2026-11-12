"""Preise von poe.ninja (https://poe.ninja/docs/api) für Path of Exile 1 und 2.

poe.ninja erlaubt die Preis-Endpunkte für eigene Anwendungen, verlangt einen User-Agent mit Kontakt,
bedingte Abrufe (ETag) und wenig Last. Abgerufen wird nur im Hub (poe_prices.py), höchstens stündlich.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx

log = logging.getLogger(__name__)

Game = Literal["poe1", "poe2"]
GAMES: tuple[Game, ...] = ("poe1", "poe2")
BASE = "https://poe.ninja"
OVERVIEW_PATHS = {"exchange": "exchange/current/overview", "stash": "stash/current/item/overview"}

# Kategorien (`type` der API) aus der poe.ninja-Doku, Stand 12.11.2026, je mit dem Pfad der Seite auf
# poe.ninja (auf der Website nachgesehen). Die Stash-Währungsübersicht von PoE 1 fehlt mit Absicht:
# Währung und Fragmente kommen aus der Exchange-Übersicht.
EXCHANGE_PAGES: dict[Game, dict[str, str]] = {
    "poe1": {"Currency": "currency", "Fragment": "fragments", "Runegraft": "runegrafts",
             "AllflameEmber": "allflame-embers", "Tattoo": "tattoos", "Omen": "omens", "DjinnCoin": "djinn-coins",
             "Ducat": "ducats", "EnshroudingCrystal": "enshrouding-crystals", "DivinationCard": "divination-cards",
             "Artifact": "artifacts", "Oil": "oils", "DeliriumOrb": "delirium-orbs", "Scarab": "scarabs",
             "Astrolabe": "astrolabes", "Fossil": "fossils", "Resonator": "resonators", "Essence": "essences"},
    "poe2": {"Currency": "currency", "Fragments": "fragments", "Abyss": "abyssal-bones", "UncutGems": "uncut-gems",
             "LineageSupportGems": "lineage-support-gems", "Essences": "essences", "SoulCores": "soul-cores",
             "Idols": "idols", "Runes": "runes", "Ritual": "omens", "Expedition": "expedition",
             "Delirium": "liquid-emotions", "Breach": "breach-catalyst", "Verisium": "verisium"},
}
STASH_PAGES: dict[Game, dict[str, str]] = {
    "poe1": {"Wombgift": "wombgifts", "Corpse": "corpses", "Incubator": "incubators",
             "UniqueWeapon": "unique-weapons", "UniqueArmour": "unique-armours",
             "UniqueAccessory": "unique-accessories", "UniqueFlask": "unique-flasks", "UniqueJewel": "unique-jewels",
             "ForbiddenJewel": "forbidden-jewels", "ShrineBelt": "shrine-belts", "UniqueTincture": "unique-tinctures",
             "UniqueRelic": "unique-relics", "SkillGem": "skill-gems", "ImbuedGem": "imbued-gems",
             "ClusterJewel": "cluster-jewels", "Map": "maps", "BlightedMap": "blighted-maps",
             "BlightRavagedMap": "blight-ravaged-maps", "UniqueMap": "unique-maps", "ValdoMap": "valdo-maps",
             "Invitation": "invitations", "Memory": "memories", "IncursionTemple": "temples",
             "ScryingOrb": "scrying-orbs", "BaseType": "base-types", "Flask": "flasks", "Beast": "beasts",
             "Vial": "vials"},
    "poe2": {"UniqueWeapons": "unique-weapons", "UniqueArmours": "unique-armours",
             "UniqueAccessories": "unique-accessories", "UniqueFlasks": "unique-flasks",
             "UniqueCharms": "unique-charms", "UniqueJewels": "unique-jewels", "UniqueSanctumRelics": "unique-relics",
             "UniqueTablets": "unique-tablets", "PrecursorTablets": "precursor-tablets"},
}
EXCHANGE_TYPES: dict[Game, tuple[str, ...]] = {game: tuple(pages) for game, pages in EXCHANGE_PAGES.items()}
STASH_TYPES: dict[Game, tuple[str, ...]] = {game: tuple(pages) for game, pages in STASH_PAGES.items()}


BLOCKED = (403, 429)  # poe.ninja will weniger Last
CATEGORIES: dict[Game, list[tuple[Literal["exchange", "stash"], str]]] = {
    game: [("exchange", c) for c in EXCHANGE_TYPES[game]] + [("stash", c) for c in STASH_TYPES[game]]
    for game in GAMES}


class PoeNinjaError(Exception):
    """poe.ninja nicht erreichbar oder Antwort kein 200/304."""


class PoeNinjaBlocked(PoeNinjaError):
    """403/429: poe.ninja will weniger Last. `retry_after` in Sekunden aus dem Header, sonst 0."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def retry_after(response: httpx.Response) -> float:
    """Retry-After in Sekunden; die Form als Datum kommt bei poe.ninja nicht vor und zählt als 0."""
    value = response.headers.get("retry-after", "")
    return float(value) if value.isdigit() else 0.0


@dataclass(frozen=True)
class PriceLine:
    """Preis eines Gegenstands; `key` ist die poe.ninja-ID (detailsId), `unit` die Währung des Preises."""

    game: Game
    league: str
    key: str
    name: str
    category: str
    icon: str | None
    price: float
    unit: str
    listings: int | None
    trade_volume: float | None


def parse_exchange(game: Game, league: str, category: str, data: dict[str, Any]) -> list[PriceLine]:
    """Exchange-Übersicht (beide Spiele gleich): Namen und Symbole stehen in `items`, über `id` verknüpft."""
    meta = {item["id"]: item for item in data["items"]}
    unit = data["core"]["primary"]

    def convert(line: dict[str, Any]) -> PriceLine:
        item = meta[line["id"]]
        image = item.get("image")
        return PriceLine(game, league, item["detailsId"], item["name"], category, BASE + image if image else None,
                         float(line["primaryValue"]), unit, None, float(line["volumePrimaryValue"]))
    return convert_rows(game, category, data["lines"], convert)


def parse_stash(game: Game, league: str, category: str, data: dict[str, Any]) -> list[PriceLine]:
    """Stash-Übersicht: PoE 1 rechnet in Chaos (`chaosValue`), PoE 2 in der Währung aus `core.primary`."""
    if game == "poe1":
        unit, value = "chaos", "chaosValue"
    else:
        unit, value = data["core"]["primary"], "primaryValue"

    def convert(line: dict[str, Any]) -> PriceLine:
        return PriceLine(game, league, line["detailsId"], line["name"], category, line.get("icon"),
                         float(line[value]), unit, int(line["listingCount"]), None)
    return convert_rows(game, category, data["lines"], convert)


def convert_rows(game: Game, category: str, rows: Any,
                 convert: Callable[[dict[str, Any]], PriceLine]) -> list[PriceLine]:
    """Einzelne kaputte Zeilen (Preis fehlt, unbekannte ID) überspringen, den Rest behalten.
    Ist `lines` selbst keine Liste, hat poe.ninja das Format geändert: dann scheitert die Kategorie."""
    if not isinstance(rows, list):
        raise ValueError(f"{game} {category}: `lines` ist keine Liste")
    lines, skipped = [], 0
    for row in rows:
        try:
            lines.append(convert(row))
        except (KeyError, TypeError, ValueError):
            skipped += 1
    if skipped:
        log.warning("poe.ninja: %s %s: %d Zeilen übersprungen", game, category, skipped)
    return lines


def league_slug(league: str) -> str:
    """Liga im Pfad der Website: klein ohne Leerzeichen, Hardcore hinten („HC Runes of Aldur“ → „runesofaldurhc“)."""
    words = league.lower().split()
    if len(words) > 1 and words[0] in ("hc", "hardcore"):
        words = words[1:] + ["hc"]
    return "".join(words)


def ninja_url(game: Game, league: str, category: str, key: str) -> str:
    """Seite des Gegenstands auf poe.ninja; Format am 12.11.2026 auf der Website nachgesehen."""
    page = (EXCHANGE_PAGES[game] | STASH_PAGES[game])[category]
    return f"{BASE}/{game}/economy/{league_slug(league)}/{page}/{key}"


class PoeNinja:
    """Zugriff auf poe.ninja. Merkt sich je Adresse nur das ETag; 304 (unverändert) gibt None zurück."""

    def __init__(self, http: httpx.AsyncClient, user_agent: str) -> None:
        self.http, self.user_agent = http, user_agent
        self.etags: dict[str, str] = {}

    async def leagues(self, game: Game) -> list[str] | None:
        """Aktive Ligen, die erste ist die aktuelle Challenge-Liga; None, wenn unverändert."""
        data = await self.get(f"{BASE}/{game}/api/economy/leagues")
        return None if data is None else [league["id"] for league in data]

    def overview_address(self, game: Game, kind: Literal["exchange", "stash"], league: str, category: str) -> str:
        params = {"league": league, "type": category}
        return str(httpx.URL(f"{BASE}/{game}/api/economy/{OVERVIEW_PATHS[kind]}", params=params))

    async def overview(self, game: Game, kind: Literal["exchange", "stash"], league: str,
                       category: str) -> dict[str, Any] | None:
        """Übersicht einer Kategorie; None, wenn sie seit dem letzten Abruf unverändert ist."""
        data = await self.get(self.overview_address(game, kind, league, category))
        if data is not None and not isinstance(data, dict):
            raise PoeNinjaError(f"{game} {kind} {category}: unerwartete Antwort")
        return data

    def forget(self, game: Game, kind: Literal["exchange", "stash"], league: str, category: str) -> None:
        """ETag verwerfen, wenn die Antwort nicht gespeichert werden konnte: sonst käme nur noch 304."""
        self.etags.pop(self.overview_address(game, kind, league, category), None)

    async def get(self, address: str) -> Any:
        headers = {"User-Agent": self.user_agent}
        etag = self.etags.get(address)
        if etag:
            headers["If-None-Match"] = etag
        try:
            response = await self.http.get(address, headers=headers)
        except httpx.HTTPError as error:
            raise PoeNinjaError(f"{address}: {error!r}") from error
        if response.status_code == 304 and etag:
            return None
        if response.status_code in BLOCKED:
            raise PoeNinjaBlocked(f"{address}: HTTP {response.status_code}", retry_after(response))
        if response.status_code != 200:
            raise PoeNinjaError(f"{address}: HTTP {response.status_code}")
        data = response.json()
        if new_etag := response.headers.get("etag"):
            self.etags[address] = new_etag
        return data
