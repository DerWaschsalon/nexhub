"""Modul Armory: eingetragene Charaktere mit Verlauf, Bewertung gegen Top-Spieler, Upgrade-Plan, Vergleich."""
from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from starlette.datastructures import State

from ...module import ApiModule, Runtime
from . import rating_routes, routes, shared_routes, upgrade_routes
from .census import Census
from .service import Armory, armory_ids


def start(state: State, runtime: Runtime) -> list[Coroutine[Any, Any, None]]:
    """state.armory: ruft Armory-Charaktere ab; None, wenn der Abruf der Website aus ist."""
    state.armory_ids = armory_ids  # damit das Modul Logs zu Mitspielern auf die Armory verweisen kann
    state.armory = Armory(runtime.sessionmaker, runtime.nc) if runtime.nc else None
    if not state.armory:
        return []
    # der tägliche Abruf und die Zählung der Top-Spieler für die Bewertung
    return [state.armory.daily(), Census(runtime.sessionmaker, runtime.http).daily()]


MODULE = ApiModule("armory", (routes.router, upgrade_routes.router, rating_routes.router, shared_routes.router),
                   requires=("logs", "bis"), start=start)
