"""Externe Programme starten: mit Zeitlimit, ohne Ausnahme, wenn das Programm fehlt."""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass

MISSING = 127  # Rückgabewert wie in der Shell, wenn das Programm fehlt
TIMED_OUT = -1


@dataclass(frozen=True)
class Result:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


async def run(*args: str, timeout: float = 3.0, stdin: bytes | None = None) -> Result:
    try:
        p = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        return Result(MISSING, "", f"{args[0]}: nicht installiert")
    try:
        out, err = await asyncio.wait_for(p.communicate(stdin), timeout)
    except TimeoutError:
        p.kill()
        await p.wait()
        return Result(TIMED_OUT, "", f"{args[0]}: Timeout nach {timeout} s")
    return Result(p.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace"))
