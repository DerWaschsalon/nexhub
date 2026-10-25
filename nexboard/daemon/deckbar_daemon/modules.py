"""Module: einzeln zuschaltbare Teile des Daemons.

Jedes Modul hat eine feste Beschreibung (MODULES, für Web-UI und Dashboard) und zur Laufzeit
Aufgaben (asyncio-Tasks), die nur laufen, solange es eingeschaltet ist. Ein- und Ausschalten
geht ohne Neustart. Gespeichert wird nur, was eingeschaltet ist (modules.yaml):

    enabled: [deck, aion2.dps, aion2.overlay]

Abhängigkeiten: Einschalten schaltet benötigte Module mit ein, Ausschalten schaltet die davon
abhängigen mit aus. Neue Module: Eintrag in MODULES, Aufgaben in server.py (NexBoard.module_tasks)
und eine Seite in web/app/modules/.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

import yaml

from .config import _atomic_write

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleInfo:
    id: str
    name: str
    category: str
    icon: str  # Material-Design-Icon (web/ui-icons.json)
    summary: str
    requires: tuple[str, ...] = ()
    default: bool = False  # bei einer frischen Installation an
    tags: tuple[str, ...] = ()


CATEGORIES = {
    "device": "Geräte",
    "games": "Spiele",
    "community": "Community",
    "system": "System",
}

MODULES: tuple[ModuleInfo, ...] = (
    ModuleInfo(
        "deck", "Touch-Leiste", "device", "gesture-tap-button",
        "Seiten, Kacheln und Aktionen für die Touch-Leiste (ESP32) und den Simulator: Medien, "
        "Lautstärke, Hotkeys, Befehle, Links.",
        default=True, tags=("Hardware", "Makros"),
    ),
    ModuleInfo(
        "aion2.dps", "AION 2 · DPS-Mitschnitt", "games", "sword-cross",
        "Liest den Kampf passiv mit (deckbar-capture, Kern des A2Tools DPS Meter) und liefert DPS "
        "für Leiste, Overlay und Discord.",
        tags=("AION 2", "Live"),
    ),
    ModuleInfo(
        "aion2.overlay", "AION 2 · Overlay", "games", "layers-triple",
        "Meter und Widgets über dem Spiel: frei verschiebbar, klickdurchlässig, mit Boss-Leiste, "
        "Event-Timern und Namenseffekt.",
        requires=("aion2.dps",), tags=("AION 2", "Desktop"),
    ),
    ModuleInfo(
        "aion2.runs", "AION 2 · Dungeon-Runs", "games", "trophy",
        "Fasst Bosskämpfe zu Runs zusammen und postet nach jedem Run ein Bild mit dem Schaden pro "
        "Boss in einen Discord-Kanal.",
        requires=("aion2.dps",), tags=("AION 2", "Discord"),
    ),
    ModuleInfo(
        "aion2.radar", "AION 2 · Radar", "games", "radar",
        "Hidden Cubes, Karte und Boss-Warnungen als Widgets im Overlay, Feldbosse und Vertraute in "
        "der Web-UI. Läuft mit AION 2 und liest den Server-Verkehr passiv mit (tcpdump).",
        tags=("AION 2", "Desktop"),
    ),
    ModuleInfo(
        "discord.bot", "Discord-Bot", "community", "robot",
        "Schickt Gruppen-DPS nach Bosskämpfen und Run-Ergebnisse an einen Discord-Bot "
        "(z. B. TheWashBot), der Meldungen mehrerer Spieler zusammenführt.",
        requires=("aion2.dps",), tags=("Discord", "Gruppe"),
    ),
    ModuleInfo(
        "hub", "NexHub", "community", "link-variant",
        "Verbindet die NexBoard mit deinem Konto im NexHub, der Website der Gilde. Später lädt sie "
        "dorthin deine Dungeon-Runs hoch.",
        tags=("Hub", "Online"),
    ),
    ModuleInfo(
        "updates", "Updates", "system", "update",
        "Prüft täglich auf neue Versionen und neue Releases des A2Tools-Kerns, Installation mit "
        "einem Klick.",
        default=True, tags=("Wartung",),
    ),
)
BY_ID = {m.id: m for m in MODULES}

TaskFactory = Callable[[], Awaitable[None]]
Hook = Callable[[bool], Awaitable[None]]


@dataclass
class Runtime:
    tasks: list[TaskFactory] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)  # nach dem Ein-/Ausschalten (True = an)
    running: list[asyncio.Task] = field(default_factory=list)
    status: Callable[[], dict] | None = None  # Kurzstand fürs Dashboard


def dependents(mid: str) -> set[str]:
    """Alle Module, die (auch indirekt) `mid` brauchen."""
    out: set[str] = set()
    todo = [mid]
    while todo:
        cur = todo.pop()
        for m in MODULES:
            if cur in m.requires and m.id not in out:
                out.add(m.id)
                todo.append(m.id)
    return out


def requirements(mid: str) -> set[str]:
    out: set[str] = set()
    todo = list(BY_ID[mid].requires)
    while todo:
        cur = todo.pop()
        if cur not in out:
            out.add(cur)
            todo += BY_ID[cur].requires
    return out


class ModuleManager:
    def __init__(self, config_dir: Path, initial: Callable[[], set[str]] | None = None) -> None:
        self.path = config_dir / "modules.yaml"
        self.enabled: set[str] = self._load(initial)
        self.runtime: dict[str, Runtime] = {m.id: Runtime() for m in MODULES}
        self.listeners: list[Callable[[], Awaitable[None]]] = []
        self.started = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ Speichern
    def _load(self, initial: Callable[[], set[str]] | None) -> set[str]:
        try:
            data = yaml.safe_load(self.path.read_text()) or {}
            ids = data.get("enabled") if isinstance(data, dict) else None
            if not isinstance(ids, list):
                raise ValueError("enabled fehlt")
            unknown = [i for i in ids if i not in BY_ID]
            if unknown:
                log.warning("unbekannte Module in %s ignoriert: %s", self.path, ", ".join(map(str, unknown)))
            return self._closed({i for i in ids if i in BY_ID})
        except FileNotFoundError:
            pass
        except (OSError, ValueError, yaml.YAMLError) as e:
            log.error("%s ungültig (%s), nutze Standard", self.path, e)
        ids = initial() if initial else {m.id for m in MODULES if m.default}
        enabled = self._closed({i for i in ids if i in BY_ID})
        self._save(enabled)
        log.info("Module festgelegt: %s", ", ".join(sorted(enabled)) or "keine")
        return enabled

    @staticmethod
    def _closed(ids: set[str]) -> set[str]:
        """Benötigte Module dazunehmen."""
        out = set(ids)
        for i in ids:
            out |= requirements(i)
        return out

    def _save(self, enabled: set[str]) -> None:
        order = [m.id for m in MODULES if m.id in enabled]
        text = ("# Eingeschaltete Module – wird von der Web-UI überschrieben.\n"
                + yaml.safe_dump({"enabled": order}, sort_keys=False))
        _atomic_write(self.path, text)

    # ------------------------------------------------------------ Abfragen
    def on(self, mid: str) -> bool:
        return mid in self.enabled

    def register(self, mid: str, *tasks: TaskFactory, hook: Hook | None = None,
                 status: Callable[[], dict] | None = None) -> None:
        rt = self.runtime[mid]
        rt.tasks += tasks
        if hook:
            rt.hooks.append(hook)
        if status:
            rt.status = status

    def info(self) -> dict:
        mods = []
        for m in MODULES:
            rt = self.runtime[m.id]
            st: dict = {}
            if rt.status and m.id in self.enabled:
                try:
                    st = rt.status()
                except Exception:  # Dashboard darf an einem Modul nicht scheitern
                    log.exception("Status von %s", m.id)
            mods.append({**asdict(m), "enabled": m.id in self.enabled,
                         "dependents": sorted(dependents(m.id)), "status": st})
        return {"categories": CATEGORIES, "modules": mods}

    # ------------------------------------------------------------ Laufzeit
    async def start(self) -> None:
        self.started = True
        for m in MODULES:
            if m.id in self.enabled:
                await self._start(m.id)

    async def stop_all(self) -> None:
        """Beim Beenden des Daemons: nur Aufgaben stoppen, ohne Hooks (das Overlay läuft weiter)."""
        for m in reversed(MODULES):
            await self._stop(m.id, hooks=False)
        self.started = False

    async def _start(self, mid: str) -> None:
        rt = self.runtime[mid]
        if rt.running:
            return
        rt.running = [asyncio.ensure_future(self._guard(mid, f)) for f in rt.tasks]
        for h in rt.hooks:
            await h(True)

    async def _stop(self, mid: str, hooks: bool = True) -> None:
        rt = self.runtime[mid]
        tasks, rt.running = rt.running, []
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if hooks:
            for h in rt.hooks:
                await h(False)

    @staticmethod
    async def _guard(mid: str, factory: TaskFactory) -> None:
        """Eine abgestürzte Aufgabe nach kurzer Pause neu starten, statt das Modul still zu verlieren."""
        while True:
            try:
                await factory()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Modul %s: Aufgabe abgestürzt, starte in 10 s neu", mid)
                await asyncio.sleep(10)

    async def set(self, mid: str, on: bool) -> list[str]:
        """Modul ein-/ausschalten; gibt alle dadurch geänderten Module zurück."""
        if mid not in BY_ID:
            raise KeyError(mid)
        async with self._lock:
            if on:
                change = ({mid} | requirements(mid)) - self.enabled
            else:
                change = ({mid} | dependents(mid)) & self.enabled
            if not change:
                return []
            order = [m.id for m in MODULES if m.id in change]
            if on:
                self.enabled |= change
            else:
                self.enabled -= change
            self._save(self.enabled)
            log.info("Module %s: %s", "ein" if on else "aus", ", ".join(order))
            if self.started:
                for i in (order if on else reversed(order)):
                    if on:
                        await self._start(i)
                    else:
                        await self._stop(i)
        for fn in self.listeners:
            await fn()
        return order
