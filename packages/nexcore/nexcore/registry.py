"""Registry: welche Module es gibt, welche eingeschaltet sind, und das Ein- und Ausschalten.

Gespeichert wird nur, was eingeschaltet ist (eine YAML-Datei, z. B. modules.yaml):

    enabled: [deck, aion2.dps]

Einschalten schaltet benötigte Module mit ein, Ausschalten die davon abhängigen mit aus. Der Kern
kennt keine Module: der Host übergibt die Klassen.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .module import Context, Module, ModuleInfo
from .paths import atomic_write

log = logging.getLogger("nexcore.registry")

CHANGED = "modules.changed"  # Thema auf dem Bus, Inhalt: Liste der geänderten Modul-IDs


class Registry:
    def __init__(self, ctx: Context, modules: Sequence[type[Module]], state_file: Path,
                 initial: Callable[[], set[str]] | None = None) -> None:
        self.ctx = ctx
        self.order = [m.info.id for m in modules]  # Startreihenfolge = Reihenfolge der Klassen
        self.infos: dict[str, ModuleInfo] = {m.info.id: m.info for m in modules}
        self.modules: dict[str, Module] = {m.info.id: m(ctx) for m in modules}
        self.state_file = state_file
        self.enabled = self._load(initial)
        self.started = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ Abhängigkeiten
    def requirements(self, mid: str) -> set[str]:
        """Alle Module, die `mid` (auch indirekt) braucht."""
        out: set[str] = set()
        todo = list(self.infos[mid].requires)
        while todo:
            cur = todo.pop()
            if cur not in out:
                out.add(cur)
                todo += self.infos[cur].requires
        return out

    def dependents(self, mid: str) -> set[str]:
        """Alle Module, die (auch indirekt) `mid` brauchen."""
        return {other for other in self.infos if mid in self.requirements(other)}

    def _closed(self, ids: set[str]) -> set[str]:
        out = set(ids)
        for mid in ids:
            out |= self.requirements(mid)
        return out

    def _sorted(self, ids: set[str]) -> list[str]:
        return [mid for mid in self.order if mid in ids]

    # ------------------------------------------------------------ Speichern
    def _load(self, initial: Callable[[], set[str]] | None) -> set[str]:
        try:
            data = yaml.safe_load(self.state_file.read_text()) or {}
            ids = data.get("enabled") if isinstance(data, dict) else None
            if not isinstance(ids, list):
                raise ValueError("enabled fehlt")
            unknown = [i for i in ids if i not in self.infos]
            if unknown:
                log.warning("unbekannte Module in %s ignoriert: %s", self.state_file, ", ".join(map(str, unknown)))
            return self._closed({i for i in ids if i in self.infos})
        except FileNotFoundError:
            pass
        except (OSError, ValueError, yaml.YAMLError) as e:
            log.error("%s ungültig (%s), nutze Standard", self.state_file, e)
        ids = initial() if initial else {mid for mid, info in self.infos.items() if info.default}
        enabled = self._closed({i for i in ids if i in self.infos})
        self._save(enabled)
        return enabled

    def _save(self, enabled: set[str]) -> None:
        text = ("# Eingeschaltete Module – wird von der Web-UI überschrieben.\n"
                + yaml.safe_dump({"enabled": self._sorted(enabled)}, sort_keys=False))
        atomic_write(self.state_file, text)

    # ------------------------------------------------------------ Abfragen
    def on(self, mid: str) -> bool:
        return mid in self.enabled

    def info(self) -> list[dict[str, Any]]:
        """Jedes Modul mit Beschreibung, Schalter, Abhängigen und Kurzstand fürs Dashboard."""
        out = []
        for mid in self.order:
            status: dict[str, Any] = {}
            if mid in self.enabled:
                try:
                    status = self.modules[mid].status()
                except Exception:  # das Dashboard darf an einem Modul nicht scheitern
                    log.exception("Status von %s", mid)
            out.append({**asdict(self.infos[mid]), "enabled": mid in self.enabled,
                        "dependents": self._sorted(self.dependents(mid)), "status": status})
        return out

    # ------------------------------------------------------------ Laufzeit
    async def start(self) -> None:
        self.started = True
        for mid in self._sorted(self.enabled):
            await self.modules[mid].activate()

    async def shutdown(self) -> None:
        """Host beendet sich: nur abräumen, ohne die Aus-Schritte der Module."""
        for mid in reversed(self._sorted(self.enabled)):
            await self.modules[mid].shutdown()
        self.started = False

    async def set(self, mid: str, on: bool) -> list[str]:
        """Modul ein- oder ausschalten; zurück kommen alle dadurch geänderten Module."""
        if mid not in self.infos:
            raise KeyError(mid)
        async with self._lock:
            if on:
                change = ({mid} | self.requirements(mid)) - self.enabled
            else:
                change = ({mid} | self.dependents(mid)) & self.enabled
            if not change:
                return []
            order = self._sorted(change)
            self.enabled = self.enabled | change if on else self.enabled - change
            self._save(self.enabled)
            log.info("Module %s: %s", "ein" if on else "aus", ", ".join(order))
            if self.started:
                await self._switch(order, on)
        await self.ctx.bus.emit(CHANGED, order)
        return order

    async def _switch(self, order: list[str], on: bool) -> None:
        if on:
            for mid in order:
                await self.modules[mid].activate()
        else:
            for mid in reversed(order):
                await self.modules[mid].deactivate()
