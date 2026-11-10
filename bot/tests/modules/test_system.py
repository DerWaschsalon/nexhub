"""System-Modul: Server-Status nur für OWNER_ID, Container-Feld ohne Docker-Socket."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import discord
import pytest
from nexcore import EventBus, Paths

from bot.core import BotContext
from bot.db import Database
from bot.errors import UserError
from bot.modules.system.status import ServerStatus, is_owner, require_owner
from bot.modules.system.status.commands import StatusCog


def test_only_owner_may_use_server_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_ID", "42")
    assert is_owner(42)
    assert not is_owner(7)
    with pytest.raises(UserError):
        require_owner(7)
    monkeypatch.setenv("OWNER_ID", "")
    assert not is_owner(42)  # ohne OWNER_ID darf niemand


def test_container_field_explains_missing_docker() -> None:
    client = MagicMock(spec=discord.Client)
    module = ServerStatus(BotContext(bus=EventBus(), paths=Paths("test"), db=MagicMock(spec=Database),
                                     client=client))

    def no_socket() -> None:
        raise UserError("Docker-Socket nicht erreichbar")

    module.docker.client = no_socket  # type: ignore[method-assign]
    name, value = asyncio.run(StatusCog(module)._container_field())
    assert name == "Container"
    assert "Docker-Socket" in value


def test_latency_unknown_before_first_heartbeat() -> None:
    client = MagicMock(spec=discord.Client)
    client.latency = float("nan")
    module = ServerStatus(BotContext(bus=EventBus(), paths=Paths("test"), db=MagicMock(spec=Database),
                                     client=client))
    assert module.latency_ms() is None
    client.latency = 0.0421
    assert module.latency_ms() == 42
