"""Dateien der Meter-Oberfläche (Submodul capture/a2tools) und der Plugins, ausgeliefert wie von Vites
Dev-Server: erst public/, dann die Wurzel des Meters. Die Host-Seiten bekommen das Shim vor alle Skripte."""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote

from aiohttp import web

from .plugin_files import valid_id
from .plugin_page import content_policy, with_fonts
from .plugins import PluginHost

A2_ROOT = Path(__file__).resolve().parents[2] / "capture" / "a2tools"
SHIM = Path(__file__).resolve().parent / "web" / "a2shim.js"
SHIM_URL = "/__deckbar__/a2shim.js"
EVENTS_WORKER = Path(__file__).resolve().parent / "web" / "a2events.js"
EVENTS_WORKER_URL = "/__deckbar__/a2events.js"
PLUGIN_PREFIX = "/__a2plugin__/"
SDK = A2_ROOT / "src-tauri" / "src" / "plugins" / "a2.js"
SDK_URL = "/_sdk/a2.js"
HOST_PAGES = ("index.html", "plugin-host.html", "plugin-widget.html")  # bekommen das Shim


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


def inject_shim(html: str) -> str:
    tag = f'<script src="{SHIM_URL}"></script>'
    i = html.find("<script")
    return html[:i] + tag + "\n" + html[i:] if i >= 0 else html + tag


def _content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class MeterFiles:
    def __init__(self, plugins: PluginHost) -> None:
        self.plugins = plugins

    async def static(self, request: web.Request) -> web.StreamResponse:
        if request.path == SHIM_URL:
            return web.FileResponse(SHIM, headers={"Cache-Control": "no-cache"})
        if request.path == EVENTS_WORKER_URL:
            headers = {"Cache-Control": "no-cache", "Content-Type": "text/javascript"}
            return web.FileResponse(EVENTS_WORKER, headers=headers)
        if request.path == SDK_URL or request.path.startswith(PLUGIN_PREFIX):
            return self.plugin_file(request)
        path = resolve(request.path)
        if path is None:
            raise web.HTTPNotFound()
        if path.name in HOST_PAGES and path.parent in (A2_ROOT, A2_ROOT / "public"):
            html = inject_shim(path.read_text(encoding="utf-8"))
            return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})
        return web.FileResponse(path, headers={"Content-Type": _content_type(path)})

    def plugin_file(self, request: web.Request) -> web.Response:
        """Dateien eines Plugins für sein Sandbox-iframe, mit CSP ohne Netz (serve im Original)."""
        origin = f"{request.scheme}://{request.host}"
        rel = unquote(request.path.removeprefix(PLUGIN_PREFIX))
        plugin, _, rest = rel.partition("/")
        policy = content_policy(origin, PLUGIN_PREFIX, plugin)
        headers = {"Content-Security-Policy": policy, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        if request.path == SDK_URL:
            return web.Response(body=SDK.read_bytes(), content_type="text/javascript", charset="utf-8", headers=headers)
        loaded = self.plugins.loaded.get(plugin) if valid_id(plugin) else None
        if loaded is None or not rest:
            raise web.HTTPNotFound(headers=headers)
        root = loaded.folder.resolve()
        file = (root / rest).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            raise web.HTTPNotFound(headers=headers)
        if file.suffix == ".html":
            html = with_fonts(file.read_text(encoding="utf-8"))
            return web.Response(text=html, content_type="text/html", headers=headers)
        return web.Response(body=file.read_bytes(), headers={**headers, "Content-Type": _content_type(file)})
