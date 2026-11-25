"""Modul BiS-Listen: Bestand der Top-Spieler je Klasse und die Auswertung daraus."""
from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from starlette.datastructures import State

from ...module import ApiModule, Runtime
from . import routes
from .collector import BisCollector


def start(state: State, runtime: Runtime) -> list[Coroutine[Any, Any, None]]:
    return [BisCollector(runtime.sessionmaker, runtime.nc, runtime.http).run()] if runtime.nc else []


MODULE = ApiModule("bis", (routes.router,), start=start)
