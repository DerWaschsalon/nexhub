"""Anzeige der Path-of-Exile-Preise in Discord: Preisalarm, Tagespost und /poe preis.

Die Daten kommen fertig vom Hub (hub/api/nexhub_api/poe_alerts.py `Move`, routes/poe.py `PriceOut`).
"""

from __future__ import annotations

from typing import Any

import discord

COLOUR = 0xAF6025  # Bronze wie die Schrift im Spiel
FOOTER = "Preise: poe.ninja"
GAME_LABELS = {"poe1": "PoE 1", "poe2": "PoE 2"}
NO_MOVES = "keine"
NO_CHANGE = "–"
FIELD_LIMIT = 1024  # Discords Grenze für den Text eines Felds
SMALL_PRICE = 10  # darunter zählen Nachkommastellen (0,35 divine), darüber nicht mehr


def fmt_price(value: float, unit: str) -> str:
    digits = 2 if value < SMALL_PRICE else 0
    number = f"{value:.{digits}f}".replace(".", ",")
    return f"{number} {unit}"


def fmt_change(change: float | None) -> str:
    if change is None:
        return NO_CHANGE
    rounded = round(change)
    if rounded == 0:
        return "0 %"  # sonst stünde bei kleinen Verlusten „-0 %“ da
    return f"{rounded:+d} %"


def move_text(move: dict[str, Any]) -> str:
    """Alter und neuer Preis mit Änderung, z. B. „100 divine → 125 divine (+25 %)“."""
    old, new = fmt_price(move["old"], move["unit"]), fmt_price(move["new"], move["unit"])
    return f"{old} → {new} ({fmt_change(move['change'])})"


def base_embed(title: str, game: str, league: str, *, url: str | None = None,
               icon: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, url=url, colour=COLOUR)
    embed.set_author(name=f"{GAME_LABELS.get(game, game)} · {league}")
    if icon:
        embed.set_thumbnail(url=icon)
    embed.set_footer(text=FOOTER)
    return embed


def alert_embed(data: dict[str, Any]) -> discord.Embed:
    embed = base_embed(f"Preisalarm: {data['name']}", data["game"], data["league"], url=data["url"],
                       icon=data["icon"])
    embed.description = move_text(data)
    return embed


def move_lines(moves: list[dict[str, Any]]) -> str:
    lines = [f"[{m['name']}]({m['url']}): {move_text(m)}" for m in moves]
    # Lange Namen: hinten Zeilen weglassen, bis das Feld in Discords Grenze passt
    while len("\n".join(lines)) > FIELD_LIMIT:
        lines.pop()
    return "\n".join(lines) or NO_MOVES


def daily_embed(data: dict[str, Any]) -> discord.Embed:
    embed = base_embed("Preise seit gestern", data["game"], data["league"])
    embed.add_field(name="Gewinner", value=move_lines(data["up"]), inline=False)
    embed.add_field(name="Verlierer", value=move_lines(data["down"]), inline=False)
    return embed


def price_embed(data: dict[str, Any], game: str) -> discord.Embed:
    embed = base_embed(data["name"], game, data["league"], url=data["url"], icon=data["icon"])
    embed.description = f"**{fmt_price(data['price'], data['unit'])}**"
    embed.add_field(name="24 Stunden", value=fmt_change(data["change_24h"]))
    embed.add_field(name="7 Tage", value=fmt_change(data["change_7d"]))
    return embed
