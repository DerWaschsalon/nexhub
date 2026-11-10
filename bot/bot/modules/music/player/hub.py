"""Seite „Musik“ im NexHub: Läuft gerade mit Steuerung, Abspielen, Warteschlange."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from bot.errors import UserError
from bot.hubpages import Action, Actions, Column, Ctx, Field, Page, Status, Table, user_label

from .player import LOOP_LABELS, Player, fmt_time
from .sources import resolve

if TYPE_CHECKING:
    from . import MusicPlayer

PAGE_ORDER = 10
QUEUE_LIMIT = 200


def music_page(module: "MusicPlayer") -> Page:
    def player_of(ctx: Ctx) -> Player:
        player = module.players.get(ctx.guild.id)
        if player is None or player.voice() is None:
            raise UserError("Gerade läuft nichts.")
        return player

    async def now(ctx: Ctx) -> list[dict[str, Any]]:
        player = module.players.get(ctx.guild.id)
        vc = player.voice() if player else None
        if player is None or vc is None or player.current is None:
            return [{"label": "Status", "value": "Gerade läuft nichts."}]
        t = player.current
        return [
            {"label": "Titel", "value": t.title, "href": t.page_url},
            {"label": "Länge", "value": "Live" if t.live else fmt_time(t.duration)},
            {"label": "Gewünscht von", "value": user_label(ctx.guild, t.requester_id)},
            {"label": "Kanal", "value": vc.channel.name if vc.channel else "–"},
            {"label": "Lautstärke", "value": f"{round(player.volume * 100)} %"},
            {"label": "Wiederholen", "value": LOOP_LABELS[player.loop]},
            {"label": "Status", "value": "pausiert" if vc.is_paused() else "spielt"},
            {"active": True, "playing": vc.is_playing(), "paused": vc.is_paused()},
        ]

    async def queue(ctx: Ctx) -> list[dict[str, Any]]:
        player = module.players.get(ctx.guild.id)
        if player is None:
            return []
        return [{"id": str(i), "pos": i, "title": t.title, "length": fmt_time(t.duration),
                 "by": user_label(ctx.guild, t.requester_id)} for i, t in enumerate(player.queue[:QUEUE_LIMIT], 1)]

    async def play(ctx: Ctx, v: dict[str, Any], _item: str | None) -> str:
        tracks, name = await resolve(v["query"], ctx.who_id or ctx.guild.me.id, module.http())
        player = await module.join(ctx.guild, v["channel"], stay_if_busy=True)
        module.add(player, tracks, front=v["front"])
        await player.refresh_np()
        if len(tracks) > 1:
            return f"{len(tracks)} Titel hinzugefügt" + (f" aus {name}" if name else "") + "."
        return f"„{tracks[0].title}“ hinzugefügt."

    async def pause(ctx: Ctx, _v: dict[str, Any], _i: str | None) -> str:
        vc = player_of(ctx).voice()
        if vc:
            vc.pause()
        return "Pausiert."

    async def resume(ctx: Ctx, _v: dict[str, Any], _i: str | None) -> str:
        vc = player_of(ctx).voice()
        if vc:
            vc.resume()
        return "Weiter geht's."

    async def skip(ctx: Ctx, _v: dict[str, Any], _i: str | None) -> str:
        player_of(ctx).skip()
        return "Übersprungen."

    async def shuffle(ctx: Ctx, _v: dict[str, Any], _i: str | None) -> str:
        player = player_of(ctx)
        random.shuffle(player.queue)
        await player.refresh_np()
        return "Gemischt."

    async def volume(ctx: Ctx, v: dict[str, Any], _i: str | None) -> str:
        player = player_of(ctx)
        player.set_volume(v["percent"] / 100)
        await player.refresh_np()
        return f"Lautstärke {v['percent']} %."

    async def loop(ctx: Ctx, v: dict[str, Any], _i: str | None) -> str:
        player = player_of(ctx)
        player.loop = v["mode"]
        await player.refresh_np()
        return f"Wiederholen: {LOOP_LABELS[player.loop]}."

    async def stop(ctx: Ctx, _v: dict[str, Any], _i: str | None) -> str:
        player_of(ctx)
        await module.disconnect(ctx.guild)
        return "Gestoppt."

    async def remove(ctx: Ctx, _v: dict[str, Any], item: str | None) -> str:
        player = player_of(ctx)
        pos = int(item or 0)
        if not 1 <= pos <= len(player.queue):
            raise UserError("Den Titel gibt es nicht mehr in der Warteschlange.")
        track = player.queue.pop(pos - 1)
        await player.refresh_np()
        return f"„{track.title}“ entfernt."

    status = Status("jetzt", "Läuft gerade", now, (
        Action("pause", "Pause", pause, when="playing"),
        Action("resume", "Weiter", resume, when="paused"),
        Action("skip", "Überspringen", skip, when="active"),
        Action("shuffle", "Mischen", shuffle, when="active"),
        Action("volume", "Lautstärke", volume, (Field("percent", "int", "Lautstärke in %", default=60, min=0,
                                                      max=150),), when="active"),
        Action("loop", "Wiederholen", loop, (Field("mode", "choice", "Modus", default="aus",
                                                   options=tuple(LOOP_LABELS.items())),), when="active"),
        Action("stop", "Stoppen", stop, confirm="Musik stoppen und Kanal verlassen?", danger=True, when="active"),
    ))
    play_form = Actions("abspielen", "Abspielen", (Action("play", "Abspielen", play, (
        Field("channel", "voice", "Sprachkanal", required=True, hint="Spielt der Bot schon woanders, bleibt er dort."),
        Field("query", "text", "Link oder Suche", required=True, hint="YouTube, SoundCloud, Spotify oder Suchbegriff"),
        Field("front", "bool", "An den Anfang der Warteschlange"),
    )),))
    queue_table = Table("queue", "Warteschlange", (
        Column("pos", "#", "num"), Column("title", "Titel"), Column("length", "Länge"), Column("by", "Gewünscht von"),
    ), queue, actions=(Action("remove", "Entfernen", remove),), empty="Die Warteschlange ist leer.")
    return Page("musik", "Musik", "Musik", (status, play_form, queue_table),
                "Steuert die Wiedergabe für alle im Sprachkanal, wie die DJ-Rolle in Discord.", order=PAGE_ORDER)
