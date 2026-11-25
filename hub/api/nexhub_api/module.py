"""Was ein Modul der Hub-API ist: seine Routen und, falls nötig, seine Hintergrundaufgaben.

Jedes Modul liegt in modules/<id>/ (Routen, Fachlogik, Tabellen) und trägt dieselbe Kennung wie sein Gegenstück
im Web (hub/web/src/modules/<id>). Importieren darf es den Kern und die Module, die es in `requires` nennt;
das prüft tests/test_module_boundaries.py.
"""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import State

from .aion2 import NC
from .config import Settings


@dataclass(frozen=True)
class Runtime:
    """Was der Kern den Modulen beim Start gibt."""

    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient
    nc: NC | None  # Abruf der AION-2-Website; None, wenn er ausgeschaltet ist (HUB_AION2_ENABLED)


# Legt die Dienste des Moduls in `state` ab (für seine Routen) und gibt zurück, was neben dem Webserver läuft
Start = Callable[[State, Runtime], list[Coroutine[Any, Any, None]]]


@dataclass(frozen=True)
class ApiModule:
    id: str
    routers: tuple[APIRouter, ...]
    requires: tuple[str, ...] = ()  # Module, auf denen dieses aufbaut
    start: Start | None = None
