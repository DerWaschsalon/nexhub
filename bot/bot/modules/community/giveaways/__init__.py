"""Gewinnspiele: Embed mit „🎉 Teilnehmen“-Knopf (Klick an- oder abmelden), automatische Auslosung zur
Endzeit, /giveaway-reroll für neue Gewinner. Die custom_id des Knopfs trägt die Nachrichten-ID, deshalb
reicht es, nach einem Neustart je laufendem Gewinnspiel die Ansicht neu anzumelden."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule
from bot.core.clock import TZ
from bot.core.discord_checks import can_send
from bot.core.when import parse_when
from bot.errors import UserError
from bot.hubpages import Page

from .store import GiveawayStore

CHECK_EVERY_S = 60
JOIN_PREFIX = "giveaway:join:"


def mentions(user_ids: list[int]) -> str:
    return ", ".join(f"<@{u}>" for u in user_ids)


def build_giveaway_embed(prize: str, winner_count: int, ends_at: float, host_id: int | None, *,
                         ended: bool = False, winner_ids: list[int] | None = None) -> discord.Embed:
    if ended:
        e = discord.Embed(title="🎉 Giveaway beendet", description=f"**{prize}**", colour=discord.Colour.dark_grey())
        e.add_field(name="Gewinner", value=mentions(winner_ids) if winner_ids else "Niemand hat teilgenommen")
        return e
    e = discord.Embed(title="🎉 Giveaway", description=f"**{prize}**", colour=discord.Colour.gold())
    e.add_field(name="Endet", value=discord.utils.format_dt(datetime.fromtimestamp(ends_at, tz=UTC), "R"))
    e.add_field(name="Gewinner-Anzahl", value=str(winner_count))
    if host_id:
        e.add_field(name="Gestartet von", value=f"<@{host_id}>")
    return e


def result_text(prize: str, winners: list[int]) -> str:
    if winners:
        return f"🎉 Gewinner von **{prize}**: {mentions(winners)}"
    return f"😢 Niemand hat bei **{prize}** mitgemacht."


class JoinButton(discord.ui.Button["JoinView"]):
    def __init__(self, module: "Giveaways", message_id: int) -> None:
        super().__init__(label="🎉 Teilnehmen", style=discord.ButtonStyle.success,
                         custom_id=f"{JOIN_PREFIX}{message_id}")
        self.module, self.message_id = module, message_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self.module.toggle(self.message_id, interaction.user.id),
                                                ephemeral=True)


class JoinView(discord.ui.View):
    def __init__(self, module: "Giveaways", message_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(JoinButton(module, message_id))


class Giveaways(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="community.giveaways", name="Gewinnspiele", category="Community", icon="mdi-gift",
        summary="Gewinnspiel mit Teilnahme-Knopf und Auslosung zur Endzeit.",
    )

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.store = GiveawayStore(ctx.db)

    async def start(self) -> None:
        self.spawn(self.restore_views)
        self.every(CHECK_EVERY_S, self.finish_due)

    def cog(self) -> commands.Cog:
        from .commands import GiveawaysCog

        return GiveawaysCog(self)

    def pages(self) -> list[Page]:
        from .hub import giveaway_page

        return [giveaway_page(self)]

    async def restore_views(self) -> None:
        """Nach dem Start: Knöpfe laufender Gewinnspiele wieder anklickbar machen."""
        await self.client.wait_until_ready()
        for row in await self.store.running():
            self.client.add_view(JoinView(self, row["message_id"]), message_id=row["message_id"])

    async def begin(self, channel: discord.TextChannel, prize: str, duration: str, winners: int, host_id: int) -> None:
        """Gewinnspiel posten und eintragen (Befehl und Hub)."""
        if not can_send(channel):
            raise UserError(f"Ich darf in #{channel.name} nicht schreiben.")
        ends_at = parse_when(duration, datetime.now(TZ)).timestamp()
        message = await channel.send(embed=build_giveaway_embed(prize, winners, ends_at, host_id))
        view = JoinView(self, message.id)
        await message.edit(view=view)
        self.client.add_view(view, message_id=message.id)
        await self.store.add(message.id, channel.guild.id, channel.id, host_id, prize, winners, ends_at)

    async def toggle(self, message_id: int, user_id: int) -> str:
        if not await self.store.is_running(message_id):
            return "Dieses Giveaway ist schon vorbei."
        if await self.store.toggle_entry(message_id, user_id):
            return "Du nimmst jetzt teil! 🎉"
        return "Du nimmst nicht mehr teil."

    async def finish_due(self) -> None:
        for row in await self.store.due(time.time()):
            await self.finish(row)

    async def finish(self, row: Any) -> None:
        await self.store.mark_ended(row["message_id"])
        winners = await self.store.pick_winners(row["message_id"], row["winners"])
        channel = self.client.get_channel(row["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return
        ended = build_giveaway_embed(row["prize"], row["winners"], row["ends"], None, ended=True, winner_ids=winners)
        try:
            message = await channel.fetch_message(row["message_id"])
            await message.edit(embed=ended, view=None)
            await channel.send(result_text(row["prize"], winners))
        except discord.HTTPException as e:
            self.log.warning("Giveaway #%s beenden: %r", row["message_id"], e)

    async def redraw(self, row: Any) -> str:
        if not row["ended"]:
            raise UserError("Dieses Giveaway läuft noch.")
        winners = await self.store.pick_winners(row["message_id"], row["winners"])
        if not winners:
            return "Es gibt keine Teilnehmer zum Auslosen."
        channel = self.client.get_channel(row["channel_id"])
        if isinstance(channel, discord.TextChannel):
            await channel.send(f"🔁 Neu ausgelost für **{row['prize']}**: {mentions(winners)}")
        return "Neu ausgelost."

    async def remove(self, row: Any) -> None:
        """Gewinnspiel samt Post löschen."""
        channel = self.client.get_channel(row["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                await (await channel.fetch_message(row["message_id"])).delete()
            except discord.HTTPException:
                pass  # Post schon weg
        await self.store.delete(row["message_id"])
