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
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

log = logging.getLogger(__name__)

ID = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
Style = Literal["default", "accent", "danger", "success", "warning"]


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
class Item(_Strict):
    id: ID
    type: Literal["button", "toggle", "slider", "media", "dps"] = "button"
    label: str | None = Field(None, max_length=24)
    icon: str | None = Field(None, max_length=48)
    icon_on: str | None = Field(None, max_length=48)
    style: Style | None = None
    bind: str | None = Field(None, max_length=32)
    mute_bind: str | None = Field(None, max_length=32)
    min: int | None = None
    max: int | None = None
    nav: ID | None = None
    # dps: Anzahl Spieler und Zusatzwert neben der DPS-Zahl
    players: int | None = Field(None, ge=1, le=8)
    extra: Literal["pct", "dmg", "none"] | None = None
    w: int = Field(1, ge=1, le=8)
    h: int = Field(1, ge=1, le=3)
    action: Action | None = None
    long_action: Action | None = None

    @model_validator(mode="after")
    def _check(self) -> "Item":
        if self.type in ("toggle", "slider") and not self.bind:
            raise ValueError(f"Item '{self.id}': {self.type} braucht 'bind'")
        if self.nav and self.type != "button":
            raise ValueError(f"Item '{self.id}': 'nav' gibt es nur bei type=button")
        if self.type != "dps" and (self.players is not None or self.extra is not None):
            raise ValueError(f"Item '{self.id}': 'players' und 'extra' gibt es nur bei type=dps")
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError(f"Item '{self.id}': min muss kleiner als max sein")
        return self


class Page(_Strict):
    id: ID
    name: str | None = Field(None, max_length=24)
    cols: int = Field(6, ge=1, le=8)
    rows: int = Field(2, ge=1, le=3)
    items: list[Item] = Field(default_factory=list, max_length=24)


class Theme(_Strict):
    accent: str = Field("#5AC8FA", pattern=r"^#[0-9A-Fa-f]{6}$")
    # "default" | "wallpaper" (KDE-Hintergrund) | Pfad zu einer Bilddatei, siehe background.py
    background: str = Field("default", min_length=1, max_length=512)


class Layout(_Strict):
    theme: Theme = Field(default_factory=Theme)
    pages: list[Page] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _check(self) -> "Layout":
        page_ids = [p.id for p in self.pages]
        if len(set(page_ids)) != len(page_ids):
            raise ValueError("Seiten-IDs müssen eindeutig sein")
        item_ids = [i.id for p in self.pages for i in p.items]
        dup = {i for i in item_ids if item_ids.count(i) > 1}
        if dup:
            raise ValueError(f"Item-IDs müssen seitenübergreifend eindeutig sein: {', '.join(sorted(dup))}")
        for p in self.pages:
            for i in p.items:
                if i.nav and i.nav not in page_ids:
                    raise ValueError(f"Item '{i.id}': Seite '{i.nav}' gibt es nicht")
        return self

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
    host: str = "0.0.0.0"
    port: int = Field(8765, ge=1, le=65535)
    token: str = Field(min_length=8)
    name: str = "DeckBar"
    heartbeat: int = Field(5, ge=1, le=60)
    mdns: bool = True
    player: str | None = Field(None, description="playerctl -p … (leer = aktivster Player)")
    open_browser: bool = False
    # Gerät per USB-Kabel: "auto" (Espressif-Ports passiv prüfen), "off" oder fester Pfad
    usb: str = "auto"


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
            "# DeckBar-Daemon – diese Datei enthält das Geräte-Token, nicht committen.\n"
            "host: 0.0.0.0        # Adresse für Geräte (LAN). Die Web-UI antwortet trotzdem nur auf localhost.\n"
            "port: 8765\n"
            f"token: {token}\n"
            "name: DeckBar\n"
            "heartbeat: 5\n"
            "mdns: true\n"
            "player: null          # z. B. spotify; null = playerctl wählt\n"
            "usb: auto             # Gerät auch per USB-Kabel; off oder fester Pfad /dev/serial/by-id/…\n"
        )
        _atomic_write(path, text, 0o600)
        log.info("neue Konfiguration mit frischem Token angelegt: %s", path)
    data = yaml.safe_load(path.read_text()) or {}
    return Settings.model_validate(data)


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
    header = "# DeckBar-Layout – wird von der Web-UI überschrieben (Kommentare gehen dabei verloren).\n"
    _atomic_write(path, header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
