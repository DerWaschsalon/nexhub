"""NexHub-Anbindung: dieses NexBoard mit einem Konto im NexHub koppeln.

Kopplung wie beim Fernseher (RFC 8628): „Koppeln“ holt beim Hub einen kurzen Code und zeigt ihn mit
Link in der Web-UI. Wer ihn im Hub unter „Geräte“ bestätigt, verbindet dieses NexBoard mit seinem
Konto. Der Daemon fragt währenddessen alle paar Sekunden nach und bekommt danach sein Geräte-Token.
Das Token steht nur hier (hub.yaml, Rechte 600); im Hub lässt sich das Gerät jederzeit entfernen.

Hochgeladen wird noch nichts; Runs als NexLog kommen im nächsten Schritt. Ist das Modul aus,
spricht der Daemon den Hub gar nicht an.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import time
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlsplit

import aiohttp
import yaml
from pydantic import Field, ValidationError, field_validator

from . import __version__
from .config import _atomic_write, _Strict

log = logging.getLogger(__name__)

TIMEOUT_S = 15
CHECK_EVERY_S = 600  # Gerät noch gültig? So oft, solange das Modul an ist
MIN_POLL_S = 1.0  # schneller fragt der Daemon nie nach, egal was der Hub sagt
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _url(v: str) -> str:
    """https://… oder, für einen SSH-Tunnel, http://localhost:…; das Token geht nie unverschlüsselt
    über ein fremdes Netz."""
    v = v.strip().rstrip("/")
    if not v:
        return v
    u = urlsplit(v)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("keine http(s)-Adresse")
    if u.scheme == "http" and u.hostname not in LOCAL_HOSTS:
        raise ValueError("ohne https nur localhost (z. B. per SSH-Tunnel)")
    if u.path or u.query:
        raise ValueError("nur die Adresse des Hubs, ohne Pfad")
    return v


class HubSettings(_Strict):
    url: str = Field("", max_length=200)
    name: str = Field(default_factory=lambda: socket.gethostname()[:64] or "NexBoard", min_length=1, max_length=64)
    token: str = Field("", max_length=200)  # Geräte-Token, nie in der Web-UI

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _url(v)


class HubError(Exception):
    """Hub nicht erreichbar oder unerwartete Antwort; Text für die Web-UI."""


class Hub:
    def __init__(self, config_dir: Path) -> None:
        self.path = config_dir / "hub.yaml"
        self.settings = self._load()
        self.enabled = False  # Modul an (ModuleManager)
        self.listeners: list[Callable[[], Awaitable[None]]] = []
        # Anzeige: "unpaired" | "pairing" | "paired" | "offline"
        self.status = "paired" if self.settings.token else "unpaired"
        self.detail = ""
        self.pairing: dict | None = None  # {user_code, uri, expires_at} während der Kopplung
        self.account: dict | None = None  # {device, owner} laut Hub
        self._poll_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------ Einstellungen
    def _load(self) -> HubSettings:
        try:
            return HubSettings.model_validate(yaml.safe_load(self.path.read_text()) or {})
        except FileNotFoundError:
            return HubSettings()
        except (yaml.YAMLError, ValidationError) as e:
            log.error("%s ungültig, nutze Standardwerte: %s", self.path, e)
            return HubSettings()

    def save(self, settings: HubSettings) -> None:
        header = "# NexHub-Anbindung – wird von der Web-UI überschrieben. Enthält das Geräte-Token.\n"
        text = yaml.safe_dump(settings.model_dump(), sort_keys=False, allow_unicode=True)
        _atomic_write(self.path, header + text, 0o600)
        self.settings = settings

    def update(self, data: dict) -> HubSettings:
        """Adresse und Gerätename aus der Web-UI. Eine neue Adresse heißt ein anderer Hub:
        das alte Token gilt dort nicht, also neu koppeln."""
        merged = self.settings.model_dump()
        merged.update({k: v for k, v in data.items() if k in ("url", "name")})
        settings = HubSettings.model_validate(merged)
        if settings.url != self.settings.url and settings.token:
            settings = settings.model_copy(update={"token": ""})
            self._forget("Neue Hub-Adresse – bitte neu koppeln")
        self.save(settings)
        return settings

    def info(self) -> dict:
        s = self.settings
        return {"settings": {"url": s.url, "name": s.name}, "status": self.status, "detail": self.detail,
                "pairing": self.pairing, "account": self.account}

    async def _changed(self) -> None:
        for fn in self.listeners:
            await fn()

    def _forget(self, detail: str) -> None:
        self.status, self.detail, self.account = "unpaired", detail, None

    # ------------------------------------------------------------ HTTP
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
                headers={"User-Agent": f"NexBoard/{__version__}", "X-NexBoard-Version": __version__})
        return self._session

    async def _call(self, method: str, path: str, *, auth: bool = False, json: dict | None = None) -> tuple[int, dict]:
        if not self.settings.url:
            raise HubError("Keine Hub-Adresse eingetragen")
        headers = {"Authorization": f"Bearer {self.settings.token}"} if auth else {}
        try:
            async with self.session().request(method, self.settings.url + path, json=json, headers=headers) as r:
                body = await r.json(content_type=None) if r.content_length != 0 else {}
                return r.status, body if isinstance(body, dict) else {}
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            raise HubError(f"Hub nicht erreichbar ({e.__class__.__name__})") from None

    async def close(self) -> None:
        await self.cancel_pairing(notify=False)
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------ Kopplung
    async def start_pairing(self) -> None:
        """Code beim Hub holen und im Hintergrund auf die Bestätigung warten."""
        await self.cancel_pairing(notify=False)
        status, body = await self._call("POST", "/api/devices/pair",
                                        json={"name": self.settings.name, "version": __version__})
        if status != 200:
            raise HubError(body.get("detail") or f"Hub antwortet {status}")
        self.pairing = {"user_code": body["user_code"], "uri": body["verification_uri_complete"],
                        "expires_at": int(time.time()) + int(body["expires_in"])}
        self.status, self.detail = "pairing", ""
        self._poll_task = asyncio.create_task(
            self._poll(body["device_code"], float(body.get("interval", 5)), int(body["expires_in"])))
        await self._changed()

    async def cancel_pairing(self, notify: bool = True) -> None:
        task, self._poll_task = self._poll_task, None
        if task and task is not asyncio.current_task():
            task.cancel()
        if self.pairing:
            self.pairing = None
            if self.status == "pairing":
                self.status = "paired" if self.settings.token else "unpaired"
            if notify:
                await self._changed()

    async def _poll(self, device_code: str, interval: float, expires_in: int) -> None:
        deadline = time.monotonic() + expires_in
        while time.monotonic() < deadline:
            await asyncio.sleep(max(interval, MIN_POLL_S))
            try:
                status, body = await self._call("POST", "/api/devices/pair/poll", json={"device_code": device_code})
            except HubError:
                continue  # kurz weg (Tunnel, WLAN): weiter versuchen, bis der Code abläuft
            if status == 200 and body.get("status") == "approved" and body.get("token"):
                self.save(self.settings.model_copy(update={"token": body["token"]}))
                self.pairing, self._poll_task = None, None
                log.info("NexHub: gekoppelt als %s", body.get("device_name"))
                await self.check()
                return
            if status != 200:
                break  # 410: abgelaufen oder unbekannt
        self.pairing, self._poll_task = None, None
        self._forget("Code abgelaufen – bitte neu koppeln")
        await self._changed()

    async def unpair(self) -> None:
        """Abkoppeln: im Hub austragen (wenn erreichbar) und das Token hier vergessen."""
        if self.settings.token:
            try:
                await self._call("DELETE", "/api/devices/me", auth=True)
            except HubError as e:
                log.warning("NexHub: Abmelden im Hub fehlgeschlagen (%s), Token wird trotzdem gelöscht", e)
        self.save(self.settings.model_copy(update={"token": ""}))
        self._forget("Abgekoppelt")
        await self._changed()

    # ------------------------------------------------------------ Laufender Betrieb
    async def check(self) -> None:
        """Gilt das Token noch, und wem gehört das Gerät? Ergebnis in status/account."""
        if not self.settings.token:
            if self.status != "pairing":
                self._forget(self.detail)
        else:
            try:
                status, body = await self._call("GET", "/api/devices/me", auth=True)
            except HubError as e:
                self.status, self.detail = "offline", str(e)
            else:
                if status == 200:
                    self.status, self.detail = "paired", ""
                    self.account = {"device": body.get("name"), "owner": body.get("owner")}
                elif status == 401:
                    # Im Hub entfernt oder Konto gesperrt: das Token ist wertlos
                    self.save(self.settings.model_copy(update={"token": ""}))
                    self._forget("Im Hub entfernt – bei Bedarf neu koppeln")
                else:
                    self.status, self.detail = "offline", f"Hub antwortet {status}"
        await self._changed()

    async def watch(self) -> None:
        """Modul-Aufgabe: beim Einschalten und dann regelmäßig nachsehen, ob das Gerät noch gilt."""
        while True:
            await self.check()
            await asyncio.sleep(CHECK_EVERY_S)
