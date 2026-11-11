"""Der Plugin-Katalog von A2Tools: signierten Katalog holen, Dateien laden und prüfen, Installation schreiben.

Jede Installation hinterlegt den Katalog samt Signatur als Nachweis; beim Laden prüft verify_installed
die Dateien dagegen. Der Host (plugins.py) entscheidet, wann installiert wird, und lädt danach neu.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import aiohttp

from .plugin_files import (
    API_VERSION,
    MAX_PLUGIN,
    PluginError,
    check_files,
    load_manifest,
    newer,
    safe_path,
    sha256_hex,
    valid_id,
    verify_catalog,
)

PROOF_DIR = ".proof"
MAX_CATALOG = 1024 * 1024
PARALLEL_DOWNLOADS = 4


class PluginCatalog:
    def __init__(self, folder: Path, base_url: str, key_hex: str,
                 session: Callable[[], Awaitable[aiohttp.ClientSession]]) -> None:
        self.folder = folder  # hier liegen die installierten Plugins
        self.base_url = base_url
        self.key_hex = key_hex
        self.session = session
        # Zeitpunkt, Katalog, Katalogtext, Signatur des zuletzt geholten Stands
        self._cached: tuple[float, dict, str, str] | None = None

    async def get(self, url: str, cap: int) -> bytes:
        http = await self.session()
        async with http.get(url) as r:
            if r.status != 200:
                raise PluginError(f"{url}: HTTP {r.status}")
            data = bytearray()
            async for chunk in r.content.iter_chunked(64 * 1024):
                data += chunk
                if len(data) > cap:
                    raise PluginError(f"{url}: größer als {cap} Byte")
            return bytes(data)

    def _check_serial(self, serial: int) -> None:
        """Einen älteren Katalog als den schon gelesenen ablehnen (alter signierter Stand erneut ausgeliefert)."""
        path = self.folder / PROOF_DIR / "serials.json"
        try:
            seen = json.loads(path.read_text())
        except (OSError, ValueError):
            seen = {}
        last = int(seen.get("main", 0))
        if serial < last:
            raise PluginError(f"Der Plugin-Katalog ist älter als ein schon gelesener ({serial} < {last})")
        if serial > last:
            seen["main"] = serial
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(seen))

    async def fetch(self, max_age: float = 0) -> dict:
        now = time.monotonic()
        if self._cached and now - self._cached[0] < max_age:
            return self._cached[1]
        body, signature = await asyncio.gather(self.get(f"{self.base_url}/index.json", MAX_CATALOG),
                                               self.get(f"{self.base_url}/index.json.sig", 1024))
        text = signature.decode("ascii", "replace").strip()
        catalog = verify_catalog(body, text, self.key_hex)
        self._check_serial(int(catalog.get("serial") or 0))
        self._cached = (now, catalog, body.decode("utf-8"), text)
        return catalog

    async def download(self, entry: dict) -> list[tuple[str, bytes]]:
        plugin = str(entry.get("id"))
        if not valid_id(plugin):
            raise PluginError(f"Plugin-Kennung {plugin!r} ungültig")
        api = entry.get("apiVersion")
        if not isinstance(api, int) or not 0 < api <= API_VERSION:
            raise PluginError(f"{entry.get('name')} braucht ein neueres NexBoard (Plugin-API {api})")
        files: dict[str, str] = entry.get("files") or {}
        if "manifest.json" not in files or "index.html" not in files:
            raise PluginError(f"{entry.get('name')}: Manifest oder Seite fehlt")
        for path in files:
            if not safe_path(path):
                raise PluginError(f"{entry.get('name')}: Datei {path!r} nicht erlaubt")
        limit = asyncio.Semaphore(PARALLEL_DOWNLOADS)

        async def one(path: str, want: str) -> tuple[str, bytes]:
            url = f"{self.base_url}/{plugin}/{entry.get('version')}/{path}"
            async with limit:
                try:
                    data = await self.get(url, MAX_PLUGIN)
                except (PluginError, aiohttp.ClientError, TimeoutError):
                    data = await self.get(url, MAX_PLUGIN)
            if sha256_hex(data).lower() != want.lower():
                raise PluginError(f"{entry.get('name')}: {path} passt nicht zum Katalog, keine Installation")
            return path, data

        try:
            got = await asyncio.gather(*(one(p, h) for p, h in files.items()))
        except (aiohttp.ClientError, TimeoutError) as e:
            raise PluginError(f"Download fehlgeschlagen: {e}") from e
        if sum(len(d) for _, d in got) > MAX_PLUGIN:
            raise PluginError(f"{entry.get('name')} ist größer als {MAX_PLUGIN} Byte")
        return got

    def write(self, entry: dict, files: list[tuple[str, bytes]]) -> None:
        assert self._cached
        plugin = entry["id"]
        self.folder.mkdir(parents=True, exist_ok=True)
        staging = self.folder / f".staging-{plugin}"
        target = self.folder / plugin
        shutil.rmtree(staging, ignore_errors=True)
        try:
            for path, data in files:
                file = staging / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            manifest = load_manifest(staging)
            # Was der Zustimmungsdialog gezeigt hat (Katalog), ist, was das Manifest gewährt
            if (manifest["id"] != plugin or manifest.get("version") != entry.get("version")
                    or sorted(entry.get("permissions") or []) != sorted(manifest.get("permissions") or [])):
                raise PluginError(f"{entry.get('name')}: Manifest passt nicht zum Katalog")
            if target.is_dir():
                try:
                    old = load_manifest(target)
                except PluginError:
                    old = None
                if old and newer(str(old.get("version")), str(entry.get("version"))):
                    raise PluginError(f"{entry.get('name')} {old.get('version')} ist neuer als der Katalog")
                shutil.rmtree(target)
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        proof = self.proof(plugin)
        proof.parent.mkdir(parents=True, exist_ok=True)
        _, _, index, signature = self._cached
        proof.write_text(json.dumps({"index": index, "signature": signature}))

    def proof(self, plugin: str) -> Path:
        return self.folder / PROOF_DIR / f"{plugin}.json"

    def verify_installed(self, plugin: str, folder: Path, version: str) -> None:
        try:
            signed = json.loads(self.proof(plugin).read_text())
            index, signature = signed["index"], signed["signature"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise PluginError("ohne Nachweis aus dem Katalog: bitte neu installieren") from e
        catalog = verify_catalog(index.encode(), signature, self.key_hex)
        entry = next((e for e in catalog.get("plugins", []) if e.get("id") == plugin and e.get("version") == version), None)
        if entry is None:
            raise PluginError(f"der Katalog kennt {plugin} {version} nicht")
        check_files(entry, folder)
