"""AION-2-Dungeon-Runs: nach jedem Run ein PNG mit der Schadensaufteilung pro Boss nach Discord.

Quelle ist nicht der Live-Stream (dps.py), sondern die Kampf-History im Format des A2Tools-Meters,
geschrieben von deckbar-capture (Quelle `capture`) oder vom Meter selbst:
Für jeden Bosskampf entsteht `history/<id>.json`, mit Dungeon, Boss, maximalen HP und
dem Schaden jeder Fähigkeit pro Spieler. Die Datei entsteht schon während des Kampfs und
wird laufend neu geschrieben – sie wird deshalb bei jeder Änderung neu gelesen, und ein
beendeter Run geht erst raus, wenn seine Dateien `SETTLE_RUN_S` lang ruhen. Aufeinanderfolgende Kämpfe im selben Dungeon
ergeben einen Run. Er endet,
  - sobald der Endboss liegt: laut `END_BOSSES` (recherchiert, englische Namen aus den
    Meter-Daten), sonst der Boss mit den meisten HP, den es in diesem Dungeon in früheren
    Runs schon gab – im ersten Run eines nicht gelisteten Dungeons ist er also unbekannt,
  - wenn der nächste Kampf in einem anderen Dungeon stattfindet oder ein in diesem Run
    schon besiegter Boss wieder auftaucht,
  - oder nach `idle_minutes` ohne neuen Bosskampf.
Gepostet wird jeder Run mit mindestens einem besiegten Boss, per Discord-Webhook.

Das Meter speichert fremde Namen maskiert („Mo***n“: zwei Zeichen vorn, eins hinten), der
Live-Stream (State `dps`) zeigt sie aber voll. Die NexBoard merkt sich die vollen Namen
(Schlüssel „Maske|Klasse“, in runs-state.json); von Hand in der Web-UI Eingetragenes
(`names` in runs.yaml) hat Vorrang.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiohttp
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pydantic import Field, ValidationError, field_validator

from .config import _atomic_write, _Strict
from .dps import a2tools_settings_path

log = logging.getLogger(__name__)

POLL_S = 5
# Datei erst lesen, wenn das Meter sie so lange nicht mehr angefasst hat
SETTLE_S = 2
# Beendeten Run erst posten, wenn keine seiner Dateien sich so lange geändert hat
SETTLE_RUN_S = 20
# Beim Start nachgeholte Runs nur posten, wenn sie so frisch sind
LATE_POST_S = 3600
KILL_RATIO = 0.97
# gelernte Namen (runs-state.json); Weltbosse bringen schnell Dutzende Fremde mit
MAX_LEARNED = 1000
# Endbosse je Dungeon (englischer Name wie in i18n/npcs/en.json, gilt für alle Schwierigkeiten
# und Stufen). Recherche 11.10.2026: metabot.gg, games.gg, gamesfuze.com, thegameswiki.com, u4n.com.
# Nicht gelistet, weil unklar: Mirror of Scarlet Desire, Consumed Deus Research Base – dort
# greift weiter das Lernen über die HP.
END_BOSSES = {
    "Ultimate Berk",  # Krao Cave
    "Divine Auldor",  # Urugugu Canyon
    "Kromede's Desire",  # Fire Temple
    "Transcendent Bakarma",  # Draupnir
    "Decaying Durvati",  # Dying Dramata's Nest (nicht „… (Specimen)“)
    "Atiel",  # Deus Research Base (erscheint nach Gelcos + Nazmun)
    "Talisra of the Void",  # Shattered Arkanis (keine Quelle; im Spiel zuletzt, doppelte HP)
    "Vakron",  # Vakron Sky Island
    "Ferocious Horn Nuakum",  # Ferocious Horn Den
    "Afflicted Bakarma",  # Cradle of Nihility
    "Nathara",  # Hall of Illusion
    "Awakened Alturadon",  # Azure Breath Island
    "Basilus the False",  # Citadel of the Fallen Daeva
    "Submerged Emon",  # Submerged Life Temple
    "Gargaum",  # Abyssal Horn Den
}
WEBHOOK_RE = re.compile(r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")

# jobId der History → Klassen-Schlüssel wie im Live-Stream (dps.CLASSES)
JOBS = {11: "gladiator", 12: "templar", 13: "assassin", 14: "ranger", 15: "sorcerer",
        16: "spiritmaster", 17: "cleric", 18: "chanter"}
CLASS_NAMES = {"gladiator": "Gladiator", "templar": "Templer", "assassin": "Assassine", "ranger": "Waldläufer",
               "sorcerer": "Magier", "spiritmaster": "Beschwörer", "cleric": "Kleriker", "chanter": "Kantor"}
# wie CLASS_COLORS in web/app.js, damit Bild und Kachel gleich aussehen
CLASS_COLORS = {"gladiator": "#E8A33D", "templar": "#5B8DEF", "ranger": "#6CCB5F", "assassin": "#B46AE6",
                "sorcerer": "#4FC3F7", "cleric": "#F4E07A", "spiritmaster": "#EC7FB8", "chanter": "#4DD4B0"}


class RunSettings(_Strict):
    enabled: bool = False
    webhook: str = Field("", max_length=200)
    # Minuten ohne neuen Bosskampf, nach denen ein Run als beendet gilt
    idle_minutes: int = Field(15, ge=2, le=120)
    # „Mo***n|ranger“ → echter Name
    names: dict[str, str] = Field(default_factory=dict, max_length=200)

    @field_validator("webhook")
    @classmethod
    def _webhook(cls, v: str) -> str:
        v = v.strip()
        if v and not WEBHOOK_RE.match(v):
            raise ValueError("keine Discord-Webhook-URL (https://discord.com/api/webhooks/…)")
        return v

    @field_validator("names")
    @classmethod
    def _names(cls, v: dict[str, str]) -> dict[str, str]:
        out = {}
        for k, name in v.items():
            name = name.strip()[:24]
            if name and len(k) <= 48:
                out[k] = name
        return out


def mask(name: str) -> str:
    """So maskiert das A2Tools-Meter Namen in der History: 2 Zeichen vorn, 1 hinten, höchstens 4 Sterne
    („Ironwhisper“ → „Ir****r“); kurze Namen: „Kan“ → „K*n“, „Xu“ → „X*“."""
    if "*" in name or len(name) < 2:
        return name
    if len(name) == 2:
        return name[0] + "*"
    head = 1 if len(name) == 3 else 2
    return name[:head] + "*" * min(4, len(name) - head - 1) + name[-1]


def char_key(name: str, cls: str | None) -> str:
    return f"{mask(name)}|{cls or ''}"


# ---------------------------------------------------------------- Daten des Meters
def a2tools_dir() -> Path:
    return a2tools_settings_path().parent


REPO_DATA = Path(__file__).resolve().parents[2] / "capture" / "a2tools" / "src" / "data"


def a2tools_data_dir() -> Path:
    """Übersetzungen (Boss-, Dungeonnamen): installiertes Meter, sonst das Submodul im Repo."""
    if env := os.environ.get("DECKBAR_A2TOOLS_DATA"):
        return Path(env)
    installed = Path("/usr/lib/A2Tools DPS Meter/data")
    return installed if installed.is_dir() or not REPO_DATA.is_dir() else REPO_DATA


@cache
def _i18n(name: str) -> dict:
    try:
        data = json.loads((a2tools_data_dir() / "i18n" / name).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def boss_name(mob: int, fallback: str) -> str:
    return (_i18n("npcs/de.json").get(str(mob)) or {}).get("name") or fallback or f"Boss {mob}"


def is_end_boss(mob: int) -> bool:
    return (_i18n("npcs/en.json").get(str(mob)) or {}).get("name") in END_BOSSES


def dungeon_name(dungeon: int) -> str:
    entry = _i18n("dungeons/en.json").get(str(dungeon)) or {}
    name = entry.get("name") or f"Dungeon {dungeon}"
    diff = {"normal": "Normal", "exploration": "Erkundung", "hard": "Schwer"}.get(entry.get("difficulty"))
    return f"{name} ({diff})" if diff else name


def dungeon_parts_en(dungeon: int) -> tuple[str, str | None]:
    """Englischer Name und Schwierigkeit („Hard“) – sprachunabhängig, für Weitergaben an andere
    Programme (bot.py), damit Meldungen verschiedener Spieler zusammenpassen."""
    entry = _i18n("dungeons/en.json").get(str(dungeon)) or {}
    diff = {"normal": "Normal", "exploration": "Exploration", "hard": "Hard"}.get(entry.get("difficulty"))
    return entry.get("name") or f"Dungeon {dungeon}", diff


def boss_name_en(mob: int, fallback: str = "") -> str:
    return (_i18n("npcs/en.json").get(str(mob)) or {}).get("name") or fallback or f"Boss {mob}"


@dataclass
class Player:
    name: str
    cls: str | None
    dmg: int
    you: bool = False

    @property
    def key(self) -> str:
        return char_key(self.name, self.cls)


@dataclass
class Fight:
    id: str
    dungeon: int
    mob: int
    boss: str
    start_ms: int
    duration_ms: int
    max_hp: int
    dealt: int  # Schaden am Boss insgesamt
    killed: bool
    players: list[Player]

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


def parse_fight(data: dict, you_actor: int | None = None) -> Fight | None:
    """History-Eintrag → Fight; None für Übungspuppen und Kämpfe außerhalb von Dungeons."""
    try:
        dungeon = int(data.get("dungeonId") or 0)
        mob = int(data.get("mobCode") or 0)
        details = data.get("details") or {}
        if not dungeon or data.get("isTrain") or (_i18n("npcs/de.json").get(str(mob)) or {}).get("isDummy"):
            return None
        dmg: dict[int, int] = {}
        for s in details.get("skills") or []:
            dmg[s["actorId"]] = dmg.get(s["actorId"], 0) + max(0, int(s.get("dmg") or 0))
        players = [
            Player(str(a.get("nickname") or "?")[:24], JOBS.get(a.get("jobId")), dmg.get(a["actorId"], 0),
                   a["actorId"] == you_actor)
            for a in data.get("actors") or [] if dmg.get(a["actorId"])
        ]
        max_hp = int(details.get("maxHp") or 0)
        total = int(details.get("totalTargetDamage") or data.get("totalDamage") or 0)
        return Fight(
            id=str(data["id"]), dungeon=dungeon, mob=mob, boss=boss_name(mob, str(data.get("bossName") or "")),
            start_ms=int(data["startTimeMs"]), duration_ms=max(0, int(data.get("durationMs") or 0)),
            max_hp=max_hp, dealt=total, killed=max_hp > 0 and total >= max_hp * KILL_RATIO, players=players,
        )
    except (KeyError, TypeError, ValueError):
        return None


def load_fight(path: Path) -> Fight | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    you = None
    try:  # wer das Meter laufen hat, steht in der zugehörigen slices-Datei
        you = json.loads((path.parent.parent / "slices" / path.name).read_text()).get("uploaderActorId")
    except (OSError, ValueError, AttributeError):
        pass
    return parse_fight(data, you) if isinstance(data, dict) else None


# ---------------------------------------------------------------- Runs
@dataclass
class Boss:
    mob: int
    name: str
    duration_ms: int = 0
    attempts: int = 0
    killed: bool = False
    max_hp: int = 0
    best: float = 0.0  # größter Anteil der HP, der in einem Kampf weg war (0–1)
    players: dict[str, Player] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(p.dmg for p in self.players.values())


@dataclass
class Run:
    dungeon: int
    fights: list[Fight] = field(default_factory=list)
    complete: bool = False  # Endboss besiegt
    names: dict[str, str] = field(default_factory=dict)  # echte Namen zu maskierten (siehe rename)

    @property
    def start_ms(self) -> int:
        return self.fights[0].start_ms

    @property
    def end_ms(self) -> int:
        return max(f.end_ms for f in self.fights)

    @property
    def name(self) -> str:
        return dungeon_name(self.dungeon)

    def rename(self, names: dict[str, str]) -> None:
        """Maskierte Namen beim Auswerten durch bekannte echte ersetzen (die Kämpfe bleiben unverändert)."""
        self.names = dict(names)

    def _display(self, p: Player) -> str:
        return self.names.get(p.key, p.name) if "*" in p.name else p.name

    def bosses(self) -> list[Boss]:
        """Kämpfe pro Boss zusammengefasst (mehrere Versuche oder vom Meter geteilte Kämpfe)."""
        out: dict[int, Boss] = {}
        for f in self.fights:
            b = out.setdefault(f.mob, Boss(f.mob, f.boss))
            b.duration_ms += f.duration_ms
            b.attempts += 1
            b.killed |= f.killed
            b.max_hp = max(b.max_hp, f.max_hp)
            if f.max_hp:
                b.best = max(b.best, min(1.0, f.dealt / f.max_hp))
            for p in f.players:
                q = b.players.setdefault(p.key, Player(self._display(p), p.cls, 0, p.you))
                q.dmg += p.dmg
                q.you |= p.you
                if "*" in q.name and "*" not in p.name:
                    q.name = p.name
        return list(out.values())

    def total(self) -> Boss:
        t = Boss(0, "Gesamt")
        for b in self.bosses():
            t.duration_ms += b.duration_ms
            for key, p in b.players.items():
                q = t.players.setdefault(key, Player(p.name, p.cls, 0, p.you))
                q.dmg += p.dmg
                q.you |= p.you
        return t

    @property
    def kills(self) -> int:
        return sum(b.killed for b in self.bosses())


class RunTracker:
    """Setzt Kämpfe zu Runs zusammen. `known` = maximale HP je Boss aus abgeschlossenen Runs,
    `listed` = Dungeons, deren Endboss in `END_BOSSES` steht (dort zählt nur die Liste)."""

    def __init__(self, idle_ms: int) -> None:
        self.idle_ms = idle_ms
        self.known: dict[int, dict[int, int]] = {}
        self.listed: set[int] = set()
        self.run: Run | None = None

    def learn(self, f: Fight) -> None:
        mobs = self.known.setdefault(f.dungeon, {})
        mobs[f.mob] = max(mobs.get(f.mob, 0), f.max_hp)
        if is_end_boss(f.mob):
            self.listed.add(f.dungeon)

    def end_boss(self, dungeon: int) -> int | None:
        mobs = self.known.get(dungeon)
        return max(mobs, key=mobs.__getitem__) if mobs else None

    def _is_end(self, f: Fight) -> bool:
        if not f.killed:
            return False
        if is_end_boss(f.mob):
            return True
        return f.dungeon not in self.listed and f.mob == self.end_boss(f.dungeon)

    def _close(self, complete: bool) -> Run:
        run, self.run = self.run, None
        assert run is not None
        run.complete = complete
        for f in run.fights:
            self.learn(f)
        return run

    def add(self, f: Fight) -> list[Run]:
        """Neuer Kampf oder neuer Stand eines Kampfs (gleiche id) → ggf. beendete Runs."""
        if self.run:
            for i, old in enumerate(self.run.fights):
                if old.id == f.id:
                    self.run.fights[i] = f
                    if self._is_end(f):
                        return [self._close(True)]
                    return []
        closed = []
        if self.run and (f.dungeon != self.run.dungeon or f.start_ms - self.run.end_ms > self.idle_ms
                         or self._again(f)):
            closed.append(self._close(False))
        if self.run is None:
            self.run = Run(f.dungeon)
        self.run.fights.append(f)
        if self._is_end(f):
            closed.append(self._close(True))
        return closed

    def _again(self, f: Fight) -> bool:
        """Schon besiegter Boss taucht wieder auf (nicht bloß der gleiche Kampf weiter) → nächster Run."""
        assert self.run is not None
        last = self.run.fights[-1]
        return last.mob != f.mob and any(x.mob == f.mob and x.killed for x in self.run.fights)

    def check_idle(self, now_ms: int) -> list[Run]:
        if self.run and now_ms - self.run.end_ms > self.idle_ms:
            return [self._close(False)]
        return []


# ---------------------------------------------------------------- Bild
# Optik nach dem A2Tools-Meter (src/styles.css dort): dunkles HUD, Balken als Tönung hinter der
# Zeile mit leuchtender Kante, Klassen-Icons, schmale Ziffern. Gezeichnet in doppelter Größe (S).
ASSETS = Path(__file__).parent / "assets"
WEB = Path(__file__).parent / "web"
S = 2
HUD_BG = (9, 13, 24)
ROW_FILL = (95, 191, 135)  # --row-fill
USER_FILL = (106, 166, 255)  # --isUser-fill
HP_KILL = ((71, 212, 125), (46, 167, 95), (216, 255, 232))  # Verlauf oben/unten, Kante
HP_OPEN = ((240, 187, 82), (207, 145, 44), (255, 240, 208))
END_DOT = (123, 109, 255)  # --indicator-end
WHITE = (255, 255, 255)


def _rgba(c: tuple[int, int, int], a: float) -> tuple[int, int, int, int]:
    return (*c, round(255 * a))


def _mix(c: tuple[int, int, int], other: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """t = Anteil von c (wie color-mix(in srgb, c t, other))."""
    return tuple(round(a * t + b * (1 - t)) for a, b in zip(c, other))  # type: ignore[return-value]


@cache
def _font_file(spec: str) -> str | None:
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", spec], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


@cache
def font(kind: str, size: float) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """kind: name/name_bold (Inter wie Pretendard), num/num_bold (Barlow Semi Condensed wie Bahnschrift), cjk."""
    files = {
        "name": WEB / "Inter-Medium.woff2",
        "name_bold": WEB / "Inter-SemiBold.woff2",
        "num": ASSETS / "fonts" / "BarlowSemiCondensed-SemiBold.ttf",
        "num_bold": ASSETS / "fonts" / "BarlowSemiCondensed-Bold.ttf",
    }
    path = str(files[kind]) if kind in files else _font_file("Noto Sans CJK KR:medium")
    px = round(size * S)
    try:
        return ImageFont.truetype(path, px) if path else ImageFont.load_default(px)
    except OSError:
        return ImageFont.load_default(px)


def name_font(name: str, size: float, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Inter hat kein Chinesisch/Koreanisch/Japanisch – dafür Noto Sans CJK (wie .name.isCjk im Meter)."""
    if any(ord(ch) >= 0x2E80 for ch in name):
        return font("cjk", size - 0.5)
    return font("name_bold" if bold else "name", size)


@cache
def class_icon(cls: str, size: int) -> Image.Image | None:
    try:
        return Image.open(ASSETS / "classes" / f"{cls}.png").convert("RGBA").resize((size, size), Image.LANCZOS)
    except OSError:
        return None


def fmt_amount(v: float) -> str:
    if v >= 1e6:
        return f"{v / 1e6:.2f} M".replace(".", ",")
    if v >= 1e4:
        return f"{v / 1e3:.1f} k".replace(".", ",")
    return f"{v:,.0f}".replace(",", ".")


def fmt_time(ms: int) -> str:
    s = round(ms / 1000)
    return f"{s // 60}:{s % 60:02d}"


def _tracked(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, f, fill, tracking: float,
             anchor: str = "la") -> float:
    """Text mit Laufweite (letter-spacing); gibt die Breite zurück. anchor: la oder ra."""
    gap = tracking * S
    w = sum(d.textlength(ch, font=f) for ch in text) + gap * (len(text) - 1)
    x, y = xy
    if anchor == "ra":
        x -= w
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + gap
    return w


def _hgrad(w: int, h: int, color: tuple[int, int, int], a0: float, a1: float) -> Image.Image:
    """Waagerechter Verlauf derselben Farbe von Deckkraft a0 nach a1."""
    # linear_gradient läuft von oben (0) nach unten (255); gespiegelt an der Diagonale → links nach rechts
    mask = Image.linear_gradient("L").transpose(Image.TRANSPOSE).resize((max(1, w), max(1, h)))
    mask = mask.point(lambda v: round(255 * (a0 + (a1 - a0) * v / 255)))
    img = Image.new("RGBA", mask.size, color)
    img.putalpha(mask)
    return img


def _vgrad(w: int, h: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    mask = Image.linear_gradient("L").resize((max(1, w), max(1, h)))
    return Image.composite(Image.new("RGBA", mask.size, bottom), Image.new("RGBA", mask.size, top), mask)


def _rounded(img: Image.Image, r: int) -> Image.Image:
    """Ecken abrunden (overflow: hidden mit border-radius)."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, fill=255)
    out = img.copy()
    out.putalpha(Image.composite(img.getchannel("A"), mask, mask))
    return out


class _Layers:
    """Grundfläche, Leuchten (weichgezeichnet), Textschatten (weichgezeichnet), Text – wie im CSS gestapelt."""

    def __init__(self, size: tuple[int, int]) -> None:
        self.base = Image.new("RGBA", size, (0, 0, 0, 0))
        self.glow = Image.new("RGBA", size, (0, 0, 0, 0))
        self.shadow = Image.new("RGBA", size, (0, 0, 0, 0))
        self.text = Image.new("RGBA", size, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.base)
        self.g = ImageDraw.Draw(self.glow)
        self.s = ImageDraw.Draw(self.shadow)
        self.t = ImageDraw.Draw(self.text)

    def label(self, xy, text, f, fill, anchor="la", shadow=0.85) -> None:
        self.s.text((xy[0], xy[1] + S), text, font=f, fill=(0, 0, 0, round(255 * shadow)), anchor=anchor)
        self.t.text(xy, text, font=f, fill=fill, anchor=anchor)

    def flatten(self) -> Image.Image:
        out = self.base
        out.alpha_composite(self.glow.filter(ImageFilter.GaussianBlur(4 * S)))
        out.alpha_composite(self.shadow.filter(ImageFilter.GaussianBlur(1.5 * S)))
        out.alpha_composite(self.text)
        return out


PANEL_W = 400  # CSS-Pixel wie im Meter (dort 380)
ROW_H = 30
ROW_GAP = 3
PAD = 8


def _panel_height(boss: Boss) -> int:
    rows = len(boss.players)
    head = 40 + (24 if boss.mob else 0)
    return head + 7 + rows * ROW_H + max(0, rows - 1) * ROW_GAP + 9


def _hp_strip(L: _Layers, x: int, y: int, w: int, boss: Boss) -> None:
    """Wie die Boss-HP-Leiste im Meter: besiegt = voll und grün, sonst bernstein bis zum besten Versuch."""
    h = 16 * S
    L.d.rounded_rectangle((x, y, x + w, y + h), 4 * S, fill=(0, 0, 0, 90))
    top, bottom, edge = HP_KILL if boss.killed else HP_OPEN
    fw = round(w * (1.0 if boss.killed else boss.best))
    if fw > 2 * S:
        fill = _vgrad(fw, h, top, bottom)
        fill.putalpha(Image.new("L", fill.size, round(255 * 0.8)))
        L.base.alpha_composite(_rounded(fill, 4 * S), (x, y))
        L.d.rectangle((x + fw - 2 * S, y, x + fw, y + h), fill=edge)
        L.g.rectangle((x + fw - 2 * S, y, x + fw, y + h), fill=_rgba(top, 0.9))
    f = font("num", 10.5)
    left = "BESIEGT" if boss.killed else f"{round(100 * boss.best)} % · NICHT BESIEGT"
    L.s.text((x + 8 * S, y + 2.5 * S + S), left, font=f, fill=(0, 0, 0, 230))
    _tracked(L.t, (x + 8 * S, y + 2.5 * S), left, f, WHITE, 0.6)
    if boss.max_hp:
        hp = f"{fmt_amount(boss.max_hp)} HP"
        L.s.text((x + w - 8 * S, y + 2.5 * S + S), hp, font=f, fill=(0, 0, 0, 230), anchor="ra")
        L.t.text((x + w - 8 * S, y + 2.5 * S), hp, font=f, fill=_rgba(WHITE, 0.72), anchor="ra")


def _row(L: _Layers, x: int, y: int, w: int, rank: int, p: Player, best: int, total: int, secs: float) -> None:
    h = ROW_H * S
    row = Image.new("RGBA", (w, h), (255, 255, 255, 9))  # --hud-row-bg
    bar = USER_FILL if p.you else ROW_FILL
    fw = max(2 * S, round(w * p.dmg / best))
    # Balken = Tönung hinter der Zeile (30 % → 62 %, mal 0,8 Deckkraft) …
    row.alpha_composite(_hgrad(fw, h, bar, 0.30 * 0.8, 0.62 * 0.8))
    rd = ImageDraw.Draw(row)
    # … mit heller Kante am Ende, die leuchtet
    rd.rectangle((fw - 2 * S, 0, fw - 1, h), fill=_mix(bar, WHITE, 0.35))
    if p.you:  # eigene Zeile: Leuchtschiene links
        rd.rectangle((0, 0, 2 * S - 1, h), fill=USER_FILL)
    # Abdunklung hinter den Zahlen rechts (wie der Scrim im Meter)
    scrim_w = 190 * S
    row.alpha_composite(_hgrad(scrim_w, h, HUD_BG, 0.0, 0.8), (w - scrim_w, 0))
    L.base.alpha_composite(_rounded(row, 4 * S), (x, y))
    L.g.rectangle((x + fw - 3 * S, y, x + fw + S, y + h), fill=_rgba(bar, 0.75))
    if p.you:
        L.g.rectangle((x, y, x + 2 * S, y + h), fill=_rgba(USER_FILL, 0.7))

    cy = y + h // 2
    cx = x + 6 * S
    rf = font("num", 11)
    L.label((cx + 13 * S, cy), str(rank), rf, _rgba(WHITE, 0.8 if rank == 1 else 0.3), anchor="rm", shadow=0.9)
    cx += 13 * S + 7 * S
    icon = class_icon(p.cls, 20 * S) if p.cls else None
    if icon:
        sh = Image.new("RGBA", icon.size, (0, 0, 0, 0))
        sh.putalpha(icon.getchannel("A").point(lambda v: v * 0.8))
        L.shadow.alpha_composite(sh, (cx, cy - 10 * S + S))
        L.text.alpha_composite(icon, (cx, cy - 10 * S))
    cx += 20 * S + 7 * S
    nf = name_font(p.name, 14.5, p.you)
    L.label((cx, cy), p.name, nf, _rgba(WHITE, 0.95), anchor="lm")

    # Anzeige rechts: Gesamtschaden (leise) · DPS (groß) · Anteil
    rx = x + w - 8 * S
    pct = f"{100 * p.dmg / total:.1f}".replace(".", ",") + " %"
    pf, df, sf = font("num", 11.5), font("num_bold", 16.5), font("num", 11.5)
    L.label((rx, cy), pct, pf, _rgba(WHITE, 0.88), anchor="rm", shadow=0.95)
    rx -= max(L.t.textlength(pct, font=pf), 40 * S) + 9 * S
    dps = fmt_amount(p.dmg / secs) + "/s"
    L.label((rx, cy), dps, df, WHITE, anchor="rm", shadow=0.95)
    rx -= L.t.textlength(dps, font=df) + 10 * S
    L.label((rx, cy), fmt_amount(p.dmg), sf, _rgba(WHITE, 0.45), anchor="rm", shadow=0.9)


def _panel(boss: Boss, height: int) -> Image.Image:
    w, h = PANEL_W * S, height * S
    L = _Layers((w, h))
    L.d.rounded_rectangle((0, 0, w - 1, h - 1), 10 * S, fill=(*_mix(WHITE, HUD_BG, 0.035), 245),
                          outline=(255, 255, 255, 31), width=S)
    # Kopf: Bossname links, Kampfzeit (+ Versuche) rechts
    tf = font("name_bold", 15.5)
    L.label((12 * S, 21 * S), boss.name if boss.mob else "Gesamt", tf, _rgba(WHITE, 0.96), anchor="lm")
    mf = font("num", 13)
    meta = fmt_time(boss.duration_ms)
    if boss.attempts > 1:
        meta = f"{boss.attempts} Kämpfe · {meta}"
    if not boss.mob:
        meta = f"Kampfzeit {meta}"
    L.label((w - 12 * S, 21 * S), meta, mf, _rgba(WHITE, 0.5), anchor="rm")
    y = 40 * S
    if boss.mob:
        _hp_strip(L, PAD * S, y, w - 2 * PAD * S, boss)
        y += 24 * S
    y += 7 * S
    players = sorted(boss.players.values(), key=lambda p: -p.dmg)
    best = max((p.dmg for p in players), default=1) or 1
    total = boss.total or 1
    secs = max(1.0, boss.duration_ms / 1000)
    for i, p in enumerate(players):
        _row(L, PAD * S, y, w - 2 * PAD * S, i + 1, p, best, total, secs)
        y += (ROW_H + ROW_GAP) * S
    return L.flatten()


def render_run(run: Run) -> bytes:
    """Run → PNG: Kopf mit Dungeon, dann je ein Meter-Fenster für „Gesamt“ und jeden Boss."""
    bosses = run.bosses()
    panels = [run.total(), *bosses] if len(bosses) > 1 else bosses
    cols = 1 if len(panels) == 1 else 2 if len(panels) <= 4 else 3
    rows = [panels[i:i + cols] for i in range(0, len(panels), cols)]
    heights = [max(_panel_height(b) for b in r) for r in rows]
    gap, margin, head, foot = 16, 28, 92, 30
    W = (margin * 2 + cols * PANEL_W + (cols - 1) * gap) * S
    H = (margin + head + sum(heights) + gap * (len(rows) - 1) + foot) * S

    img = Image.new("RGBA", (W, H), (*HUD_BG, 255))
    # leichtes Leuchten oben links, damit die Fläche nicht tot wirkt
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((-W // 4, -H // 2, W // 2, H // 3), fill=(95, 202, 255, 22))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(80 * S)))

    L = _Layers((W, H))
    x0 = margin * S
    L.label((x0, margin * S), run.name, font("name_bold", 28), WHITE, shadow=0.6)
    start = datetime.fromtimestamp(run.start_ms / 1000)
    end = datetime.fromtimestamp(run.end_ms / 1000)
    kills = run.kills
    sub = (f"{start:%d.%m.%Y}  ·  {start:%H:%M}–{end:%H:%M}  ·  {kills}/{len(bosses)} "
           f"{'BOSS' if len(bosses) == 1 else 'BOSSE'}  ·  KAMPFZEIT {fmt_time(sum(b.duration_ms for b in bosses))}")
    _tracked(L.t, (x0, (margin + 44) * S), sub, font("num", 14), _rgba(WHITE, 0.5), 0.8)
    # Status-Chip rechts oben
    chip = "RUN ABGESCHLOSSEN" if run.complete or kills == len(bosses) else "RUN BEENDET"
    cf = font("num", 12)
    cw = sum(L.t.textlength(ch, font=cf) for ch in chip) + 0.8 * S * (len(chip) - 1)
    cx1, cy0 = W - x0, (margin + 6) * S
    cx0 = cx1 - cw - 34 * S
    L.d.rounded_rectangle((cx0, cy0, cx1, cy0 + 26 * S), 13 * S, fill=(255, 255, 255, 14), outline=(255, 255, 255, 36), width=S)
    dot = END_DOT if chip == "RUN ABGESCHLOSSEN" else HP_OPEN[0]
    L.d.ellipse((cx0 + 12 * S, cy0 + 10 * S, cx0 + 18 * S, cy0 + 16 * S), fill=dot)
    L.g.ellipse((cx0 + 10 * S, cy0 + 8 * S, cx0 + 20 * S, cy0 + 18 * S), fill=_rgba(dot, 0.9))
    _tracked(L.t, (cx0 + 25 * S, cy0 + 5.5 * S), chip, cf, _rgba(WHITE, 0.85), 0.8)
    img.alpha_composite(L.flatten())

    y = (margin + head) * S
    for r, rh in zip(rows, heights):
        for i, boss in enumerate(r):
            px = x0 + i * (PANEL_W + gap) * S
            p = _panel(boss, rh)
            shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rounded_rectangle((px, y + 8 * S, px + p.width, y + 8 * S + p.height), 10 * S,
                                                     fill=(0, 0, 0, 115))
            img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14 * S)))
            img.alpha_composite(p, (px, y))
        y += (rh + gap) * S
    d = ImageDraw.Draw(img)
    _tracked(d, (W - x0, H - (foot - 6) * S), "NEXBOARD  ·  DATEN: A2TOOLS DPS METER", font("num", 11),
             _rgba(WHITE, 0.25), 1.0, anchor="ra")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def run_message(run: Run) -> str:
    bosses = run.bosses()
    fight_ms = sum(b.duration_ms for b in bosses)
    return (f"**{run.name}** – {run.kills}/{len(bosses)} {'Boss' if len(bosses) == 1 else 'Bosse'} besiegt, "
            f"Kampfzeit {fmt_time(fight_ms)} ({datetime.fromtimestamp(run.start_ms / 1000):%H:%M}–"
            f"{datetime.fromtimestamp(run.end_ms / 1000):%H:%M})")


async def post_discord(session: aiohttp.ClientSession, webhook: str, text: str, png: bytes, filename: str) -> None:
    """PNG + Text an einen Discord-Webhook; wartet einmal, falls Discord bremst (429)."""
    payload = {"content": text, "username": "NexBoard", "allowed_mentions": {"parse": []},
               "attachments": [{"id": 0, "filename": filename}]}
    for attempt in range(2):
        form = aiohttp.FormData()
        form.add_field("payload_json", json.dumps(payload), content_type="application/json")
        form.add_field("files[0]", png, filename=filename, content_type="image/png")
        async with session.post(webhook, data=form) as resp:
            if resp.status == 429 and attempt == 0:
                retry = float((await resp.json(content_type=None) or {}).get("retry_after", 2))
                await asyncio.sleep(min(retry, 30))
                continue
            if resp.status >= 300:
                body = (await resp.text())[:200]
                raise RuntimeError(f"Discord antwortet {resp.status}: {body}")
            return


# ---------------------------------------------------------------- Dienst
class DungeonRuns:
    def __init__(self, config_dir: Path) -> None:
        self.path = config_dir / "runs.yaml"
        self.state_path = config_dir / "runs-state.json"
        self.settings = self._load()
        self.tracker = RunTracker(self.settings.idle_minutes * 60_000)
        self.mtimes: dict[str, float] = {}  # Dateiname → zuletzt gelesene Änderungszeit
        self.fights: dict[str, Fight] = {}  # alle Dungeon-Kämpfe nach id (Mitspielerliste, Vorschau)
        self.pending: list[tuple[Run, float]] = []  # beendet, wartet auf Ruhe in den Dateien
        self.done: set[str] = set()  # Kämpfe aus erledigten Runs – späte Änderungen ignorieren
        self.last_ms, self.learned = self._read_state()
        self.last: Run | None = None  # zuletzt beendeter Run (Vorschau, Testpost)
        self.result = ""  # letzter Post: Erfolg oder Fehler, für die Web-UI
        self.listeners: list[Callable[[], Awaitable[None]]] = []
        # Jeder beendete Run mit besiegtem Boss, Namen schon aufgelöst (z. B. Discord-Bot, bot.py)
        self.run_listeners: list[Callable[[Run], Awaitable[None]]] = []
        self._ready = False
        # Wo die History liegt, hängt an der DPS-Quelle (server.py setzt das)
        self.history_dir: Callable[[], Path] = lambda: a2tools_dir() / "history"

    # ------------------------------------------------------------ Einstellungen
    def _load(self) -> RunSettings:
        try:
            return RunSettings.model_validate(yaml.safe_load(self.path.read_text()) or {})
        except FileNotFoundError:
            return RunSettings()
        except (yaml.YAMLError, ValidationError) as e:
            log.error("%s ungültig, nutze Standardwerte: %s", self.path, e)
            return RunSettings()

    def save(self, settings: RunSettings) -> None:
        header = "# AION-2-Dungeon-Runs nach Discord – wird von der Web-UI überschrieben.\n"
        text = yaml.safe_dump(settings.model_dump(), sort_keys=False, allow_unicode=True)
        _atomic_write(self.path, header + text, 0o600)  # die Webhook-URL ist ein Geheimnis
        self.settings = settings
        self.tracker.idle_ms = settings.idle_minutes * 60_000

    def info(self) -> dict:
        s = self.settings.model_dump()
        s["webhook"] = "•" * 8 if s["webhook"] else ""  # die URL verlässt den Daemon nicht
        last = None
        if self.last:
            last = {"name": self.last.name, "end": self.last.end_ms, "kills": self.last.kills}
        return {"settings": s, "history": self.history_dir().is_dir(),
                "last_run": last, "result": self.result, "open_run": bool(self.tracker.run),
                "characters": self.characters()}

    def names(self) -> dict[str, str]:
        """Maske|Klasse → echter Name: in der History unmaskiert oder live gesehen; von Hand Eingetragenes zuletzt."""
        full = {p.key: p.name for f in self.fights.values() for p in f.players if "*" not in p.name}
        return {**full, **self.learned, **self.settings.names}

    def characters(self) -> list[dict]:
        """Mitspieler aus den Dungeon-Kämpfen der letzten 30 Tage, häufigste zuerst (für die Namensliste)."""
        names = self.settings.names
        full = self.names()
        seen: dict[str, dict] = {}
        for f in self.fights.values():
            if f.start_ms < (time.time() - 30 * 86400) * 1000:
                continue
            for p in f.players:
                c = seen.setdefault(p.key, {"key": p.key, "mask": mask(p.name), "cls": p.cls, "count": 0, "you": False})
                c["count"] += 1
                c["you"] |= p.you
        out = [c for c in seen.values() if c["count"] >= 2 or c["key"] in names]
        out = sorted(out, key=lambda c: (not c["you"], -c["count"], c["mask"].lower()))[:12]
        for c in out:
            c["name"] = names.get(c["key"], "")
            c["seen"] = full.get(c["key"], "") if c["key"] not in names else ""  # bekannt → Platzhalter
        return out

    def observe(self, value: dict | None) -> None:
        """Live-Stand vom Meter (State `dps`): volle Namen merken, sofern das Meter sie zeigt."""
        if not value:
            return
        new = {}
        for r in value.get("rows") or []:
            name = r.get("name") or ""
            if "*" in name or name.startswith("#") or len(name) < 3:
                continue
            key = char_key(name, r.get("cls"))
            if self.learned.get(key) != name:
                new[key] = name
        if new:
            log.info("Namen aus dem Live-Stream gelernt: %s", ", ".join(new.values()))
            for key in new:
                self.learned.pop(key, None)  # neu Gesehene ans Ende, Älteste fliegen zuerst raus
            self.learned.update(new)
            while len(self.learned) > MAX_LEARNED:
                self.learned.pop(next(iter(self.learned)))
            self._write_state()

    # ------------------------------------------------------------ Zustand über Neustarts
    def _read_state(self) -> tuple[int | None, dict[str, str]]:
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return None, {}
        if not isinstance(data, dict):
            return None, {}
        try:
            last_ms = int(data["last_ms"])
        except (KeyError, TypeError, ValueError):
            last_ms = None
        learned = data.get("learned")
        # Schlüssel neu bilden, falls sich die Maskenregel geändert hat (Klasse steht hinter dem „|“)
        learned = {char_key(str(v)[:24], str(k).partition("|")[2] or None): str(v)[:24]
                   for k, v in learned.items()} if isinstance(learned, dict) else {}
        return last_ms, learned

    def _write_state(self) -> None:
        data = {"last_ms": self.last_ms, "learned": self.learned}
        _atomic_write(self.state_path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")

    def _scan(self, settle: bool = True) -> list[Fight]:
        """Neue und seit dem letzten Lesen geänderte Kämpfe."""
        hist = self.history_dir()
        now = time.time()
        fights = []
        try:
            entries = list(os.scandir(hist))
        except OSError:
            return []
        for e in entries:
            if not e.name.endswith(".json"):
                continue
            try:
                mtime = e.stat().st_mtime
            except OSError:
                continue
            if self.mtimes.get(e.name) == mtime or (settle and now - mtime < SETTLE_S):
                continue
            self.mtimes[e.name] = mtime
            f = load_fight(Path(e.path))
            if f:
                fights.append(f)
                self.fights[f.id] = f
        return sorted(fights, key=lambda f: f.start_ms)

    def _update_pending(self, f: Fight) -> bool:
        """Neuer Stand eines Kampfs aus einem schon beendeten, noch nicht geposteten Run."""
        for i, (run, _) in enumerate(self.pending):
            for j, old in enumerate(run.fights):
                if old.id == f.id:
                    run.fights[j] = f
                    self.pending[i] = (run, time.monotonic())
                    return True
        return False

    async def start(self) -> list[Run]:
        """Alte Kämpfe einlesen (lernt die Endbosse) und seit dem letzten Run Verpasstes nachholen."""
        fights = await asyncio.to_thread(self._scan, False)
        last_ms = self.last_ms
        if last_ms is None:  # erster Start: nichts Altes posten
            self.last_ms = last_ms = int(time.time() * 1000)
            self._write_state()
        closed: list[Run] = []
        for f in fights:
            if f.start_ms <= last_ms:
                self.tracker.learn(f)
                self.done.add(f.id)
            else:
                closed += self.tracker.add(f)
        closed += self.tracker.check_idle(int(time.time() * 1000))
        self._ready = True
        return closed

    async def watch(self) -> None:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for run in await self.start():
                await self._finish(session, run, late=True)
            while True:
                await asyncio.sleep(POLL_S)
                await self.poll(session)

    async def poll(self, session: aiohttp.ClientSession) -> None:
        closed: list[Run] = []
        for f in await asyncio.to_thread(self._scan):
            log.info("Bosskampf: %s – %s (%s, %s)", dungeon_name(f.dungeon), f.boss,
                     fmt_time(f.duration_ms), "besiegt" if f.killed else "läuft/nicht besiegt")
            if f.id in self.done or self._update_pending(f):
                continue
            closed += self.tracker.add(f)
        closed += self.tracker.check_idle(int(time.time() * 1000))
        now = time.monotonic()
        self.pending += [(run, now) for run in closed]
        for entry in list(self.pending):
            if now - entry[1] >= SETTLE_RUN_S:
                self.pending.remove(entry)
                await self._finish(session, entry[0])

    async def _finish(self, session: aiohttp.ClientSession, run: Run, late: bool = False) -> None:
        self.done |= {f.id for f in run.fights}
        self.last_ms = run.end_ms
        self._write_state()
        log.info("Run beendet: %s, %d Kämpfe, %d Bosse besiegt%s", run.name, len(run.fights), run.kills,
                 " (Endboss)" if run.complete else "")
        if not run.kills:
            return
        self.last = run
        if late and time.time() * 1000 - run.end_ms > LATE_POST_S * 1000:
            await self._notify()
            return
        if self.settings.enabled and self.settings.webhook:
            await self.post(session, run)
        run.rename(self.names())
        for fn in self.run_listeners:
            try:
                await fn(run)
            except Exception:  # ein Zuhörer (Netz) darf das Auswerten nicht anhalten
                log.exception("Run-Zuhörer")
        await self._notify()

    async def post(self, session: aiohttp.ClientSession, run: Run) -> bool:
        run.rename(self.names())
        try:
            png = await asyncio.to_thread(render_run, run)
            name = f"run-{datetime.fromtimestamp(run.start_ms / 1000):%Y%m%d-%H%M}.png"
            await post_discord(session, self.settings.webhook, run_message(run), png, name)
        except (aiohttp.ClientError, TimeoutError, RuntimeError, OSError) as e:
            self.result = f"Fehler beim Posten: {e}"
            log.warning("Discord: %s", e)
            return False
        self.result = f"gepostet: {run.name}, {datetime.fromtimestamp(run.end_ms / 1000):%d.%m. %H:%M}"
        log.info("Discord: %s", self.result)
        return True

    def latest_run(self) -> Run | None:
        """Zuletzt beendeter Run – oder, falls seit dem Start keiner endete, der letzte aus der History."""
        run = self.last or self._last_from_history()
        if run:
            run.rename(self.names())
        return run

    def _last_from_history(self) -> Run | None:
        fights = list(self.fights.values()) or [
            f for f in (load_fight(p) for p in self.history_dir().glob("*.json")) if f]
        tracker = RunTracker(self.settings.idle_minutes * 60_000)
        runs: list[Run] = []
        for f in sorted(fights, key=lambda f: f.start_ms):
            runs += tracker.add(f)
        runs += tracker.check_idle(int(time.time() * 1000))  # der laufende Run zählt noch nicht
        runs = [r for r in runs if r.kills]
        return runs[-1] if runs else None

    async def _notify(self) -> None:
        for fn in self.listeners:
            await fn()


def _cli() -> None:
    """python -m deckbar_daemon.runs [out.png] – letzten Run aus der History rendern (ohne zu posten)."""
    import sys
    run = DungeonRuns(Path("/nonexistent")).latest_run()
    if not run:
        sys.exit("keine Dungeon-Runs in der History")
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "run.png")
    out.write_bytes(render_run(run))
    print(run_message(run), "→", out)


if __name__ == "__main__":
    _cli()
