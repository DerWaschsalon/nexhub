"""Seite „Erinnerungen“ im NexHub: offene Erinnerungen ansehen und löschen."""

from __future__ import annotations

from typing import Any

from bot.hubpages import Action, Column, Ctx, Page, Table, channel_label, user_label

from . import ReminderStore

PAGE_ORDER = 80


def reminder_page(store: ReminderStore) -> Page:
    async def rows(ctx: Ctx) -> list[dict[str, Any]]:
        return [{"id": str(r["id"]), "user": user_label(ctx.guild, r["user_id"]), "text": r["text"], "due": r["due"],
                 "where": "per DM" if r["private"] else channel_label(ctx.guild, r["channel_id"])}
                for r in await store.of_guild(ctx.guild.id)]

    async def delete(ctx: Ctx, _values: dict[str, Any], item: str | None) -> str:
        await store.delete(ctx.guild.id, int(item or 0))
        return "Gelöscht."

    table = Table("reminders", "Offene Erinnerungen", (
        Column("user", "Für"), Column("text", "Text"), Column("due", "Fällig", "time"), Column("where", "Wo"),
    ), rows, actions=(Action("delete", "Löschen", delete, confirm="Erinnerung löschen?", danger=True),),
        empty="Keine offenen Erinnerungen.")
    return Page("erinnerungen", "Erinnerungen", "Community", (table,), "Mitglieder legen sie mit /erinnere an.",
                order=PAGE_ORDER)
