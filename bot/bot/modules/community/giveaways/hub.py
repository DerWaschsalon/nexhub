"""Seite „Giveaways“ im NexHub: Liste, neu starten, jetzt auslosen, neu auslosen, löschen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bot.errors import UserError
from bot.hubpages import Action, Column, Ctx, Field, Page, Table, channel_label, user_label

if TYPE_CHECKING:
    from . import Giveaways

PAGE_ORDER = 40


def giveaway_page(module: "Giveaways") -> Page:
    store = module.store

    async def rows(ctx: Ctx) -> list[dict[str, Any]]:
        return [{"id": str(r["message_id"]), "prize": r["prize"], "channel": channel_label(ctx.guild, r["channel_id"]),
                 "ends": r["ends"], "entries": r["n"], "winners": r["winners"],
                 "state": "beendet" if r["ended"] else "läuft", "state_tone": "" if r["ended"] else "ok",
                 "host": user_label(ctx.guild, r["host_id"]), "active": not r["ended"], "ended": bool(r["ended"])}
                for r in await store.of_guild(ctx.guild.id)]

    async def create(ctx: Ctx, values: dict[str, Any], _item: str | None) -> str:
        await module.begin(values["channel"], values["prize"], values["duration"], values["winners"],
                           ctx.who_id or ctx.guild.me.id)
        return f"Giveaway gestartet in #{values['channel'].name}."

    async def end_now(ctx: Ctx, _values: dict[str, Any], item: str | None) -> str:
        row = await store.get(ctx.guild.id, int(item or 0))
        if row["ended"]:
            raise UserError("Das Giveaway ist schon vorbei.")
        await module.finish(row)
        return "Ausgelost."

    async def reroll(ctx: Ctx, _values: dict[str, Any], item: str | None) -> str:
        return await module.redraw(await store.get(ctx.guild.id, int(item or 0)))

    async def delete(ctx: Ctx, _values: dict[str, Any], item: str | None) -> str:
        await module.remove(await store.get(ctx.guild.id, int(item or 0)))
        return "Gelöscht."

    table = Table("giveaways", "Giveaways", (
        Column("prize", "Preis"), Column("channel", "Kanal"), Column("ends", "Endet", "time"),
        Column("entries", "Teilnehmer", "num"), Column("winners", "Gewinner", "num"),
        Column("state", "Status", "badge"),
    ), rows, create=Action("create", "Neues Giveaway", create, (
        Field("channel", "channel", "Kanal", required=True),
        Field("prize", "text", "Preis", required=True),
        Field("duration", "text", "Dauer", hint="z. B. 2h, 30m, 1d2h oder 24.12. 18:00", required=True),
        Field("winners", "int", "Anzahl Gewinner", default=1, min=1, max=20),
    ), submit="Giveaway starten"), actions=(
        Action("end", "Jetzt auslosen", end_now, confirm="Giveaway jetzt beenden und auslosen?", when="active"),
        Action("reroll", "Neu auslosen", reroll, confirm="Neue Gewinner auslosen?", when="ended"),
        Action("delete", "Löschen", delete, confirm="Giveaway samt Post löschen?", danger=True),
    ), empty="Noch keine Giveaways.")
    return Page("giveaways", "Giveaways", "Community", (table,),
                "Mit Teilnahme-Knopf in Discord, ausgelost wird automatisch zur Endzeit.", order=PAGE_ORDER)
