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


def test_server_cpu_and_memory_calculations() -> None:
    from bot.serverstatus import cpu_percent_from_samples, parse_meminfo, ram_usage_kb

    # user nice system idle iowait irq softirq steal (verkürzt, Rest wird ignoriert)
    a = [100, 0, 50, 800, 50, 0, 0, 0]
    b = [150, 0, 70, 820, 60, 0, 0, 0]  # delta_total=100, delta_idle(idle+iowait)=30 -> 70% genutzt
    assert cpu_percent_from_samples(a, b) == 70.0
    assert cpu_percent_from_samples(a, a) == 0.0  # keine Zeit vergangen -> 0 statt Division durch 0

    meminfo_text = "MemTotal:       16000000 kB\nMemFree:         2000000 kB\nMemAvailable:    8000000 kB\n"
    info = parse_meminfo(meminfo_text)
    assert info == {"MemTotal": 16000000, "MemFree": 2000000, "MemAvailable": 8000000}
    used, total = ram_usage_kb(info)
    assert (used, total) == (8000000, 16000000)  # über MemAvailable, nicht MemFree


def test_server_fmt_bytes_and_uptime() -> None:
    from bot.serverstatus import fmt_bytes, format_uptime

    assert fmt_bytes(500) == "500 B"
    assert fmt_bytes(2048) == "2.0 KB"
    assert fmt_bytes(5 * 1024 * 1024 * 1024) == "5.0 GB"

    assert format_uptime(90) == "1 Min."
    assert format_uptime(3 * 3600 + 90) == "3 Std. 1 Min."
    assert format_uptime(2 * 86400 + 3 * 3600) == "2 Tag(e) 3 Std."


def test_server_build_recreate_config_translates_inspect_data() -> None:
    from bot.serverstatus import build_recreate_config

    inspect_data = {
        "Name": "/thewashbot",
        "Config": {
            "Env": ["DISCORD_TOKEN=secret", "LOG_LEVEL=INFO"],
            "Labels": {"com.docker.compose.project": "thewashbot"},
            "ExposedPorts": {"8787/tcp": {}, "8789/tcp": {}},
        },
        "HostConfig": {
            "Binds": ["/mnt/user/appdata/thewashbot/data:/data"],
            "PortBindings": {
                "8787/tcp": [{"HostIp": "", "HostPort": "8787"}],
                "8789/tcp": [{"HostIp": "", "HostPort": "8789"}],
            },
            "RestartPolicy": {"Name": "unless-stopped", "MaximumRetryCount": 0},
            "NetworkMode": "bridge",
        },
    }
    cfg = build_recreate_config(inspect_data, "ghcr.io/derwaschsalon/thewashbot:v2")
    assert cfg["name"] == "thewashbot"  # führender "/" aus dem Inspect-Namen entfernt
    assert cfg["image"] == "ghcr.io/derwaschsalon/thewashbot:v2"
    assert cfg["environment"] == ["DISCORD_TOKEN=secret", "LOG_LEVEL=INFO"]
    assert cfg["host_config_kwargs"]["binds"] == ["/mnt/user/appdata/thewashbot/data:/data"]
    assert cfg["host_config_kwargs"]["port_bindings"] == {"8787/tcp": "8787", "8789/tcp": "8789"}
    assert cfg["host_config_kwargs"]["restart_policy"]["Name"] == "unless-stopped"
    assert cfg["host_config_kwargs"]["network_mode"] == "bridge"

    # Fehlende/leere Felder (z. B. ein ganz schlicht konfigurierter Container) crashen nicht
    minimal = build_recreate_config({"Name": "x", "Config": {}, "HostConfig": {}}, "img:latest")
    assert minimal["host_config_kwargs"]["restart_policy"] == {"Name": "unless-stopped"}
    assert minimal["host_config_kwargs"]["port_bindings"] == {}


