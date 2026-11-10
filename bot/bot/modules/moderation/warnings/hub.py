"""Seite „Moderation“ im NexHub: Maßnahmen, Verwarnungen, Bann-Liste."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bot.hubpages import Action, Actions, Column, Ctx, Field, Page, Table, user_label

if TYPE_CHECKING:
    from . import Warnings

PAGE_ORDER = 10
BAN_LIMIT = 500


def by(ctx: Ctx) -> str:
    return f"{ctx.who or 'NexHub'} (NexHub)"


def moderation_page(module: "Warnings") -> Page:
    async def timeout(ctx: Ctx, v: dict[str, Any], _item: str | None) -> str:
        await module.timeout(v["member"], v["minutes"], by(ctx), v["reason"])
        return f"{v['member'].display_name} ist für {v['minutes']} Min. stumm."

    async def kick(ctx: Ctx, v: dict[str, Any], _item: str | None) -> str:
        await module.kick(v["member"], by(ctx), v["reason"])
        return f"{v['member'].display_name} wurde entfernt."

    async def ban(ctx: Ctx, v: dict[str, Any], _item: str | None) -> str:
        await module.ban(v["member"], ctx.reason, v["reason"], v["days"])
        return f"{v['member'].display_name} wurde gebannt."

    async def warnings(ctx: Ctx) -> list[dict[str, Any]]:
        return [{"id": str(r["id"]), "member": user_label(ctx.guild, r["user_id"]), "reason": r["reason"],
                 "by": user_label(ctx.guild, r["moderator_id"]), "created": r["created"]}
                for r in await module.store.of_guild(ctx.guild.id)]

    async def warn(ctx: Ctx, v: dict[str, Any], _item: str | None) -> str:
        count = await module.warn(ctx.guild, v["member"], ctx.member or ctx.guild.me, v["reason"])
        return f"{v['member'].display_name} verwarnt (Nr. {count})."

    async def warn_delete(ctx: Ctx, _v: dict[str, Any], item: str | None) -> str:
        await module.store.delete(ctx.guild.id, int(item or 0))
        return "Verwarnung gelöscht."

    async def bans(ctx: Ctx) -> list[dict[str, Any]]:
        if not ctx.guild.me.guild_permissions.ban_members:
            return []
        return [{"id": str(b.user.id), "user": b.user.name, "reason": b.reason or ""}
                async for b in ctx.guild.bans(limit=BAN_LIMIT)]

    async def unban(ctx: Ctx, _v: dict[str, Any], item: str | None) -> str:
        await module.unban(ctx.guild, int(item or 0), ctx.reason)
        return "Bann aufgehoben."

    member = Field("member", "member", "Mitglied", required=True)
    reason = Field("reason", "text", "Grund", hint="Steht im Log und in der DM an das Mitglied.")
    actions = Actions("massnahmen", "Maßnahmen", (
        Action("timeout", "Timeout", timeout, (member, Field("minutes", "int", "Minuten", default=60, min=1,
                                                             max=40320), reason)),
        Action("kick", "Kick", kick, (member, reason), confirm="Mitglied vom Server entfernen?", danger=True),
        Action("ban", "Bann", ban, (member, reason, Field("days", "int", "Nachrichten der letzten Tage löschen",
                                                         default=0, min=0, max=7)),
               confirm="Mitglied bannen?", danger=True),
    ), "Wirkt sofort und steht im Log-Kanal. Im Discord-Audit-Log steht „NexHub: <dein Name>“.")
    warning_table = Table("warnings", "Verwarnungen", (
        Column("member", "Mitglied"), Column("reason", "Grund"), Column("by", "Von"), Column("created", "Wann", "time"),
    ), warnings, create=Action("warn", "Verwarnen", warn, (member, Field("reason", "text", "Grund", required=True))),
        actions=(Action("delete", "Löschen", warn_delete, confirm="Verwarnung löschen?", danger=True),),
        empty="Keine Verwarnungen.")
    ban_table = Table("bans", "Gebannt", (Column("user", "Nutzer"), Column("reason", "Grund")), bans,
                      actions=(Action("unban", "Bann aufheben", unban, confirm="Bann aufheben?"),),
                      empty="Niemand ist gebannt.")
    return Page("moderation", "Moderation", "Moderation", (actions, warning_table, ban_table), order=PAGE_ORDER)
