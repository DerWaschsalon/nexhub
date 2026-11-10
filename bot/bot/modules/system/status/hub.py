"""Seite „Server-Status“ im NexHub: Kennzahlen, Container, Bot aktualisieren."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from bot.hubpages import Action, Actions, Block, Column, Ctx, Page, Status, Table
from bot.serverstatus import fmt_bytes, format_uptime

from .docker_host import docker_available
from .host_stats import read_host_stats

if TYPE_CHECKING:
    from . import ServerStatus

PAGE_ORDER = 10


def status_page(module: ServerStatus) -> Page:
    async def stats(_ctx: Ctx) -> list[dict[str, Any]]:
        st = await read_host_stats()
        latency = module.latency_ms()
        items: list[dict[str, Any]] = [
            {"label": "CPU", "value": f"{st.cpu:.0f} %"},
            {"label": "RAM", "value": f"{fmt_bytes(st.ram[0])} / {fmt_bytes(st.ram[1])}"},
            {"label": "Festplatte", "value": f"{fmt_bytes(st.disk[0])} / {fmt_bytes(st.disk[1])}"},
            {"label": "Rechner läuft seit", "value": format_uptime(st.uptime)},
            {"label": "Discord-Latenz", "value": "–" if latency is None else f"{latency} ms"},
            {"label": "Version", "value": os.getenv("GIT_REV", "dev")},
        ]
        if not docker_available():
            items.append({"label": "Container", "value": "kein Docker-Socket eingebunden"})
        return items

    async def containers(_ctx: Ctx) -> list[dict[str, Any]]:
        rows = []
        for name, state, image in await module.docker.containers():
            tone = "ok" if state == "running" else "danger"
            rows.append({"id": name, "name": name, "image": image, "state": state, "state_tone": tone})
        return rows

    async def restart(_ctx: Ctx, _values: dict[str, Any], item: str | None) -> str:
        name = item or ""
        await module.docker.restart(name)
        return f"{name} neu gestartet."

    async def update(_ctx: Ctx, _values: dict[str, Any], _item: str | None) -> str:
        module.start_self_update()
        return "Update läuft, der Bot ist gleich kurz offline."

    blocks: list[Block] = [Status("host", "Server", stats, description="Werte des Rechners, auf dem der Bot läuft.")]
    if docker_available():
        blocks.append(Table(
            "containers", "Container",
            (Column("name", "Name"), Column("image", "Image"), Column("state", "Status", "badge")), containers,
            actions=(Action("restart", "Neu starten", restart, confirm="Container neu starten?", danger=True),),
            empty="Keine Container gefunden."))
        blocks.append(Actions("update", "Bot aktualisieren", (
            Action("self_update", "Neuestes Image holen und neu starten", update, danger=True,
                   confirm="Bot jetzt aktualisieren? Er ist dabei kurz offline."),
        ), "Zieht das neueste Bot-Image. Auf dem VPS rollt nexhub-update den Bot aus, dort nicht nötig."))
    return Page("server", "Server-Status", "System", tuple(blocks), order=PAGE_ORDER)
