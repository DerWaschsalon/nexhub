"""Modul Logs: hochgeladene Runs, ihre Kämpfe und die Profile der Mitspieler."""
from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from starlette.datastructures import State

from ...module import ApiModule, Runtime
from . import character_routes, routes, shared_routes
from .characters import Fetcher


def start(state: State, runtime: Runtime) -> list[Coroutine[Any, Any, None]]:
    """state.characters: holt die Profile der Mitspieler; None, wenn der Abruf der Website aus ist."""
    state.characters = Fetcher(runtime.sessionmaker, runtime.nc) if runtime.nc else None
    return [state.characters.resume()] if state.characters else []  # liegengebliebene Abrufe vom letzten Lauf


MODULE = ApiModule("logs", (routes.router, character_routes.router, shared_routes.router), start=start)
