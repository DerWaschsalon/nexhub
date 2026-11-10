"""Die Oberfläche des A2Tools DPS Meter (Submodul capture/a2tools, GPL-3.0) fürs NexBoard-Overlay.

Läuft als eigener kleiner Webserver auf 127.0.0.1 (Port der NexBoard + 1), damit die absoluten
Pfade der Oberfläche (/src/js/…, /vendor/…) unverändert passen. Das Overlay (overlay/deckbar-overlay)
lädt sie in Qt WebEngine. Statt Tauri spricht die Oberfläche mit dem Shim in web/a2shim.js:

    GET  /…                 Dateien wie Vites Dev-Server: erst public/, dann die Wurzel des Meters;
                            in index.html kommt der Shim vor alle anderen Skripte
    GET  /api/a2/events     Server-Sent Events: die Tauri-Events (dps-update, ping-update, …)
    POST /api/a2/invoke     {"cmd": …, "args": {…}}: Tauri-Commands, siehe INVOKE
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import unquote

from aiohttp import web

from .capture import DEFAULT_INTERVAL_MS, Capture, history_root
from .config import _atomic_write
from .plugins import LANGUAGE_KEY, PluginError, PluginHost, content_policy, valid_id, with_fonts

log = logging.getLogger(__name__)

A2_ROOT = Path(__file__).resolve().parents[2] / "capture" / "a2tools"
SHIM = Path(__file__).resolve().parent / "web" / "a2shim.js"
SHIM_URL = "/__deckbar__/a2shim.js"
EVENTS_WORKER = Path(__file__).resolve().parent / "web" / "a2events.js"
EVENTS_WORKER_URL = "/__deckbar__/a2events.js"
PLUGIN_PREFIX = "/__a2plugin__/"
SDK = A2_ROOT / "src-tauri" / "src" / "plugins" / "a2.js"
HOST_PAGES = ("index.html", "plugin-host.html", "plugin-widget.html")  # bekommen das Shim
# Je Client; ein hängender Client verliert lieber alte dps-update. Der Strom ist je Browser-Profil
# einer (a2events.js), Plugin-Ereignisse dürfen hier nicht verloren gehen.
QUEUE_MAX = 256

# Nicht aus den Einstellungen des A2Tools-Meters übernehmen: Geheimnisse, Fensterlagen, Online-Kram
# Befehle ohne plugin_-Vorsilbe, die der Plugin-Host beantwortet
PLUGIN_COMMANDS = {"meter_shown", "set_meter_shown", "set_plugin_theme"}
UPDATE_RATE = "dpsMeter.updateRateMs"  # Einstellung „Aktualisierung“ des Meters
UPDATE_RATES_MS = (100, 200, 250, 500)  # Auswahl im Meter
NO_IMPORT = re.compile(r"(?i)key|token|secret|account|^window\.|streamOverlay|autoUpload|discord|kwinRule|plugin")


def app_version(root: Path = A2_ROOT) -> str:
    """Version des Submoduls (tauri.conf.json), zeigt die Oberfläche an."""
    try:
        return str(json.loads((root / "src-tauri" / "tauri.conf.json").read_text())["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return "?"


def resolve(rel: str, root: Path = A2_ROOT) -> Path | None:
    """URL-Pfad → Datei, wie Vite: public/ zuerst, /i18n und /data aus src/data (dorthin kopiert
    sie erst das Vite-Plugin). Nichts außerhalb von root."""
    rel = unquote(rel).lstrip("/") or "index.html"
    candidates = [root / "public", root]
    if rel.startswith(("i18n/", "data/")):
        rel = rel.removeprefix("data/")
        candidates = [root / "src" / "data"]
    for base in candidates:
        p = (base / rel).resolve()
        if p.is_relative_to(base.resolve()) and p.is_file():
            return p
    return None


def plain_id(fight_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", fight_id) or fight_id.startswith("."):
        raise ValueError(f"ungültige Kampf-ID {fight_id!r}")
    return fight_id


def member_jobs(record: dict) -> list[str]:
    """Wie FightRecord::member_jobs im Meter."""
    actors = [a for a in record.get("actors") or [] if isinstance(a, dict) and a.get("job")]
    if any(a.get("dbid") for a in actors):
        jobs = [a["job"] for a in actors if a.get("dbid")]
    else:
        jobs = [a["job"] for a in actors
                if not a.get("nickname") or not all(c.isdigit() or c in "*#" for c in a["nickname"])]
    return sorted(jobs)


def summaries(hist: Path) -> list[dict]:
    """FightSummary-Liste wie FightHistoryManager::list_fights, wenn deckbar-capture nicht läuft."""
    out = []
    for p in hist.glob("*.json") if hist.is_dir() else []:
        try:
            r = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(r, dict) or "id" not in r:
            continue
        out.append({k: r.get(k) for k in ("id", "bossName", "targetId", "startTimeMs", "durationMs", "totalDamage",
                                         "jobs", "jobIds", "isTrain", "appVersion", "mobCode", "dungeonId")}
                   | {"isLive": False, "memberJobs": member_jobs(r)})
    out.sort(key=lambda f: f.get("startTimeMs") or 0, reverse=True)
    return out


def inject_shim(html: str) -> str:
    tag = f'<script src="{SHIM_URL}"></script>'
    i = html.find("<script")
    return html[:i] + tag + "\n" + html[i:] if i >= 0 else html + tag


class A2Ui:
    def __init__(self, capture: Capture, settings_path: Path, plugin_dir: Path | None = None) -> None:
        self.capture = capture
        self.settings_path = settings_path
        self.clients: set[asyncio.Queue] = set()
        self.settings = self._load_settings()
        self._apply_update_rate()
        capture.data_listeners.append(self._on_capture)
        base = plugin_dir or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "deckbar"
        self.plugins = PluginHost(capture, lambda: self.settings, self._set_setting, self.emit,
                                  base / "plugins", base / "plugin-data")
        # Sprachwahl im Meter speichert die allgemeine Einstellung (setzt __main__); die meldet sich
        # dann über apply_language zurück
        self.on_language: Callable[[str], Awaitable[None]] | None = None

    async def apply_language(self, language: str) -> None:
        """Sprache der allgemeinen Einstellungen an Mitschnitt, Meter und Plugins geben."""
        if self.capture.running:
            try:
                await self._req("language", lang=language)
            except (RuntimeError, TimeoutError) as e:
                log.warning("Sprache nicht an den Mitschnitt übergeben: %s", e)
        if self.settings.get(LANGUAGE_KEY) != language:
            self._set_setting(LANGUAGE_KEY, language)
            await self.emit("setting-changed", {"key": LANGUAGE_KEY, "value": language})
        await self.plugins.tell_all("language", language)

    def _set_setting(self, key: str, value: str) -> None:
        self.settings[key] = value
        self._save_settings(self.settings)
        if key == UPDATE_RATE:
            self._apply_update_rate()

    def _apply_update_rate(self) -> None:
        """Takt aus den Meter-Einstellungen an den Mitschnitt; gilt ab seinem nächsten Start, damit er
        nicht mitten im Spiel neu startet."""
        rate = self.settings.get(UPDATE_RATE, "")
        valid = rate.isdigit() and int(rate) in UPDATE_RATES_MS
        self.capture.interval_ms = int(rate) if valid else DEFAULT_INTERVAL_MS

    # ------------------------------------------------------------ Einstellungen der Oberfläche
    def _load_settings(self) -> dict[str, str]:
        try:
            data = json.loads(self.settings_path.read_text())
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("%s unlesbar: %s", self.settings_path, e)
        # Erster Start: Einstellungen des A2Tools-Meters übernehmen (Theme, Spielerlimit, Sprache …)
        from .dps import a2tools_settings_path
        try:
            a2 = json.loads(a2tools_settings_path().read_text())
            data = {k: str(v) for k, v in a2.items() if not NO_IMPORT.search(k)} if isinstance(a2, dict) else {}
            if data:
                log.info("%d Einstellungen aus dem A2Tools-Meter übernommen", len(data))
        except (OSError, ValueError):
            data = {}
        self._save_settings(data)
        return data

    def _save_settings(self, data: dict[str, str]) -> None:
        _atomic_write(self.settings_path, json.dumps(data, ensure_ascii=False, indent=1) + "\n", 0o600)

    # ------------------------------------------------------------ Ereignisse
    async def _on_capture(self, event: str, payload: Any) -> None:
        if event == "dps":
            await self.emit("dps-update", payload)
        elif event == "ping" and payload is not None:
            await self.emit("ping-update", payload)

    async def emit(self, event: str, payload: Any) -> None:
        if not self.clients:
            return
        text = f"data: {json.dumps({'event': event, 'payload': payload}, ensure_ascii=False)}\n\n"
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

    async def events(self, request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(request)
        q: asyncio.Queue = asyncio.Queue(QUEUE_MAX)
        self.clients.add(q)
        await self.capture.set_full(True)
        # Die Oberfläche braucht sofort einen Stand (dpsData ist sonst null bis zur nächsten Änderung)
        if self.capture.running:
            try:
                snap = await self._req("snapshot")
                q.put_nowait(f"data: {json.dumps({'event': 'dps-update', 'payload': snap}, ensure_ascii=False)}\n\n")
            except (RuntimeError, TimeoutError):
                pass
        try:
            await resp.write(b": hallo\n\n")
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
            if not self.clients:
                await self.capture.set_full(False)
        return resp

    # ------------------------------------------------------------ Dateien
    async def static(self, request: web.Request) -> web.StreamResponse:
        if request.path == SHIM_URL:
            return web.FileResponse(SHIM, headers={"Cache-Control": "no-cache"})
        if request.path == EVENTS_WORKER_URL:
            return web.FileResponse(EVENTS_WORKER, headers={"Cache-Control": "no-cache", "Content-Type": "text/javascript"})
        if request.path == "/_sdk/a2.js" or request.path.startswith(PLUGIN_PREFIX):
            return self.plugin_file(request)
        path = resolve(request.path)
        if path is None:
            raise web.HTTPNotFound()
        if path.name in HOST_PAGES and path.parent in (A2_ROOT, A2_ROOT / "public"):
            html = inject_shim(path.read_text(encoding="utf-8"))
            return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return web.FileResponse(path, headers={"Content-Type": ctype})

    def plugin_file(self, request: web.Request) -> web.Response:
        """Dateien eines Plugins für sein Sandbox-iframe, mit CSP ohne Netz (serve im Original)."""
        origin = f"{request.scheme}://{request.host}"
        rel = unquote(request.path.removeprefix(PLUGIN_PREFIX))
        plugin, _, rest = rel.partition("/")
        policy = content_policy(origin, PLUGIN_PREFIX, plugin)
        headers = {"Content-Security-Policy": policy, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        if request.path == "/_sdk/a2.js":
            return web.Response(body=SDK.read_bytes(), content_type="text/javascript", charset="utf-8", headers=headers)
        loaded = self.plugins.loaded.get(plugin) if valid_id(plugin) else None
        if loaded is None or not rest:
            raise web.HTTPNotFound(headers=headers)
        root = loaded.folder.resolve()
        file = (root / rest).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            raise web.HTTPNotFound(headers=headers)
        if file.suffix == ".html":
            return web.Response(text=with_fonts(file.read_text(encoding="utf-8")), content_type="text/html", headers=headers)
        ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        return web.Response(body=file.read_bytes(), headers={**headers, "Content-Type": ctype})

    # ------------------------------------------------------------ Commands
    async def invoke(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            cmd, args = str(body["cmd"]), body.get("args") or {}
            window = body.get("window")
        except (ValueError, KeyError, TypeError):
            return web.json_response({"error": "erwartet {cmd, args}"}, status=400)
        try:
            # Plugin-Seiten kommen nur an ihre Befehle, das prüft der Host anhand der Fensterkennung
            if cmd.startswith("plugin_") or cmd in PLUGIN_COMMANDS or str(window or "").startswith(("plugin-", "widget:")):
                result = await self._plugin_call(cmd, args, str(window) if window else None)
            else:
                result = await self.call(cmd, args)
        except PluginError as e:
            return web.json_response({"error": str(e)}, status=500)
        except Exception as e:  # Tauri-Commands melden Fehler als String
            log.debug("invoke %s: %s", cmd, e)
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"result": result})

    async def _plugin_call(self, cmd: str, args: dict, window: str | None) -> Any:
        if cmd == "get_settings":
            return self.settings
        return await self.plugins.call(cmd, args, window)

    async def _req(self, cmd: str, **kw: Any) -> Any:
        return await self.capture.request(cmd, timeout=10, **kw)

    async def call(self, cmd: str, args: dict) -> Any:
        """Ein Tauri-Command der Oberfläche (Liste: siehe Tabelle unten, Fensterbefehle macht das Overlay)."""
        a = args.get
        live = self.capture.running
        hist = history_root() / "history"
        match cmd:
            # ---- Allgemein
            case "build_features":
                return {"online": False}
            case "get_app_version":
                return app_version()
            case "get_settings":
                return self.settings
            case "update_settings":
                key, value = str(a("key")), str(a("value"))
                if self.settings.get(key) != value:
                    self._set_setting(key, value)
                    await self.emit("setting-changed", {"key": key, "value": value})
                return None
            case "clear_settings":
                self.settings = {}
                self._save_settings(self.settings)
                self._apply_update_rate()
                return None
            case "set_language":
                if self.on_language:
                    await self.on_language(str(a("language")))
                else:
                    await self.apply_language(str(a("language")))
                return None
            case "is_admin":
                return True
            case "debug_status":
                st = self.capture.status
                return {"port": st.get("port"), "device": st.get("device"), "ping": st.get("ping"),
                        "damageGeneration": 0, "aion2Window": bool(st.get("game")), "isAdmin": True}
            case "get_aion2_window_title":
                return await self._req("window_title") if live else None
            case "get_capture_status":
                if live:
                    return await self._req("capture_status")
                return {"locked": False, "port": None, "device": "", "ip": "127.0.0.1",
                        "localPlayerId": None, "characterName": None, "characterNameFromGame": False}
            case "is_capture_suspended":
                return bool(self.capture.status.get("suspended"))
            case "suspend_capture":
                return await self._req("suspend", on=bool(a("suspended"))) if live else None
            # ---- Meter
            case "get_dps_snapshot":
                return await self._req("snapshot") if live else None
            case "reset_combat":
                return await self._req("reset") if live else None
            case "set_target_mode":
                return await self._req("target_mode", mode=str(a("mode"))) if live else None
            case "set_character_name":
                return await self._req("set_character_name", name=str(a("name") or ""), manual=bool(a("manual"))) if live else None
            case "bind_local_actor_id":
                return await self._req("bind_local_actor_id", actor_id=int(a("actorId") or 0), manual=bool(a("manual"))) if live else None
            case "bind_local_nickname":
                return await self._req("bind_local_nickname", actor_id=int(a("actorId") or 0), nickname=str(a("nickname") or "")) if live else None
            case "get_available_devices":
                return await self._req("devices") if live else []
            case "set_manual_device":
                return await self._req("set_device", device=str(a("device") or "")) if live else None
            case "reset_auto_detection":
                return await self._req("reset_detection") if live else None
            # ---- Details und History
            case "get_details_context":
                if live:
                    return await self._req("context")
                return {"currentTargetId": 0, "targets": [], "actors": []}
            case "get_skill_details":
                if not live:
                    raise RuntimeError("kein laufender Kampf")
                return await self._req("details", target_id=int(a("targetId") or 0), actor_ids=a("actorIds"),
                                       summary=bool(a("summaryOnly")))
            case "get_fight_buffs":
                return await self._req("buffs", target_id=int(a("targetId") or 0), target_ids=a("targetIds")) if live else None
            case "get_fight_history":
                return await self._req("history") if live else await asyncio.to_thread(summaries, hist)
            case "load_fight":
                fid = plain_id(str(a("id")))
                if live:
                    return await self._req("fight", fight_id=fid)
                return json.loads((hist / f"{fid}.json").read_text())
            case "delete_fight":
                fid = plain_id(str(a("id")))
                if live:
                    return await self._req("delete_fight", fight_id=fid)
                (hist / f"{fid}.json").unlink(missing_ok=True)
                return None
            # ---- Ohne Gegenstück (Offline-Build des Meters, siehe app.rs)
            case "log_from_ui" | "set_debug_logging" | "set_packet_logging" | "account_sign_out" | "write_cached_icon":
                return None
            case "read_cached_icon" | "account_status_cached" | "choose_screenshot_folder":
                return None
            case "discord_activity_available" | "show_update_window":
                return False
            case "default_screenshot_folder":
                return ""
            case "share_status" | "get_hotkey_status":
                return {}
            case _:
                raise RuntimeError(f"{cmd}: in der NexBoard nicht verfügbar")

    def app(self, *middlewares, routes=None) -> web.Application:
        """routes: weitere Routen (Overlay-Seite), vor der Auslieferung der Meter-Dateien."""
        app = web.Application(middlewares=list(middlewares), client_max_size=4 * 1024 * 1024)
        if routes:
            routes(app)
        app.router.add_get("/api/a2/events", self.events)
        app.router.add_post("/api/a2/invoke", self.invoke)
        app.router.add_get("/{tail:.*}", self.static)
        return app
