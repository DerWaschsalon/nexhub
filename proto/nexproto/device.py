"""Geräteprotokoll v1 zwischen Daemon und Touch-Leiste: Grenzwerte und Nachrichten.

Beschreibung in Worten: nexboard/docs/protocol.md. Das JSON-Schema daneben und die Konstanten für die
Firmware (proto_gen.h) und die Web-UI erzeugt `python -m nexproto.codegen` aus dieser Datei.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from .classes import CLASS_KEYS

PROTO_VERSION = 1
DEFAULT_PORT = 8765
SCREEN_W, SCREEN_H = 640, 172
HEARTBEAT_S = 5
HELLO_TIMEOUT_S = 5
# Größte Nachricht, die die Firmware per WLAN annimmt (WEBSOCKETS_MAX_DATA_SIZE der Bibliothek
# WebSockets); eine größere verwirft sie still
MAX_MESSAGE_BYTES = 15 * 1024
MAX_PAGES = 8
MAX_ITEMS_PER_PAGE = 24
MAX_COLS, MAX_ROWS = 8, 3
ID_MAX = 32
LABEL_MAX = 24
ICON_MAX = 48
IMAGE_ID_MAX = 16
ART_MIN, ART_MAX = 8, 160
ART_CHUNK_BYTES = 2000  # Rohdaten je JSON-Nachricht (base64 ≈ 2,7 KB, unter dem TCP-Fenster des ESP32)
BIN_CHUNK_BYTES = 12000  # Rohdaten je Binärframe
BIN_HEADER_BYTES = 27  # "DB", Art, id (16), w, h, y, rows
DPS_MAX_ROWS = 8
DPS_DEFAULT_PLAYERS = 5
LONG_PRESS_MS = 600
SLIDER_EVENTS_PER_S = 20

Id = Annotated[str, Field(pattern=rf"^[A-Za-z0-9_-]{{1,{ID_MAX}}}$")]
ImageId = Annotated[str, Field(max_length=IMAGE_ID_MAX)]
Style = Literal["default", "accent", "danger", "success", "warning"]
ItemType = Literal["button", "toggle", "slider", "media", "dps", "claude"]
ClassKey = Literal[CLASS_KEYS]  # type: ignore[valid-type]


class _Message(BaseModel):
    """Unbekannte Felder werden ignoriert (Vorwärtskompatibilität)."""
    v: Literal[1] = PROTO_VERSION


# ------------------------------------------------------------------ Layout
class Item(BaseModel):
    id: Id
    type: ItemType = "button"
    label: str | None = Field(None, max_length=LABEL_MAX)
    icon: str | None = Field(None, max_length=ICON_MAX)
    icon_on: str | None = Field(None, max_length=ICON_MAX)
    style: Style | None = None
    bind: str | None = Field(None, max_length=ID_MAX)
    mute_bind: str | None = Field(None, max_length=ID_MAX)
    min: int | None = None
    max: int | None = None
    nav: Id | None = None
    # dps: Anzahl Spieler und Zusatzwert neben der DPS-Zahl
    players: int | None = Field(None, ge=1, le=DPS_MAX_ROWS)  # fehlt: DPS_DEFAULT_PLAYERS
    extra: Literal["pct", "dmg", "none"] | None = None
    w: int = Field(1, ge=1, le=MAX_COLS)
    h: int = Field(1, ge=1, le=MAX_ROWS)

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


class Page(BaseModel):
    id: Id
    name: str | None = Field(None, max_length=LABEL_MAX)
    cols: int = Field(6, ge=1, le=MAX_COLS)
    rows: int = Field(2, ge=1, le=MAX_ROWS)
    items: list[Item] = Field(default_factory=list, max_length=MAX_ITEMS_PER_PAGE)


class Theme(BaseModel):
    accent: str = Field("#5AC8FA", pattern=r"^#[0-9A-Fa-f]{6}$")


class Layout(BaseModel):
    theme: Theme = Field(default_factory=Theme)
    pages: list[Page] = Field(min_length=1, max_length=MAX_PAGES)

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


# ------------------------------------------------------------------ Gerät → Daemon
class DeviceInfo(BaseModel):
    id: str = Field(max_length=64)
    model: str | None = Field(None, max_length=64)
    fw: str | None = Field(None, max_length=32)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    sim: bool = False


class Hello(_Message):
    type: Literal["hello"] = "hello"
    token: str = Field(max_length=128)
    layout_hash: str | None = Field(None, max_length=64)
    page: Id | None = None
    bg_id: ImageId | None = None
    caps: list[Annotated[str, Field(max_length=16)]] = []
    device: DeviceInfo


class Event(_Message):
    type: Literal["event"] = "event"
    event: Literal["button_press", "long_press", "slider_change", "page_change"]
    item: Id | None = None
    part: Literal["prev", "toggle", "next", "reset"] | None = None
    page: Id | None = None
    value: int | None = None
    final: bool | None = None

    @model_validator(mode="after")
    def _required(self) -> "Event":
        fields = self.model_dump()
        missing = [name for name in EVENT_FIELDS[self.event] if fields[name] is None]
        if missing:
            raise ValueError(f"{self.event} ohne {', '.join(missing)}")
        return self


# Pflichtfelder je Ereignis
EVENT_FIELDS = {"button_press": ("item",), "long_press": ("item",), "slider_change": ("item", "value"),
                "page_change": ("page",)}


class ArtRequest(_Message):
    type: Literal["art_request"] = "art_request"
    size: int = Field(ge=ART_MIN, le=ART_MAX)
    have: ImageId | None = None


class Heartbeat(_Message):
    type: Literal["ping", "pong"]
    t: int


# ------------------------------------------------------------------ Daemon → Gerät
class ServerInfo(BaseModel):
    name: str
    version: str


class Welcome(_Message):
    type: Literal["welcome"] = "welcome"
    server: ServerInfo | None = None
    heartbeat: int = Field(HEARTBEAT_S, ge=1, le=60)


class Error(_Message):
    type: Literal["error"] = "error"
    code: Literal["auth", "version", "bad_request", "disabled"]
    message: str = ""


class LayoutMessage(_Message, Layout):
    type: Literal["layout"] = "layout"
    hash: str = Field(max_length=64)


class Track(BaseModel):
    title: str = ""
    artist: str = ""
    player: str = ""


class DpsRow(BaseModel):
    name: str = Field(max_length=LABEL_MAX)
    cls: ClassKey | None = None
    dps: int = Field(ge=0)
    dmg: int | None = Field(None, ge=0)
    pct: float | None = None
    you: bool = False


class Dps(BaseModel):
    target: str
    time: int = Field(ge=0)  # Kampfdauer in s
    hp: float | None = None  # Rest-HP des Bosses in %
    rows: list[DpsRow] = Field(max_length=DPS_MAX_ROWS)


class UsageLimit(BaseModel):
    pct: int = Field(ge=0)
    reset: str = ""


class ClaudeUsage(BaseModel):
    session: UsageLimit | None = None
    week: UsageLimit | None = None


class StateValues(BaseModel):
    """Bekannte Schlüssel; eigene (z. B. aus Shell-Statusbefehlen) sind erlaubt."""
    model_config = ConfigDict(extra="allow")
    out_volume: int | None = None
    out_muted: bool | None = None
    mic_volume: int | None = None
    mic_muted: bool | None = None
    playing: bool | None = None
    track: Track | None = None
    dps: Dps | None = None
    dps_active: bool | None = None
    claude: ClaudeUsage | None = None


class State(_Message):
    type: Literal["state"] = "state"
    full: bool = False
    values: StateValues


class _ImagePart(_Message):
    """Ein Bild in Zeilenstücken, RGB565 little-endian in base64; id "" = kein Bild."""
    id: ImageId
    w: int | None = None
    h: int | None = None
    y: int | None = Field(None, ge=0)
    rows: int | None = Field(None, ge=1)
    data: str | None = None

    @model_validator(mode="after")
    def _complete(self) -> "_ImagePart":
        if self.id and None in (self.w, self.h, self.y, self.rows, self.data):
            raise ValueError("Bildteil ohne w, h, y, rows oder data")
        return self


class Art(_ImagePart):
    """Cover der Medien-Kachel, genau in der Größe aus art_request."""
    type: Literal["art"] = "art"
    w: int | None = Field(None, ge=ART_MIN, le=ART_MAX)
    h: int | None = Field(None, ge=ART_MIN, le=ART_MAX)


class Background(_ImagePart):
    """Hintergrund der Leiste, immer bildschirmgroß."""
    type: Literal["bg"] = "bg"
    w: int | None = Field(None, ge=SCREEN_W, le=SCREEN_W)
    h: int | None = Field(None, ge=SCREEN_H, le=SCREEN_H)


class Goto(_Message):
    type: Literal["goto"] = "goto"
    page: Id


Message = Annotated[
    Union[Hello, Event, ArtRequest, Heartbeat, Welcome, Error, LayoutMessage, State, Art, Background, Goto],
    Field(discriminator="type"),
]
MESSAGE = TypeAdapter(Message)


def parse(data: dict | str | bytes) -> BaseModel:
    """Eine Nachricht prüfen und als Modell zurückgeben, sonst pydantic.ValidationError."""
    if isinstance(data, dict):
        return MESSAGE.validate_python(data)
    return MESSAGE.validate_json(data)
