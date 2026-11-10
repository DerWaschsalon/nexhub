"""Seite „GitHub & YouTube“ im NexHub: Feeds anlegen, pausieren, testen, löschen, jetzt prüfen."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from bot.errors import UserError
from bot.hubpages import Action, Actions, Column, Ctx, Field, Page, Table, channel_label

from .providers.base import ProviderError
from .providers.manager import PROVIDERS

if TYPE_CHECKING:
    from . import NotificationFeeds

PAGE_ORDER = 10


def create_fields() -> tuple[Field, ...]:
    """Formular „Neue Benachrichtigung“: je Dienst eigene Felder, sichtbar nur bei diesem Dienst."""
    fields = [Field("kind", "choice", "Dienst", default=next(iter(PROVIDERS)),
                    options=tuple((k, p.label) for k, p in PROVIDERS.items()))]
    for key, p in PROVIDERS.items():
        when = ("kind", (key,))
        fields.append(Field(f"source_{key}", "text", p.source_label, hint=p.source_help, required=True, show_if=when))
        fields.append(Field(f"events_{key}", "multi", "Ereignisse", options=tuple(p.events.items()),
                            default=list(p.events)[:1], required=True, show_if=when))
        fields.extend(Field(f"filter_{key}_{f.key}", f.kind, f.label, hint=f.hint, default=f.default, show_if=when)
                      for f in p.filter_fields)
    fields.append(Field("channel", "channel", "Kanal", required=True))
    return tuple(fields)


def feed_row(ctx: Ctx, f: Any) -> dict[str, Any]:
    p = PROVIDERS.get(f["kind"])
    events = json.loads(f["events"] or "[]")
    if f["error"]:
        state, tone = "Fehler", "danger"
    elif f["enabled"]:
        state, tone = "aktiv", "ok"
    else:
        state, tone = "pausiert", "warn"
    return {"id": str(f["id"]), "service": p.label if p else f["kind"], "source": f["source"],
            "events": ", ".join(p.events.get(e, e) if p else e for e in events),
            "channel": channel_label(ctx.guild, f["channel_id"]), "state": state, "state_tone": tone,
            "error": f["error"], "enabled": bool(f["enabled"]), "disabled": not f["enabled"]}


def feeds_page(module: "NotificationFeeds") -> Page:
    db = module.db

    async def one(ctx: Ctx, item: str | None) -> Any:
        feed = await db.fetchone("SELECT * FROM feeds WHERE id=? AND guild_id=?", (int(item or 0), ctx.guild.id))
        if feed is None:
            raise UserError("Die Benachrichtigung gibt es nicht mehr.")
        return feed

    async def rows(ctx: Ctx) -> list[dict[str, Any]]:
        return [feed_row(ctx, f) for f in await db.fetchall("SELECT * FROM feeds WHERE guild_id=? ORDER BY id",
                                                             (ctx.guild.id,))]

    async def create(ctx: Ctx, v: dict[str, Any], _item: str | None) -> str:
        kind = v["kind"]
        p = PROVIDERS[kind]
        try:
            source = await p.validate_source(v[f"source_{kind}"])
        except ProviderError as e:
            raise UserError(str(e)) from None
        filters = p.filters_from({f.key: v.get(f"filter_{kind}_{f.key}") for f in p.filter_fields})
        feed_id = await db.execute(
            "INSERT INTO feeds (guild_id, channel_id, kind, source, events, filters, enabled, state) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, '{}')",
            (ctx.guild.id, v["channel"].id, kind, source, json.dumps(v[f"events_{kind}"]), json.dumps(filters)))
        feed = await db.fetchone("SELECT * FROM feeds WHERE id=?", (feed_id,))
        await module.manager.poll_feed(feed, module.client)  # stiller Abgleich: Bestehendes gilt nicht als neu
        return f"{p.label}: {source} geht jetzt nach #{v['channel'].name}."

    async def toggle(ctx: Ctx, _v: dict[str, Any], item: str | None) -> str:
        feed = await one(ctx, item)
        await db.execute("UPDATE feeds SET enabled=?, error=NULL WHERE id=?", (0 if feed["enabled"] else 1, feed["id"]))
        return "Pausiert." if feed["enabled"] else "Läuft wieder."

    async def test(ctx: Ctx, _v: dict[str, Any], item: str | None) -> str:
        feed = await one(ctx, item)
        provider = PROVIDERS.get(feed["kind"])
        channel = ctx.guild.get_channel(feed["channel_id"])
        if provider is None or channel is None or not hasattr(channel, "send"):
            raise UserError("Dienst oder Ziel-Kanal gibt es nicht mehr.")
        try:
            n = await provider.test_notification(feed["source"], json.loads(feed["events"] or "[]"))
        except ProviderError as e:
            raise UserError(str(e)) from None
        n.embed.add_field(name="🧪 Hinweis", value="Dies ist eine Testbenachrichtigung von TheWashbot.", inline=False)
        await channel.send(embed=n.embed)
        return f"Test in #{channel.name} gesendet."

    async def delete(ctx: Ctx, _v: dict[str, Any], item: str | None) -> str:
        feed = await one(ctx, item)
        await db.execute("DELETE FROM feeds WHERE id=?", (feed["id"],))
        return "Gelöscht."

    async def check(ctx: Ctx, _v: dict[str, Any], _item: str | None) -> str:
        checked, posted = await module.poll_all(ctx.guild.id)
        return f"{checked} geprüft, {posted} neue Meldung(en) gepostet."

    from . import POLL_MINUTES

    table = Table("feeds", "Benachrichtigungen", (
        Column("service", "Dienst"), Column("source", "Quelle"), Column("events", "Ereignisse"),
        Column("channel", "Kanal"), Column("state", "Status", "badge"),
    ), rows, create=Action("create", "Neue Benachrichtigung", create, create_fields(), submit="Anlegen"), actions=(
        Action("pause", "Pausieren", toggle, when="enabled"),
        Action("resume", "Fortsetzen", toggle, when="disabled"),
        Action("test", "Test senden", test),
        Action("delete", "Löschen", delete, confirm="Benachrichtigung löschen?", danger=True),
    ), empty="Noch keine Benachrichtigungen.")
    check_now = Actions("pruefen", "Jetzt prüfen", (Action("check", "Alle aktiven jetzt abfragen", check),),
                        f"Sonst fragt der Bot alle {POLL_MINUTES} Minuten nach.")
    return Page("benachrichtigungen", "GitHub & YouTube", "Benachrichtigungen", (table, check_now),
                "Neue Releases, Issues, Pull Requests, Commits oder Videos in einen Kanal posten.", order=PAGE_ORDER)
