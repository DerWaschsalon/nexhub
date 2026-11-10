"""Seite „Geburtstage“ im NexHub: Liste, eintragen, löschen."""

from __future__ import annotations

from typing import Any

from bot.hubpages import Action, Column, Ctx, Field, Page, Table, user_label

from . import BirthdayStore

PAGE_ORDER = 50


def birthday_page(store: BirthdayStore) -> Page:
    async def rows(ctx: Ctx) -> list[dict[str, Any]]:
        return [{"id": str(r["user_id"]), "user": user_label(ctx.guild, r["user_id"]),
                 "date": f"{r['day']:02}.{r['month']:02}."} for r in await store.of_guild(ctx.guild.id)]

    async def put(ctx: Ctx, values: dict[str, Any], _item: str | None) -> str:
        await store.put(ctx.guild.id, values["member"].id, values["day"], values["month"])
        return f"Geburtstag von {values['member'].display_name} eingetragen."

    async def delete(ctx: Ctx, _values: dict[str, Any], item: str | None) -> str:
        await store.delete(ctx.guild.id, int(item or 0))
        return "Gelöscht."

    table = Table("birthdays", "Geburtstage", (Column("user", "Mitglied"), Column("date", "Datum")), rows,
                  create=Action("set", "Eintragen", put, (
                      Field("member", "member", "Mitglied", required=True),
                      Field("day", "int", "Tag", default=1, min=1, max=31),
                      Field("month", "int", "Monat", default=1, min=1, max=12),
                  ), submit="Speichern"),
                  actions=(Action("delete", "Löschen", delete, confirm="Geburtstag löschen?", danger=True),),
                  empty="Noch keine Geburtstage eingetragen.")
    return Page("geburtstage", "Geburtstage", "Community", (table,),
                "Gratuliert wird um 9 Uhr im Kanal aus „Community“. Mitglieder tragen sich mit /geburtstag-setzen "
                "ein.", order=PAGE_ORDER)
