"""Zugriff auf den Docker-Socket: Container auflisten, neu starten, den Bot selbst aktualisieren.

Die Docker-SDK-Aufrufe blockieren, deshalb laufen sie im Executor. Der Socket gibt praktisch
Root-Zugriff auf den Rechner; wer ihn benutzen darf, prüft das Modul (nur OWNER_ID).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from docker.errors import DockerException, NotFound

from bot.errors import UserError
from bot.serverstatus import build_recreate_config

log = logging.getLogger("thewashbot.system.status")

SOCKET = "/var/run/docker.sock"
RESTART_TIMEOUT_S = 10


def docker_available() -> bool:
    return os.path.exists(SOCKET)


class DockerHost:
    """Ein Docker-Client; legt sich erst beim ersten Aufruf an, damit der Bot ohne Socket startet."""

    def __init__(self) -> None:
        self._client: Any = None

    def client(self) -> Any:
        if self._client is None:
            import docker

            try:
                self._client = docker.from_env()
            except DockerException as ex:
                raise UserError(f"Docker-Socket nicht erreichbar: {ex}") from None
        return self._client

    async def containers(self) -> list[tuple[str, str, str]]:
        """(Name, Status, Image) aller Container."""
        client = self.client()

        def read() -> list[tuple[str, str, str]]:
            rows = []
            for c in client.containers.list(all=True):
                image = c.image.tags[0] if c.image.tags else c.image.short_id
                rows.append((c.name, c.status, image))
            return rows

        return await asyncio.get_running_loop().run_in_executor(None, read)

    async def restart(self, name: str) -> None:
        client = self.client()
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: client.containers.get(name).restart(timeout=RESTART_TIMEOUT_S))
        except DockerException as ex:
            log.warning("Neustart von %s fehlgeschlagen: %r", name, ex)
            raise UserError(f"Neustart fehlgeschlagen: {ex}") from None

    async def self_update(self, container_name: str, image_ref: str) -> None:
        client = self.client()
        await asyncio.get_running_loop().run_in_executor(None, self._self_update, client, container_name, image_ref)

    @staticmethod
    def _self_update(client: Any, container_name: str, image_ref: str) -> None:
        """Zieht das neue Image, liest die laufende Konfiguration des Bot-Containers aus, startet
        damit den Helfer-Container (siehe `selfupdate_helper.py`) und stoppt sich zuletzt selbst;
        ab da übernimmt der Helfer."""
        log.info("Selbst-Update: ziehe %s", image_ref)
        client.images.pull(image_ref)
        cfg = build_recreate_config(client.api.inspect_container(container_name), image_ref)

        helper_name = f"{container_name}-selfupdate-helper"
        try:
            client.containers.get(helper_name).remove(force=True)
        except NotFound:
            pass

        client.containers.run(
            image_ref, command=["python", "-m", "bot.selfupdate_helper"], name=helper_name,
            detach=True, remove=True,
            environment={"SELFUPDATE_OLD_NAME": container_name, "SELFUPDATE_CONFIG": json.dumps(cfg)},
            volumes={SOCKET: {"bind": SOCKET, "mode": "rw"}},
        )
        log.info("Selbst-Update: Helfer gestartet, stoppe mich selbst (%s)", container_name)
        client.api.stop(container_name, timeout=RESTART_TIMEOUT_S)
