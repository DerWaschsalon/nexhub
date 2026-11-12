"""Preise von poe.ninja (https://poe.ninja/docs/api) für Path of Exile 1 und 2.

poe.ninja erlaubt die Preis-Endpunkte für eigene Anwendungen, verlangt einen User-Agent mit Kontakt,
bedingte Abrufe (ETag) und wenig Last. Abgerufen wird nur im Hub (poe_prices.py), höchstens stündlich.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

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


class PoeNinjaError(Exception):
    """poe.ninja nicht erreichbar oder Antwort kein 200/304."""


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
    lines = []
    for line in data["lines"]:
        item = meta[line["id"]]
        image = item.get("image")
        lines.append(PriceLine(game, league, item["detailsId"], item["name"], category,
                               BASE + image if image else None, float(line["primaryValue"]), unit, None,
                               float(line["volumePrimaryValue"])))
    return lines


def parse_stash(game: Game, league: str, category: str, data: dict[str, Any]) -> list[PriceLine]:
    """Stash-Übersicht: PoE 1 rechnet in Chaos (`chaosValue`), PoE 2 in der Währung aus `core.primary`."""
    if game == "poe1":
        unit, value = "chaos", "chaosValue"
    else:
        unit, value = data["core"]["primary"], "primaryValue"
    return [PriceLine(game, league, line["detailsId"], line["name"], category, line.get("icon"),
                      float(line[value]), unit, int(line["listingCount"]), None) for line in data["lines"]]


def league_slug(league: str) -> str:
    """Liga im Pfad der Website: klein ohne Leerzeichen, Hardcore hinten („HC Runes of Aldur“ → „runesofaldurhc“)."""
    words = league.lower().split()
    if len(words) > 1 and words[0] in ("hc", "hardcore"):
        words = words[1:] + ["hc"]
    return "".join(words)


def ninja_url(game: Game, league: str, category: str, key: str) -> str:
    """Seite des Gegenstands auf poe.ninja; Format am 12.11.2026 auf der Website nachgesehen."""
    page = (EXCHANGE_PAGES[game] | STASH_PAGES[game]).get(category, category.lower())
    return f"{BASE}/{game}/economy/{league_slug(league)}/{page}/{key}"


class PoeNinja:
    """Zugriff auf poe.ninja. Merkt sich je Adresse ETag und Antwort; bei 304 kommt die gemerkte Antwort."""

    def __init__(self, http: httpx.AsyncClient, user_agent: str) -> None:
        self.http, self.user_agent = http, user_agent
        self.cache: dict[str, tuple[str, Any]] = {}

    async def leagues(self, game: Game) -> list[str]:
        """Aktive Ligen, die erste ist die aktuelle Challenge-Liga."""
        return [league["id"] for league in await self.get(f"{BASE}/{game}/api/economy/leagues", {})]

    async def overview(self, game: Game, kind: Literal["exchange", "stash"], league: str,
                       category: str) -> dict[str, Any]:
        data = await self.get(f"{BASE}/{game}/api/economy/{OVERVIEW_PATHS[kind]}",
                              {"league": league, "type": category})
        if not isinstance(data, dict):
            raise PoeNinjaError(f"{game} {kind} {category}: unerwartete Antwort")
        return data

    async def get(self, url: str, params: dict[str, str]) -> Any:
        address = str(httpx.URL(url, params=params))
        headers = {"User-Agent": self.user_agent}
        cached = self.cache.get(address)
        if cached:
            headers["If-None-Match"] = cached[0]
        try:
            response = await self.http.get(address, headers=headers)
        except httpx.HTTPError as error:
            raise PoeNinjaError(f"{address}: {error!r}") from error
        if response.status_code == 304 and cached:
            return cached[1]
        if response.status_code != 200:
            raise PoeNinjaError(f"{address}: HTTP {response.status_code}")
        data = response.json()
        if etag := response.headers.get("etag"):
            self.cache[address] = (etag, data)
        return data
