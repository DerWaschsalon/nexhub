"""Ersteinrichtung der Web-UI: Vorlagen (welche Module zusammen einen Zweck erfüllen) und was dafür auf dem
PC vorhanden sein muss. Eine neue Vorlage oder Voraussetzung ist ein Eintrag in den Tabellen unten."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from aiohttp import web
from nexcore.errors import ApiError

from .core.http import ok, read_object


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    summary: str
    icon: str
    modules: tuple[str, ...]
    profile: str = ""  # Profil des Overlays, das die Vorlage wählt


@dataclass(frozen=True)
class Requirement:
    id: str
    name: str
    hint: str  # was zu tun ist, wenn sie fehlt
    templates: tuple[str, ...]  # für welche Vorlagen sie gebraucht wird


TEMPLATES = (
    Template("bar", "Touch-Leiste", "Kacheln für Lautstärke, Medien, Tasten und Programme auf der Leiste am "
             "Monitor.", "tablet", ("deck",)),
    Template("pve", "AION 2 · PvE", "DPS-Meter, Boss-Leiste und Boss-Warnungen über dem Spiel, dazu Termine und "
             "die Auswertung deiner Dungeon-Runs.", "sword-cross",
             ("aion2.dps", "aion2.overlay", "aion2.warnings", "aion2.schedule", "aion2.runs"), profile="PvE"),
    Template("pvp", "AION 2 · PvP", "Nur das Meter über dem Spiel, dazu die Plugins des A2Tools-Meters, etwa der "
             "PvP Tracker.", "sword", ("aion2.dps", "aion2.overlay", "aion2.plugins"), profile="PvP"),
    Template("radar", "AION 2 · Radar", "Hidden Cubes mit Ton, Karte und die Respawn-Timer der Feldbosse.", "radar",
             ("aion2.radar", "aion2.schedule", "aion2.field_bosses", "aion2.overlay")),
)
REQUIREMENTS = (
    Requirement("tools", "Werkzeuge der Leiste", "Welche fehlen, steht oben auf jeder Seite; ihre Kacheln bleiben "
                "ohne Wirkung. Installieren, z. B.: sudo pacman -S wireplumber playerctl ydotool",
                ("bar",)),
    Requirement("capture", "Mitschnitt der Kampfdaten", "Einmal im Ordner nexboard ausführen: "
                "capture/build.sh --install (braucht Rust)", ("pve", "pvp", "radar")),
    Requirement("overlay", "Overlay-Programm", "Einmal im Ordner nexboard ausführen: overlay/install.sh "
                "(braucht pyside6, qt6-webengine, layer-shell-qt)", ("pve", "pvp", "radar")),
    Requirement("tcpdump", "tcpdump für Radar und Boss-Warnungen", "sudo pacman -S tcpdump, danach: sudo setcap "
                "cap_net_raw,cap_net_admin=eip /usr/bin/tcpdump", ("pve", "radar")),
    Requirement("character", "Name deines Charakters", "Unter System → Einstellungen eintragen; daran erkennen "
                "Meter und Radar, wer du bist.", ("pve", "pvp", "radar")),
)
Checks = dict[str, Callable[[], bool]]  # Voraussetzung → erfüllt?


class Modules(Protocol):
    enabled: set[str]

    async def set(self, mid: str, on: bool) -> list[str]: ...


class Setup:
    """GET /api/setup zeigt Vorlagen und Voraussetzungen, POST /api/setup schaltet die Module der gewählten
    Vorlagen ein. Ausgeschaltet wird hier nichts."""

    def __init__(self, modules: Modules, checks: Checks, choose_profile: Callable[[str], Awaitable[None]],
                 prepare: Callable[[], Awaitable[object]] | None = None) -> None:
        assert checks.keys() == {r.id for r in REQUIREMENTS}, "je Voraussetzung genau eine Prüfung"
        self.modules = modules
        self.checks = checks
        self.choose_profile = choose_profile
        self.prepare = prepare  # vor dem Prüfen auffrischen, was sich nicht von selbst meldet (Overlay-Dienst)

    def info(self) -> dict[str, Any]:
        templates = [{**asdict(t), "active": set(t.modules) <= self.modules.enabled} for t in TEMPLATES]
        requirements = [{**asdict(r), "ok": self.checks[r.id]()} for r in REQUIREMENTS]
        return {"templates": templates, "requirements": requirements}

    async def apply(self, wanted: list[str]) -> list[str]:
        """Module der Vorlagen einschalten; zurück kommt, was dadurch neu an ist."""
        chosen = [t for t in TEMPLATES if t.id in wanted]
        if len(chosen) != len(set(wanted)):
            raise ValueError("unbekannte Vorlage")
        changed: list[str] = []
        for template in chosen:
            for mid in template.modules:
                changed += await self.modules.set(mid, True)
        profiles = [t.profile for t in chosen if t.profile]
        if profiles:
            await self.choose_profile(profiles[0])
        return changed

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/setup", self.api_get)
        router.add_post("/api/setup", self.api_apply)

    async def api_get(self, request: web.Request) -> web.Response:
        if self.prepare:
            await self.prepare()
        return web.json_response(self.info())

    async def api_apply(self, request: web.Request) -> web.Response:
        wanted = (await read_object(request)).get("templates")
        if not isinstance(wanted, list) or not all(isinstance(t, str) for t in wanted):
            raise ApiError(400, "erwartet {templates: [Kennung, …]}")
        try:
            changed = await self.apply(wanted)
        except ValueError as e:
            raise ApiError(400, str(e)) from e
        return ok(changed=changed, **self.info())
