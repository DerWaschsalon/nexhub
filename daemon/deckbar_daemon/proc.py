"""Hilfen für externe Programme."""
from __future__ import annotations

import asyncio
import logging
import shutil

log = logging.getLogger(__name__)


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


async def run(*args: str, timeout: float = 3.0) -> tuple[int, str, str]:
    """Führt ein Programm aus und liefert (returncode, stdout, stderr)."""
    try:
        p = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        return 127, "", f"{args[0]}: nicht installiert"
    try:
        out, err = await asyncio.wait_for(p.communicate(), timeout)
    except TimeoutError:
        p.kill()
        await p.wait()
        return -1, "", f"{args[0]}: Timeout nach {timeout}s"
    return p.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")
