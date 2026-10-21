"""NexHub-Anbindung: dieses NexBoard mit einem Konto im NexHub koppeln.

Kopplung wie beim Fernseher (RFC 8628): „Koppeln“ holt beim Hub einen kurzen Code und zeigt ihn mit
Link in der Web-UI. Wer ihn im Hub unter „Geräte“ bestätigt, verbindet dieses NexBoard mit seinem
Konto. Der Daemon fragt währenddessen alle paar Sekunden nach und bekommt danach sein Geräte-Token.
Das Token steht nur hier (hub.yaml, Rechte 600); im Hub lässt sich das Gerät jederzeit entfernen.

Runs hochladen (Einstellung `upload`, standardmäßig aus): Nach jedem beendeten Run (runs.py) baut
der Daemon ein NexLog (proto/README.md) aus den Kampfdateien und Einzeltreffern des Mitschnitts und
legt es in den Postausgang (`~/.local/share/deckbar/outbox/`). Von dort geht es raus, sobald der Hub
erreichbar ist; was nicht ankommt, bleibt liegen und wird später erneut versucht. Nichts davon
hält Mitschnitt, Leiste oder Overlay auf. Ist das Modul aus, spricht der Daemon den Hub nicht an.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
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
from .runs import Run, dungeon_parts_en

log = logging.getLogger(__name__)

TIMEOUT_S = 15
CHECK_EVERY_S = 600  # Gerät noch gültig? So oft, solange das Modul an ist
MIN_POLL_S = 1.0  # schneller fragt der Daemon nie nach, egal was der Hub sagt
UPLOAD_TIMEOUT_S = 120
OUTBOX_MAX_BYTES = 500 * 1024 * 1024  # darüber fliegen die ältesten Runs raus
RETRY_S = (60, 300, 900, 1800)  # Wartezeiten nach einem Fehlschlag, dann bleibt es bei der letzten
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
    upload: bool = False  # fertige Runs hochladen (schickt Namen von Mitspielern an den Hub)

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _url(v)


class HubError(Exception):
    """Hub nicht erreichbar oder unerwartete Antwort; Text für die Web-UI."""


def default_outbox() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "deckbar" / "outbox"


def build_nexlog(run: Run, history_dir: Path, you: dict | None, language: str, capture: str | None) -> bytes:
    """Run → gepacktes NexLog. Liest die Kampfdateien und Einzeltreffer des Mitschnitts von der Platte;
    läuft in einem Thread (Packen großer Runs dauert bis ~0,1 s)."""
    from nexproto import NexLog, pack  # erst hier: fehlt das Paket, scheitert nur das Hochladen

    fights, hits = [], {}
    for f in run.fights:
        fights.append(json.loads((history_dir / f"{f.id}.json").read_text()))
        hit_file = history_dir.parent / "hits" / f"{f.id}.json"
        if hit_file.is_file():
            hits[f.id] = json.loads(hit_file.read_text())
    name, difficulty = dungeon_parts_en(run.dungeon)
    return pack(NexLog.model_validate({
        "recorder": {"nexboard": __version__, "capture": capture, "language": language},
        "run": {"dungeon_id": run.dungeon, "dungeon": name, "difficulty": difficulty, "start_ms": run.start_ms,
                "end_ms": run.end_ms, "complete": run.complete, "bosses_total": len(run.bosses()),
                "bosses_killed": run.kills},
        "you": you,
        "names": run.names,
        "fights": fights,
        "hits": hits,
    }))


class Hub:
    def __init__(self, config_dir: Path, outbox: Path | None = None) -> None:
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
        # Hochladen: Postausgang, eigener Charakter aus den Live-Daten, letztes Ergebnis
        self.outbox = outbox or default_outbox()
        self.you: dict | None = None
        self.last_upload: dict | None = None  # {ok, text, at, url}
        self._wake = asyncio.Event()
        self._failures = 0
        # setzt server.py: wo die Kampfdateien liegen, in welcher Sprache, welcher Mitschnitt
        self.history_dir: Callable[[], Path] = lambda: Path()
        self.language: Callable[[], str] = lambda: "en"
        self.capture_build: Callable[[], str | None] = lambda: None

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
        merged.update({k: v for k, v in data.items() if k in ("url", "name", "upload")})
        settings = HubSettings.model_validate(merged)
        if settings.upload and not self.settings.upload:
            self._wake.set()  # liegt schon etwas im Postausgang: gleich versuchen
        if settings.url != self.settings.url and settings.token:
            settings = settings.model_copy(update={"token": ""})
            self._forget("Neue Hub-Adresse – bitte neu koppeln")
        self.save(settings)
        return settings

    def info(self) -> dict:
        s = self.settings
        return {"settings": {"url": s.url, "name": s.name, "upload": s.upload}, "status": self.status,
                "detail": self.detail, "pairing": self.pairing, "account": self.account,
                "outbox": len(self._queued()), "last_upload": self.last_upload, "you": self.you}

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
        """Modul-Aufgabe: Gerät prüfen (beim Einschalten, dann alle 10 min) und den Postausgang leeren,
        sobald etwas Neues drin liegt oder die Wartezeit nach einem Fehlschlag um ist."""
        next_check = 0.0
        while True:
            # Vor dem Leeren zurücksetzen: ein Run, der währenddessen dazukommt, weckt sofort wieder
            self._wake.clear()
            if time.monotonic() >= next_check:
                await self.check()
                next_check = time.monotonic() + CHECK_EVERY_S
            await self.flush_outbox()
            wait = next_check - time.monotonic()
            if self._failures and self._queued():
                wait = min(wait, RETRY_S[min(self._failures, len(RETRY_S)) - 1])
            try:
                await asyncio.wait_for(self._wake.wait(), max(1.0, wait))
            except TimeoutError:
                pass

    # ------------------------------------------------------------ Runs hochladen
    async def on_fight(self, fight: dict) -> None:
        """Kampfende (DpsFeed.fight_listeners): merkt sich den eigenen Charakter für `you`."""
        for row in fight.get("rows") or []:
            if row.get("you") and row.get("name") and "*" not in row["name"]:
                self.you = {"name": str(row["name"])[:64], "cls": row.get("cls")}

    async def on_run(self, run: Run) -> None:
        """Beendeter Run (DungeonRuns.run_listeners): als NexLog in den Postausgang legen."""
        if not (self.enabled and self.settings.upload and self.settings.token):
            return
        try:
            data = await asyncio.to_thread(build_nexlog, run, self.history_dir(), self.you, self.language(),
                                           self.capture_build())
        except ImportError:
            self._note(False, "Paket nexproto fehlt: im Repo `uv tool install --force --editable ./daemon`")
            return
        except (OSError, ValueError) as e:  # Datei weg oder ungültig (ValidationError ist ein ValueError)
            self._note(False, f"Run nicht verpackt: {str(e)[:200]}")
            return
        await asyncio.to_thread(self._enqueue, f"{run.start_ms}-{run.dungeon}.nexlog.gz", data)
        log.info("NexHub: Run %s in den Postausgang (%d KB)", run.name, len(data) // 1024)
        self._failures = 0
        self._wake.set()
        await self._changed()

    def _queued(self) -> list[Path]:
        try:
            return sorted(p for p in self.outbox.iterdir() if p.name.endswith(".nexlog.gz"))
        except OSError:
            return []

    def _enqueue(self, name: str, data: bytes) -> None:
        self.outbox.mkdir(parents=True, exist_ok=True)
        tmp = self.outbox / (name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(self.outbox / name)
        # Obergrenze: die ältesten zuerst wegwerfen (Namen beginnen mit der Startzeit)
        files = self._queued()
        total = sum(p.stat().st_size for p in files)
        while total > OUTBOX_MAX_BYTES and len(files) > 1:
            oldest = files.pop(0)
            total -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            log.warning("NexHub: Postausgang voll, %s verworfen", oldest.name)

    def _note(self, ok: bool, text: str, url: str | None = None) -> None:
        self.last_upload = {"ok": ok, "text": text, "at": int(time.time()), "url": url}
        (log.info if ok else log.warning)("NexHub: %s", text)

    async def flush_outbox(self) -> None:
        """Alles im Postausgang hochladen, älteste zuerst. Bricht beim ersten Netzfehler ab."""
        if not (self.settings.upload and self.settings.token and self.settings.url):
            return
        for path in self._queued():
            data = await asyncio.to_thread(path.read_bytes)
            headers = {"Authorization": f"Bearer {self.settings.token}", "Content-Type": "application/gzip"}
            try:
                async with self.session().post(self.settings.url + "/api/runs", data=data, headers=headers,
                                               timeout=aiohttp.ClientTimeout(total=UPLOAD_TIMEOUT_S)) as r:
                    body = await r.json(content_type=None) if r.content_length != 0 else {}
                    status = r.status
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                self._failures += 1
                self._note(False, f"Hub nicht erreichbar ({e.__class__.__name__}), neuer Versuch später")
                await self._changed()
                return
            body = body if isinstance(body, dict) else {}
            if status in (200, 201):
                path.unlink(missing_ok=True)
                self._failures = 0
                self._note(True, "schon im Hub" if body.get("duplicate") else "hochgeladen", body.get("url"))
            elif status == 401:
                await self.check()  # Gerät im Hub entfernt: Token weg, Postausgang bleibt für später
                return
            elif status in (413, 422):
                # Der Hub lehnt die Datei selbst ab: beiseitelegen statt sie ewig neu zu schicken
                rejected = self.outbox / "abgelehnt"
                rejected.mkdir(exist_ok=True)
                path.replace(rejected / path.name)
                self._note(False, f"Hub lehnt den Run ab: {body.get('detail') or status}")
            else:
                self._failures += 1
                self._note(False, f"Hub antwortet {status}, neuer Versuch später")
                await self._changed()
                return
            await self._changed()
