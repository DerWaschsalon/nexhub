"""Server-Status: CPU, RAM, Laufzeit, Festplatte, Container neu starten und den Bot-Container per
Docker-Socket selbst aktualisieren (/server, /server-update und die Seite im Hub).

Die Befehle sind nur für OWNER_ID (Env): Der Docker-Socket gibt praktisch Root-Zugriff auf den
Rechner, deshalb bewusst eine einzelne Person statt einer Rolle wie bei /setup.
"""

from __future__ import annotations

import os
from typing import ClassVar

from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule
from bot.errors import UserError
from bot.hubpages import Page

from .docker_host import DockerHost

SELF_UPDATE_IMAGE = "ghcr.io/derwaschsalon/thewashbot:latest"


def is_owner(user_id: int) -> bool:
    owner_id = os.getenv("OWNER_ID", "").strip()
    return owner_id.isdigit() and user_id == int(owner_id)


def require_owner(user_id: int) -> None:
    if not is_owner(user_id):
        raise UserError("Das geht nur für den Bot-Besitzer (`OWNER_ID` in der `.env`).")


def self_container_name() -> str:
    return os.getenv("SELF_CONTAINER_NAME", "thewashbot").strip()


class ServerStatus(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="system.status", name="Server-Status", category="System", icon="mdi-server",
        summary="Werte des Rechners, Container neu starten, Bot aktualisieren.", default=True,
    )

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.docker = DockerHost()

    def cog(self) -> commands.Cog:
        from .commands import StatusCog

        return StatusCog(self)

    def pages(self) -> list[Page]:
        from .hub import status_page

        return [status_page(self)]

    def start_self_update(self) -> None:
        """Startet das Update im Hintergrund; der Bot geht dabei kurz offline."""
        self.spawn(self._self_update)

    async def _self_update(self) -> None:
        try:
            await self.docker.self_update(self_container_name(), SELF_UPDATE_IMAGE)
        except Exception:
            self.log.exception("Selbst-Update fehlgeschlagen")

    def latency_ms(self) -> int | None:
        latency = self.client.latency
        # discord.py liefert NaN, solange noch kein Heartbeat zurückkam
        if latency != latency:
            return None
        return round(latency * 1000)


__all__ = ["SELF_UPDATE_IMAGE", "ServerStatus"]
