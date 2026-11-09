"""Konfiguration: config.yaml (Server, Token) und layout.yaml (Seiten, Buttons, Aktionen)."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import tempfile
from importlib import resources
from pathlib import Path
from typing import Annotated, Any, Literal, Union

import yaml
from nexcore.settings import ADVANCED, SECRET
from nexproto import device
from pydantic import BaseModel, ConfigDict, Field, model_validator

log = logging.getLogger(__name__)

ID = device.Id


def device_message(type_: str, **fields: Any) -> str:
    """Eine Nachricht ans Gerät, so kompakt, wie sie über die Leitung geht."""
    return json.dumps({"v": device.PROTO_VERSION, "type": type_, **fields}, ensure_ascii=False,
                      separators=(",", ":"))


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ Aktionen
class MediaAction(_Strict):
    do: Literal["media"]
    op: Literal["play_pause", "play", "pause", "stop", "next", "previous"] = "play_pause"
    player: str | None = None


class VolumeAction(_Strict):
    do: Literal["volume"]
    target: Literal["sink", "source"] = "sink"
    op: Literal["toggle_mute", "mute", "unmute", "set", "step"] = "toggle_mute"
    step: int = Field(5, ge=-100, le=100, description="Prozentpunkte bei op=step")
    limit: int = Field(100, ge=1, le=150, description="Obergrenze in Prozent")


class OpenAction(_Strict):
    do: Literal["open"]
    url: str = Field(min_length=1)


class HotkeyAction(_Strict):
    do: Literal["hotkey"]
    keys: str = Field(min_length=1, description='z. B. "ctrl+shift+m" oder "f13"')


class ShellAction(_Strict):
    do: Literal["shell"]
    cmd: str = Field(min_length=1)


Action = Annotated[
    Union[MediaAction, VolumeAction, OpenAction, HotkeyAction, ShellAction],
    Field(discriminator="do"),
]


# ------------------------------------------------------------------ Layout
# Felder und Regeln fürs Gerät stehen in nexproto.device; hier kommt dazu, was nur der PC kennt
class Item(_Strict, device.Item):
    action: Action | None = None
    long_action: Action | None = None


class Page(_Strict, device.Page):
    items: list[Item] = Field(default_factory=list, max_length=device.MAX_ITEMS_PER_PAGE)


class Theme(_Strict, device.Theme):
    # "default" | "wallpaper" (KDE-Hintergrund) | Pfad zu einer Bilddatei, siehe background.py
    background: str = Field("default", min_length=1, max_length=512)


class Layout(_Strict, device.Layout):
    theme: Theme = Field(default_factory=Theme)
    pages: list[Page] = Field(min_length=1, max_length=device.MAX_PAGES)

    @model_validator(mode="after")
    def _fits_device(self) -> "Layout":
        size = len(device_message("layout", **self.device_payload()).encode())
        if size > device.MAX_MESSAGE_BYTES:
            raise ValueError(f"Layout zu groß für die Leiste ({size // 1024} KiB, höchstens "
                             f"{device.MAX_MESSAGE_BYTES // 1024} KiB): weniger Seiten oder Kacheln, kürzere Namen")
        return self

    def has_type(self, item_type: str) -> bool:
        return any(i.type == item_type for p in self.pages for i in p.items)

    def find_item(self, item_id: str) -> Item | None:
        for p in self.pages:
            for i in p.items:
                if i.id == item_id:
                    return i
        return None

    def device_payload(self) -> dict:
        """Layout für das Gerät: ohne Aktionen, ohne Default-Felder, mit Hash."""
        data = self.model_dump(
            exclude_none=True,
            exclude={
                "pages": {"__all__": {"items": {"__all__": {"action", "long_action"}}}},
                # kommt als Bild per `bg`, der Pfad bleibt auf dem PC
                "theme": {"background"},
            },
        )
        for p in data["pages"]:
            for it in p["items"]:
                if it.get("w") == 1:
                    del it["w"]
                if it.get("h") == 1:
                    del it["h"]
        body = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        data["hash"] = hashlib.sha1(body.encode()).hexdigest()[:16]
        return data


# ------------------------------------------------------------------ Einstellungen
class Settings(_Strict):
    name: str = Field("NexBoard", title="Name", description="Erscheint auf den Geräten und im Netzwerk (mDNS)")
    player: str | None = Field(None, title="Medien-Player",
                               description="Für Media-Kacheln, z. B. spotify; leer = aktivster Player (playerctl)")
    update_check: bool = Field(True, title="Nach Updates sehen",
                               description="Täglich nach neuen Versionen und A2Tools-Releases (GitHub)")
    open_browser: bool = Field(False, title="Web-UI beim Start öffnen")
    host: str = Field("0.0.0.0", title="Adresse", description="0.0.0.0 = im ganzen LAN erreichbar",
                      json_schema_extra=ADVANCED)
    port: int = Field(device.DEFAULT_PORT, ge=1, le=65535, title="Port",
                      description="Die Overlay-Seite nutzt den Port danach", json_schema_extra=ADVANCED)
    token: str = Field(min_length=8, title="Geräte-Token", description="Steht in der Firmware (secrets.h)",
                       json_schema_extra=SECRET | ADVANCED)
    heartbeat: int = Field(device.HEARTBEAT_S, ge=1, le=60, title="Herzschlag (s)",
                           description="So oft fragt der Daemon, ob ein Gerät noch da ist", json_schema_extra=ADVANCED)
    mdns: bool = Field(True, title="mDNS", description="Geräte finden den Daemon automatisch (_deckbar._tcp)",
                       json_schema_extra=ADVANCED)
    # Rückfall per USB-Kabel, wenn WLAN nicht klappt: "auto" (Espressif-Ports passiv prüfen), "off" oder fester Pfad
    usb: str = Field("auto", title="USB-Rückfall", description="auto, off oder /dev/serial/by-id/…",
                     json_schema_extra=ADVANCED)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(os.environ.get("DECKBAR_CONFIG_DIR", Path(base) / "deckbar"))


def _atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_settings(directory: Path) -> Settings:
    path = directory / "config.yaml"
    if not path.exists():
        token = secrets.token_urlsafe(18)
        text = (
            "# NexBoard-Daemon – diese Datei enthält das Geräte-Token, nicht committen.\n"
            "host: 0.0.0.0        # Adresse für Geräte (LAN). Die Web-UI antwortet trotzdem nur auf localhost.\n"
            f"port: {device.DEFAULT_PORT}\n"
            f"token: {token}\n"
            "name: NexBoard\n"
            f"heartbeat: {device.HEARTBEAT_S}\n"
            "mdns: true\n"
            "player: null          # z. B. spotify; null = playerctl wählt\n"
            "usb: auto             # Rückfall per USB-Kabel ohne WLAN; off oder fester Pfad /dev/serial/by-id/…\n"
        )
        _atomic_write(path, text, 0o600)
        log.info("neue Konfiguration mit frischem Token angelegt: %s", path)
    data = yaml.safe_load(path.read_text()) or {}
    return Settings.model_validate(data)


def save_settings(directory: Path, settings: Settings) -> None:
    """config.yaml aus der Web-UI schreiben (Kommentare gehen verloren), bleibt nur für den Nutzer lesbar."""
    header = "# NexBoard-Daemon – enthält das Geräte-Token, nicht committen. Wird von der Web-UI überschrieben.\n"
    text = yaml.safe_dump(settings.model_dump(), sort_keys=False, allow_unicode=True)
    _atomic_write(directory / "config.yaml", header + text, 0o600)


def default_layout_text() -> str:
    return resources.files("deckbar_daemon").joinpath("default_layout.yaml").read_text()


def load_layout(path: Path) -> Layout:
    if not path.exists():
        _atomic_write(path, default_layout_text())
        log.info("Beispiel-Layout angelegt: %s", path)
    data = yaml.safe_load(path.read_text()) or {}
    return Layout.model_validate(data)


def save_layout(path: Path, layout: Layout) -> None:
    data = layout.model_dump(exclude_none=True, exclude_defaults=True)
    # pages ist Pflicht und darf nie wegfallen
    data.setdefault("pages", [])
    header = "# NexBoard-Layout – wird von der Web-UI überschrieben (Kommentare gehen dabei verloren).\n"
    _atomic_write(path, header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
