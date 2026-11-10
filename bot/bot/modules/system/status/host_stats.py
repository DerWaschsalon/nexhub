"""Kennzahlen des Rechners aus /proc: CPU, RAM, Laufzeit, Festplatte."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass

from bot.serverstatus import cpu_percent_from_samples, parse_meminfo, ram_usage_kb

CPU_SAMPLE_S = 0.3


@dataclass(frozen=True)
class HostStats:
    cpu: float
    ram: tuple[int, int]  # benutzt, gesamt in Byte
    uptime: float  # Sekunden
    disk: tuple[int, int]  # benutzt, gesamt in Byte


def _cpu_line() -> list[int]:
    with open("/proc/stat") as f:
        return [int(x) for x in f.readline().split()[1:]]


async def read_cpu_percent() -> float:
    loop = asyncio.get_running_loop()
    first = await loop.run_in_executor(None, _cpu_line)
    await asyncio.sleep(CPU_SAMPLE_S)
    second = await loop.run_in_executor(None, _cpu_line)
    return cpu_percent_from_samples(first, second)


async def read_host_stats() -> HostStats:
    cpu = await read_cpu_percent()
    with open("/proc/meminfo") as f:
        used_kb, total_kb = ram_usage_kb(parse_meminfo(f.read()))
    with open("/proc/uptime") as f:
        uptime = float(f.readline().split()[0])
    disk = shutil.disk_usage("/data" if os.path.isdir("/data") else "/")
    return HostStats(cpu, (used_kb * 1024, total_kb * 1024), uptime, (disk.used, disk.total))
