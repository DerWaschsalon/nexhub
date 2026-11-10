"""Starboard: Nachrichten ab einer einstellbaren Zahl ⭐ landen als Embed in einem Highlight-Kanal.

Der Stern des Autors zählt nicht (sich selbst starren gilt nicht). Hinzufügen und Entfernen von Sternen
folgt der Bot über die raw-Reaktionsereignisse, damit es auch für Nachrichten außerhalb des Caches geht.
"""

from __future__ import annotations

from typing import ClassVar

import discord
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.module import Listener

from .settings import StarboardSettings

STAR = "⭐"


def build_star_embed(message: discord.Message) -> discord.Embed:
    e = discord.Embed(description=message.content or "", colour=discord.Colour.gold(), timestamp=message.created_at)
    e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    image = next((a for a in message.attachments if a.content_type and a.content_type.startswith("image/")), None)
    if image:
        e.set_image(url=image.url)
    e.add_field(name="Original", value=f"[zur Nachricht]({message.jump_url})", inline=False)
    return e


async def star_count(message: discord.Message) -> int:
    """Sterne ohne den des Autors."""
    count = 0
    for reaction in message.reactions:
        if str(reaction.emoji) != STAR:
            continue
        async for user in reaction.users():
            if user.id != message.author.id:
                count += 1
    return count


async def delete_quietly(message: discord.Message) -> None:
    try:
        await message.delete()
    except discord.HTTPException:
        pass  # schon weg


class Starboard(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="community.starboard", name="Starboard", category="Community", icon="mdi-star",
        summary="Nachrichten ab X ⭐ landen in einem Highlight-Kanal.",
    )
    Settings = StarboardSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, StarboardSettings)

    def listeners(self) -> dict[str, Listener]:
        return {"on_raw_reaction_add": self.on_reaction, "on_raw_reaction_remove": self.on_reaction}

    async def on_reaction(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id or str(payload.emoji) != STAR:
            return
        settings = self.settings.get(payload.guild_id)
        if not settings.starboard_channel or payload.channel_id == settings.starboard_channel:
            return  # kein Starboard, oder Reaktion im Starboard selbst
        source = self.client.get_channel(payload.channel_id)
        if not isinstance(source, discord.TextChannel | discord.Thread):
            return
        try:
            message = await source.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        board = source.guild.get_channel(settings.starboard_channel)
        if isinstance(board, discord.TextChannel):
            await self.sync(message, await star_count(message), board, settings.starboard_threshold)

    async def sync(self, message: discord.Message, count: int, board: discord.TextChannel, threshold: int) -> None:
        """Post im Starboard anlegen, aktualisieren oder (unter der Schwelle) entfernen."""
        posted = await self.posted_message(board, message.id)
        if count < threshold:
            if posted:
                await delete_quietly(posted)
            await self.db.execute("DELETE FROM starboard WHERE message_id=?", (message.id,))
            return
        channel = message.channel
        where = channel.mention if isinstance(channel, discord.TextChannel | discord.Thread) else ""
        content = f"{STAR} **{count}** | {where}"
        if posted:
            try:
                await posted.edit(content=content, embed=build_star_embed(message))
                return
            except discord.HTTPException:
                pass  # Post weg oder nicht bearbeitbar: neu posten
        try:
            new = await board.send(content=content, embed=build_star_embed(message))
        except discord.HTTPException as e:
            self.log.warning("Starboard-Post in %s: %r", board.guild.id, e)
            return
        await self.db.execute(
            "INSERT INTO starboard (guild_id, message_id, star_message_id) VALUES (?, ?, ?) "
            "ON CONFLICT(message_id) DO UPDATE SET star_message_id=excluded.star_message_id",
            (board.guild.id, message.id, new.id))

    async def posted_message(self, board: discord.TextChannel, message_id: int) -> discord.Message | None:
        row = await self.db.fetchone("SELECT star_message_id FROM starboard WHERE message_id=?", (message_id,))
        if row is None or not row["star_message_id"]:
            return None
        try:
            return await board.fetch_message(row["star_message_id"])
        except discord.HTTPException:
            return None
