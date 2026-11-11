"""Overlay am PC: Layout der Widgets, Live-Daten für die Overlay-Seite, Steuerung des Programms.

Das Programm (overlay/deckbar-overlay, Qt) legt unter Wayland eine durchsichtige layer-shell-Fläche
über den Spielmonitor und zeigt darin die Seite web/overlay/ (vom Daemon auf Port+1, wie die
Meter-Oberfläche). Die Seite holt hier:

    GET  /api/overlay/layout     Layout (overlay_layout.py), PUT speichert (nach Ziehen im Bearbeiten-Modus)
    GET  /api/overlay/events     Server-Sent Events, die einzige Datenverbindung der Seite: widgets (angemeldete
                                 Widgets), layout, dazu was die Module veröffentlichen (dps, schedule, radar …)

Die Web-UI (Port 8765) nutzt dieselben Daten über /api/overlay und schickt Befehle an das
Programm (Bearbeiten, Sperren, Ein-/Ausblenden) über dessen Socket im Laufzeitordner.
Das Modul startet den User-Dienst deckbar-overlay, sobald AION 2 läuft, und beendet ihn
GAME_GRACE_S nach Spielende. Beim Login startet er nicht (kein Autostart).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from aiohttp import web
from pydantic import ValidationError

from .capture import aion2_running
from .config import _atomic_write
from .overlay_layout import OverlayLayout, WidgetSpec, default_profiles, merge

log = logging.getLogger(__name__)

UNIT = "deckbar-overlay.service"
PAGE_DIR = Path(__file__).resolve().parent / "web" / "overlay"
LAUNCHER = Path(__file__).resolve().parents[2] / "overlay" / "deckbar-overlay.desktop"
QUEUE_MAX = 32
GAME_POLL_S = 5
GAME_GRACE_S = 30  # Spiel weg: so lange warten (Absturz mit Neustart, Ladebildschirm)
UNIT_POLL_S = 30   # Dienststatus fürs Dashboard auffrischen (nur mit Spiel oder offener Web-UI)
COMMANDS = ("toggle", "show", "hide", "edit", "lock", "click", "reload", "details", "history", "settings",
            "autohide-on", "autohide-off")
# Ereignisse, deren letzter Stand eine neu verbundene Overlay-Seite sofort bekommt
RETAINED = ("dps", "schedule", "veil", "plugin-widgets")


def launcher_path() -> Path:
    """Starter „NexBoard Overlay ein/aus“, den overlay/install.sh anlegt (Vorlage im Repo)."""
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "applications" / LAUNCHER.name


def socket_path() -> Path:
    """Gleiche Regel wie im Overlay-Programm."""
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/deckbar-{os.getuid()}"
    return Path(base) / "deckbar-overlay.sock"


def _sse(event: str, payload: Any) -> str:
    """Eine Meldung an die Overlay-Seite. Alle kommen als gewöhnliche Nachricht mit Namen und Inhalt: die
    Seite braucht so nur einen Empfänger und verpasst nichts, bevor ein Widget geladen ist."""
    return f"data: {json.dumps({'event': event, 'payload': payload}, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------- Dienst
class Overlay:
    def __init__(self, config_dir: Path, manage_unit: bool = True) -> None:
        """manage_unit: den User-Dienst ein-/ausschalten. Nur für den Daemon mit der echten
        Konfiguration; Testinstanzen (--config-dir) fassen systemd nie an."""
        self.manage_unit = manage_unit
        self.path = config_dir / "overlay" / "layout.json"
        self.specs: dict[str, WidgetSpec] = {}
        self.module_on: Callable[[str], bool] = lambda _: True  # setzt der Daemon (Modulschalter)
        self.fresh = not self.path.exists()  # neue Datei: Profile kommen aus den Angaben der Widgets
        self.stored = self._load()  # wie in der Datei, auch mit Widgets noch nicht angemeldeter Module
        self.layout = self._fitted(self.stored)
        self.enabled = False
        self.clients: set[asyncio.Queue] = set()
        self.retained: dict[str, Any] = {"dps": {"dps": None, "dps_active": False}, "schedule": []}
        self.unit: dict[str, Any] = {"installed": None, "active": None}
        # Läuft AION 2? Setzt der Daemon (nutzt den Blick des Mitschnitts, sonst eigener Scan)
        self.game_check: Callable[[], Awaitable[bool]] | None = None
        self.game = False
        self.ui_watching: Callable[[], bool] = lambda: True  # Web-UI offen? (setzt der Daemon)
        self.screens: list[dict] = []
        self.listeners: list = []

    # ------------------------------------------------------------ Widgets und Layout
    def register(self, module: str, specs: Iterable[WidgetSpec]) -> None:
        """Ein Modul meldet seine Widgets an; ihr gespeicherter Stand gilt ab jetzt."""
        for spec in specs:
            self.specs[spec.id] = WidgetSpec(**{**spec.__dict__, "module": module})
        self.layout = self._fitted(self.stored)

    def widgets_info(self) -> list[dict[str, Any]]:
        return [spec.public(self.module_on(spec.module)) for spec in self.specs.values()]

    def _load(self) -> OverlayLayout:
        try:
            return OverlayLayout.model_validate(json.loads(self.path.read_text()))
        except FileNotFoundError:
            return OverlayLayout()
        except (OSError, ValueError, ValidationError) as e:
            log.error("%s ungültig, nutze Standard: %s", self.path, e)
            return OverlayLayout()

    def _fitted(self, stored: OverlayLayout) -> OverlayLayout:
        layout = stored.model_copy(deep=True)
        if self.fresh:
            layout.profiles = default_profiles(self.specs)
        layout.fit(self.specs)
        return layout

    def save(self, layout: OverlayLayout) -> None:
        _atomic_write(self.path, json.dumps(layout.model_dump(), ensure_ascii=False, indent=1) + "\n")
        self.fresh = False
        self.stored = self.layout = layout

    async def update(self, patch: dict) -> OverlayLayout:
        base = self.layout.model_dump()
        if "profiles" in patch:
            base["profiles"] = {}  # die Liste kommt immer ganz, sonst ließe sich kein Profil löschen
        layout = OverlayLayout.model_validate(merge(base, patch))
        layout.fit(self.specs)
        self._sync_profile(layout)
        autohide = layout.hide_unfocused != self.layout.hide_unfocused
        profiles_changed = layout.profiles != self.layout.profiles
        self.save(layout)
        if profiles_changed:
            self.write_launcher()
        if autohide and socket_path().exists():
            try:  # sofort ans laufende Programm, sonst gilt es beim nächsten Start
                await self.command("autohide-on" if layout.hide_unfocused else "autohide-off")
            except RuntimeError:
                pass
        await self.publish("layout", layout.model_dump())
        for fn in self.listeners:
            await fn()
        return layout

    def _sync_profile(self, layout: OverlayLayout) -> None:
        """Profilwechsel blendet die Widgets des Profils ein. Sonst merkt sich das aktive Profil jede
        Änderung der Sichtbarkeit (Bearbeiten-Modus, Web-UI, Tastenkürzel)."""
        if not layout.profile:
            return
        if layout.profile != self.layout.profile:
            layout.apply_profile()
        else:
            layout.profiles[layout.profile] = layout.visible()

    def write_launcher(self) -> None:
        """Tastenkürzel: der Starter bekommt je Profil und Widget eine Aktion, der man unter KDE
        (Systemeinstellungen → Kurzbefehle → NexBoard Overlay) eine Taste gibt. Nur wenn das Overlay
        eingerichtet ist und nie aus Testinstanzen."""
        target = launcher_path()
        if not self.manage_unit or not target.exists():
            return
        actions = [(f"profile-{name}", f"Profil {name}", f"--profile {name}") for name in self.layout.profiles]
        actions += [(f"widget-{spec.id}", f"{spec.title} ein/aus", f"--widget {spec.id}") for spec in self.specs.values()]
        text = LAUNCHER.read_text().rstrip("\n") + "\nActions=" + ";".join(a[0] for a in actions) + ";\n"
        for action, name, arguments in actions:
            text += f"\n[Desktop Action {action}]\nName={name}\nExec=deckbar-overlay {arguments}\n"
        if target.read_text() != text:
            _atomic_write(target, text)

    def info(self) -> dict:
        return {"layout": self.layout.model_dump(), "widgets": self.widgets_info(),
                "unit": self.unit, "socket": socket_path().exists(),
                "clients": len(self.clients), "screens": self.screens, "game": self.game}

    async def refresh_screens(self) -> list[dict]:
        """Monitore laut KDE (kscreen-doctor), für die Auswahl in der Web-UI; sonst leer."""
        if not shutil.which("kscreen-doctor"):
            return self.screens
        try:
            proc = await asyncio.create_subprocess_exec(
                "kscreen-doctor", "-j", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(proc.communicate(), 5)
            outputs = json.loads(out).get("outputs", [])
            self.screens = [{"name": o.get("name"), "primary": o.get("priority") == 1,
                             "width": (o.get("size") or {}).get("width"), "height": (o.get("size") or {}).get("height")}
                            for o in outputs if o.get("enabled") and o.get("connected")]
        except (OSError, ValueError, TimeoutError, AttributeError):
            pass
        return self.screens

    # ------------------------------------------------------------ Live-Daten
    async def on_state(self, diff: dict) -> None:
        part = {k: diff[k] for k in ("dps", "dps_active") if k in diff}
        if part:  # immer der ganze Stand: ein später eingeblendetes Widget bekommt ihn so in einem Stück
            await self.publish("dps", {**self.retained["dps"], **part})

    async def on_schedule(self, entries: list[dict[str, Any]]) -> None:
        await self.publish("schedule", entries)

    async def modules_changed(self) -> None:
        """Ein Modul ging an oder aus: die Seite hängt seine Widgets ein oder aus."""
        await self.publish("widgets", self.widgets_info())

    async def publish(self, event: str, payload: Any) -> None:
        """Ereignis an alle offenen Overlay-Seiten. Ereignisse aus RETAINED bekommt auch, wer später kommt."""
        if event in RETAINED:
            self.retained[event] = payload
        await self._send(event, payload)

    async def _send(self, event: str, payload: Any) -> None:
        if not self.clients:
            return
        text = _sse(event, payload)
        for q in list(self.clients):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(text)

    def close_clients(self) -> None:
        """Beim Beenden: offene Event-Streams sofort schließen (sonst wartet aiohttp darauf)."""
        for q in list(self.clients):
            while q.full():
                q.get_nowait()
            q.put_nowait(None)

    # ------------------------------------------------------------ Programm (User-Dienst)
    async def systemctl(self, *args: str) -> tuple[int, str]:
        if not self.manage_unit and args[0] != "show":
            return 1, "Testinstanz: systemd bleibt unangetastet"
        if not shutil.which("systemctl"):
            return 127, "systemctl fehlt"
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "--user", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        return proc.returncode or 0, out.decode(errors="replace").strip()

    async def refresh_unit(self) -> dict:
        code, out = await self.systemctl("show", UNIT, "--property=LoadState,ActiveState,UnitFileState")
        props = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        state = props.get("ActiveState") or "unknown"
        self.unit = {"installed": code == 0 and props.get("LoadState") == "loaded",
                     "active": state == "active", "state": state,
                     "autostart": props.get("UnitFileState") == "enabled"}
        return self.unit

    async def _unit(self, action: str) -> None:
        code, out = await self.systemctl(action, UNIT)
        if code:
            log.warning("deckbar-overlay %s: %s", action, out)
        await self.refresh_unit()

    async def on_module(self, on: bool) -> None:
        """Modul an → auf das Spiel warten (watch), aus → Dienst beenden. Ein Autostart beim Login
        (frühere Einrichtung) wird in beiden Fällen abgeschaltet."""
        self.enabled = on
        await self.refresh_unit()
        if on:
            self.write_launcher()  # Profile von früheren Starts oder einer älteren Version nachtragen
        if self.unit["installed"] and self.manage_unit:
            if self.unit.get("autostart"):
                log.info("deckbar-overlay: Autostart beim Login aus, startet jetzt mit AION 2")
                await self._unit("disable")
            if not on and self.unit["active"]:
                await self._unit("stop")
        elif on and self.manage_unit:
            log.info("Overlay-Programm nicht eingerichtet (overlay/install.sh)")
        for fn in self.listeners:
            await fn()

    async def _game_running(self) -> bool:
        if self.game_check:
            return await self.game_check()
        return await asyncio.to_thread(aion2_running)

    async def plugin_command(self, command: dict) -> None:
        """Plugin-Fenster öffnen, zeigen, verbergen … (plugins.py)."""
        await self._socket_send(b"plugin " + json.dumps(command).encode())

    async def command(self, cmd: str) -> None:
        if cmd not in COMMANDS:
            raise ValueError(f"unbekannter Befehl {cmd}")
        await self._socket_send(cmd.encode())

    async def _socket_send(self, line: bytes) -> None:
        path = socket_path()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(path)), 2)
        except (OSError, TimeoutError) as e:
            raise RuntimeError("Overlay läuft nicht") from e
        writer.write(line + b"\n")
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    async def watch(self) -> None:
        """Dienst mit dem Spiel starten und GAME_GRACE_S nach Spielende beenden. Gehandelt wird nur
        beim Wechsel: wer das Overlay mitten im Spiel beendet oder von Hand startet, behält das."""
        await self.refresh_screens()
        self.game = False
        gone = 0.0
        since_unit = UNIT_POLL_S
        try:
            while True:
                old = (self.game, dict(self.unit))
                if await self._game_running():
                    gone = 0
                    if not self.game:
                        self.game = True
                        if self.manage_unit and self.unit.get("installed") is not False:
                            log.info("AION 2 läuft, starte deckbar-overlay")
                            await self._unit("start")
                            since_unit = 0
                elif self.game:
                    gone += GAME_POLL_S
                    if gone >= GAME_GRACE_S:
                        self.game = False
                        if self.manage_unit and self.unit.get("active"):
                            log.info("AION 2 beendet, stoppe deckbar-overlay")
                            await self._unit("stop")
                            since_unit = 0
                if since_unit >= UNIT_POLL_S and (self.game or self.ui_watching()):
                    await self.refresh_unit()
                    since_unit = 0
                if old != (self.game, self.unit):
                    for fn in self.listeners:
                        await fn()
                await asyncio.sleep(GAME_POLL_S)
                since_unit += GAME_POLL_S
        finally:
            self.game = False

    # ------------------------------------------------------------ Seite (Port+1)
    async def page(self, request: web.Request) -> web.StreamResponse:
        rel = request.match_info.get("tail") or "index.html"
        p = (PAGE_DIR / rel).resolve()
        if not p.is_relative_to(PAGE_DIR.resolve()) or not p.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(p, headers={"Cache-Control": "no-cache"})

    async def api_layout(self, request: web.Request) -> web.Response:
        if request.method == "PUT":
            try:
                data = await request.json()
                if not isinstance(data, dict):
                    raise ValueError
                layout = await self.update(data)
            except ValueError as e:
                msg = str(e) if isinstance(e, ValidationError) else "kein JSON-Objekt"
                return web.json_response({"error": msg}, status=422)
            return web.json_response(layout.model_dump())
        return web.json_response(self.layout.model_dump())

    async def events(self, request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(request)
        q: asyncio.Queue = asyncio.Queue(QUEUE_MAX)
        self.clients.add(q)
        try:
            first = {"widgets": self.widgets_info(), "layout": self.layout.model_dump(), **self.retained}
            for event, payload in first.items():
                await resp.write(_sse(event, payload).encode())
            while True:
                try:
                    text = await asyncio.wait_for(q.get(), 15)
                except TimeoutError:
                    text = ": ping\n\n"
                if text is None:  # close_clients(): Daemon fährt herunter
                    break
                await resp.write(text.encode())
        except ConnectionResetError:
            pass
        finally:
            self.clients.discard(q)
        return resp

    def add_routes(self, app: web.Application) -> None:
        app.router.add_get("/__deckbar__/overlay/", self.page)
        app.router.add_get("/__deckbar__/overlay/{tail:.+}", self.page)
        app.router.add_get("/api/overlay/layout", self.api_layout)
        app.router.add_put("/api/overlay/layout", self.api_layout)
        app.router.add_get("/api/overlay/events", self.events)
