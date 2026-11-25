"""Modul Parses: wie gut der DPS eines Spielers an einem Boss war, gegen Abyss Logs (EU) und gegen die Gilde."""
from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from starlette.datastructures import State

from ...module import ApiModule, Runtime
from . import routes
from .fetcher import ParseFetcher


def start(state: State, runtime: Runtime) -> list[Coroutine[Any, Any, None]]:
    return [ParseFetcher(runtime.sessionmaker, runtime.http).run()]


MODULE = ApiModule("parses", (routes.router,), requires=("logs", "bis"), start=start)
