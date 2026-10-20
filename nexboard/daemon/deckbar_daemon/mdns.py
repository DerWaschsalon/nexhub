"""Kündigt den Daemon per mDNS/DNS-SD als _deckbar._tcp an."""
from __future__ import annotations

import ipaddress
import logging
import socket

import ifaddr
from zeroconf import IPVersion
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

log = logging.getLogger(__name__)

SERVICE = "_deckbar._tcp.local."


def lan_addresses() -> list[str]:
    addrs = []
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if not ip.is_IPv4:
                continue
            a = ipaddress.ip_address(ip.ip)
            # Loopback, Link-Local und Container-/VPN-Bridges bringen dem ESP32 nichts
            if a.is_loopback or a.is_link_local:
                continue
            if adapter.nice_name.startswith(("docker", "br-", "veth", "virbr", "tailscale")):
                continue
            addrs.append(str(a))
    return addrs


class Announcer:
    def __init__(self, name: str, port: int) -> None:
        self.name = name
        self.port = port
        self.zc: AsyncZeroconf | None = None
        self.info: AsyncServiceInfo | None = None

    async def start(self) -> None:
        addrs = lan_addresses()
        if not addrs:
            log.warning("mDNS: keine LAN-Adresse gefunden, Ankündigung übersprungen")
            return
        host = socket.gethostname().split(".")[0]
        self.info = AsyncServiceInfo(
            SERVICE,
            f"{self.name} ({host}).{SERVICE}",
            addresses=[socket.inet_aton(a) for a in addrs],
            port=self.port,
            properties={"path": "/ws", "v": "1"},
            server=f"{host}.local.",
        )
        self.zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        await self.zc.async_register_service(self.info, allow_name_change=True)
        log.info("mDNS: %s auf %s:%d", SERVICE, ", ".join(addrs), self.port)

    async def stop(self) -> None:
        if self.zc and self.info:
            await self.zc.async_unregister_service(self.info)
            await self.zc.async_close()
