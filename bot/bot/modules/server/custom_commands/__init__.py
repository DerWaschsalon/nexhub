"""Eigene Befehle: `!name` im Chat antwortet mit einem hinterlegten Text. Platzhalter {user}
(Erwähnung) und {server} (Servername). Reine Text-Auslöser über on_message, keine Slash-Befehle."""

from __future__ import annotations

import re
from typing import Any, ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule
from bot.core.module import Listener
from bot.db import Database
from bot.errors import UserError

NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
PREFIX = "!"


def render(response: str, member: discord.abc.User, guild: discord.Guild) -> str:
    return response.replace("{user}", member.mention).replace("{server}", guild.name)


def clean_name(name: str) -> str:
    """„!Hallo “ → „hallo“; ungültige Namen: UserError."""
    name = name.strip().lower().lstrip(PREFIX)
    if not NAME_RE.match(name):
        raise UserError("Name darf nur a-z, 0-9, „_“ und „-“ enthalten (höchstens 32 Zeichen).")
    return name


def command_name(content: str) -> str:
    """Name des Befehls aus einer Nachricht wie „!regeln bitte“, sonst ''."""
    if not content.startswith(PREFIX):
        return ""
    words = content[len(PREFIX):].split()
    return words[0].lower() if words else ""


class CommandStore:
    """Eigene Befehle in der Datenbank; geteilt von Befehlen, Chat und Hub."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def response(self, guild_id: int, name: str) -> str | None:
        row = await self.db.fetchone("SELECT response FROM custom_commands WHERE guild_id=? AND name=?",
                                     (guild_id, name))
        return None if row is None else str(row["response"])

    async def put(self, guild_id: int, name: str, response: str) -> str:
        name = clean_name(name)
        await self.db.execute(
            "INSERT INTO custom_commands (guild_id, name, response) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, name) DO UPDATE SET response=excluded.response", (guild_id, name, response))
        return name

    async def delete(self, guild_id: int, name: str) -> str:
        name = name.strip().lower().lstrip(PREFIX)
        if await self.response(guild_id, name) is None:
            raise UserError(f"Es gibt keinen Befehl `!{name}`.")
        await self.db.execute("DELETE FROM custom_commands WHERE guild_id=? AND name=?", (guild_id, name))
        return name

    async def of_guild(self, guild_id: int) -> list[Any]:
        return await self.db.fetchall("SELECT name, response FROM custom_commands WHERE guild_id=? ORDER BY name",
                                      (guild_id,))


class CustomCommands(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="server.custom_commands", name="Eigene Befehle", category="Server", icon="mdi-console-line",
        summary="!name im Chat antwortet mit einem hinterlegten Text.",
    )

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.store = CommandStore(ctx.db)

    def listeners(self) -> dict[str, Listener]:
        return {"on_message": self.on_message}

    def cog(self) -> commands.Cog:
        from .commands import CustomCommandsCog

        return CustomCommandsCog(self)

    async def on_message(self, message: discord.Message) -> None:
        name = command_name(message.content)
        if message.author.bot or message.guild is None or not name:
            return
        response = await self.store.response(message.guild.id, name)
        if response is None:
            return
        try:
            await message.channel.send(render(response, message.author, message.guild))
        except discord.HTTPException as e:
            self.log.debug("!%s in %s: %r", name, message.channel.id, e)
