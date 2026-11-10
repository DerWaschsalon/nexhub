"""/server, /server-neustart und /server-update (nur für OWNER_ID)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.core.confirm import Confirm
from bot.errors import UserError
from bot.serverstatus import fmt_bytes, format_uptime

from . import SELF_UPDATE_IMAGE, require_owner, self_container_name
from .host_stats import read_host_stats

if TYPE_CHECKING:
    from . import ServerStatus

FIELD_LIMIT = 1024


class StatusCog(ModuleCog):
    module: ServerStatus

    @app_commands.command(name="server", description="Server-Status: CPU/RAM/Uptime/Festplatte, laufende Container")
    async def status(self, interaction: discord.Interaction) -> None:
        require_owner(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        st = await read_host_stats()

        e = discord.Embed(title="🖥️ Server-Status", colour=discord.Colour.blurple())
        e.add_field(name="CPU", value=f"{st.cpu:.0f}%")
        e.add_field(name="RAM", value=f"{fmt_bytes(st.ram[0])} / {fmt_bytes(st.ram[1])}")
        e.add_field(name="Uptime", value=format_uptime(st.uptime))
        e.add_field(name="Festplatte (/data)", value=f"{fmt_bytes(st.disk[0])} / {fmt_bytes(st.disk[1])}")
        name, value = await self._container_field()
        e.add_field(name=name, value=value, inline=False)
        await interaction.followup.send(embed=e)

    async def _container_field(self) -> tuple[str, str]:
        """Überschrift und Text des Container-Felds; ohne Docker-Socket der Grund dafür."""
        try:
            containers = await self.module.docker.containers()
        except UserError as ex:
            return "Container", str(ex)
        lines = []
        for name, state, image in containers:
            dot = "🟢" if state == "running" else "🔴"
            lines.append(f"{dot} **{name}** ({image}) – {state}")
        text = "\n".join(lines)[:FIELD_LIMIT] or "–"
        return f"Container ({len(containers)})", text

    @app_commands.command(name="server-neustart", description="Einen Container neu starten (nicht der Bot selbst)")
    @app_commands.describe(container="Name des Containers, siehe /server")
    async def restart_container(self, interaction: discord.Interaction, container: str) -> None:
        require_owner(interaction.user.id)
        self.module.docker.client()  # meldet einen fehlenden Socket vor der Rückfrage
        confirm = Confirm(interaction.user.id, f"„{container}“ neu starten")
        await interaction.response.send_message(f"**{container}** wirklich neu starten?", view=confirm, ephemeral=True)
        await confirm.wait()
        if not confirm.confirmed:
            return
        try:
            await self.module.docker.restart(container)
        except UserError as ex:
            await interaction.followup.send(str(ex), ephemeral=True)
            return
        await interaction.followup.send(f"**{container}** neu gestartet.", ephemeral=True)

    @app_commands.command(name="server-update",
                          description="Bot-Container mit dem neuesten Image von GHCR aktualisieren")
    async def update_self(self, interaction: discord.Interaction) -> None:
        require_owner(interaction.user.id)
        self.module.docker.client()
        confirm = Confirm(interaction.user.id, "Jetzt aktualisieren")
        await interaction.response.send_message(
            f"⚠️ Zieht `{SELF_UPDATE_IMAGE}` und startet **{self_container_name()}** damit neu. Der Bot ist dabei "
            "kurz offline. Falls etwas schiefgeht: auf unraid-server `cd /mnt/user/appdata/thewashbot && "
            "docker compose up -d`.", view=confirm, ephemeral=True,
        )
        await confirm.wait()
        if not confirm.confirmed:
            return
        await interaction.followup.send("⏳ Update läuft, der Bot geht gleich kurz offline …", ephemeral=True)
        try:
            await self.module.docker.self_update(self_container_name(), SELF_UPDATE_IMAGE)
        except Exception as ex:
            self.module.log.exception("Selbst-Update fehlgeschlagen")
            await interaction.followup.send(f"Update fehlgeschlagen: {ex}", ephemeral=True)
