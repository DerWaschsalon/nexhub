"""Layout des Overlays: welche Widgets es gibt, wo sie liegen und welche ein Profil zeigt.

Ein Widget meldet sein Modul als WidgetSpec an (Overlay.register); der Kern kennt keine Widget-Namen.
Die Datei layout.json trägt je Widget einen WidgetState. Dateien der Version 1 (deutsche Schlüssel,
Radar als ein großes Fenster, eigenes PvP-Widget) übersetzt migrate_v1 beim Laden.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from .config import _Strict

FX = Literal["", "glanz", "brennen", "gold", "frost", "holo", "leere"]
# Profilname, zugleich Aktions-ID im KDE-Starter
ProfileName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{1,24}$")]
WidgetId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,24}$")]

# Version 1 → 2: umbenannte Widgets. Das Radar war ein großes Fenster (Karte, Vertraute, Würfel); sein
# Nachfolger ist das kleine Cube-Radar, Platz und Größe des alten Fensters passen dafür nicht.
V1_RENAMED = {"warnung": "warnings", "radar": "cube"}
V1_KEPT_KEYS = ("enabled", "x", "y", "scale", "opacity")
V1_BOSS_OPTIONS = ("show_ttk", "hide_idle")


class WidgetState(_Strict):
    enabled: bool = True
    # Position in CSS-Pixeln auf dem Monitor; None = Standardplatz der Seite
    x: int | None = Field(None, ge=-4000, le=16000)
    y: int | None = Field(None, ge=-4000, le=16000)
    scale: float = Field(1.0, ge=0.5, le=3.0)
    opacity: float = Field(1.0, ge=0.2, le=1.0)
    # nur bei Widgets mit ziehbarer Größe (WidgetSpec.size)
    width: int | None = Field(None, ge=160, le=2000)
    height: int | None = Field(None, ge=120, le=1600)
    options: dict[str, bool] = Field(default_factory=dict, max_length=16)


@dataclass(frozen=True)
class WidgetOption:
    """Ein Schalter eines Widgets, den die Web-UI unter „Anpassen“ zeigt."""
    key: str
    title: str
    help: str = ""
    default: bool = True


@dataclass(frozen=True)
class WidgetSpec:
    """So meldet ein Modul ein Widget an. Die Overlay-Seite lädt dazu widgets/<id>.js."""
    id: str
    title: str  # Name in Web-UI, Bearbeiten-Leiste und Tastenkürzeln
    help: str
    enabled: bool = True  # Vorgabe, solange die Datei das Widget nicht kennt
    size: tuple[int, int] | None = None  # Startgröße, wenn sich das Widget am Griff ziehen lässt
    options: tuple[WidgetOption, ...] = ()
    profiles: tuple[str, ...] = ("PvE",)  # in welchen mitgelieferten Profilen es sichtbar ist
    module: str = ""  # setzt Overlay.register

    def fit(self, state: WidgetState | None) -> WidgetState:
        """Gespeicherten Stand an diese Anmeldung anpassen: Vorgaben ergänzen, Fremdes fallen lassen."""
        state = state or WidgetState(enabled=self.enabled)
        width, height = (state.width or self.size[0], state.height or self.size[1]) if self.size else (None, None)
        options = {o.key: state.options.get(o.key, o.default) for o in self.options}
        return state.model_copy(update={"width": width, "height": height, "options": options})

    def public(self, active: bool) -> dict[str, Any]:
        """Für Overlay-Seite und Web-UI. active: das Modul des Widgets ist eingeschaltet."""
        return {"id": self.id, "title": self.title, "help": self.help, "module": self.module, "active": active,
                "resizable": self.size is not None,
                "options": [{"key": o.key, "title": o.title, "help": o.help} for o in self.options]}


def migrate_v1(data: dict[str, Any]) -> dict[str, Any]:
    """layout.json der Version 1 in die Form der Version 2 bringen."""
    widgets = {}
    for old_id, old in (data.get("widgets") or {}).items():
        if not isinstance(old, dict):
            continue
        new = {k: old[k] for k in V1_KEPT_KEYS if k in old}
        if old_id == "radar":
            new = {"enabled": bool(old.get("enabled"))}
        if old_id == "boss":
            new["options"] = {k: bool(old[k]) for k in V1_BOSS_OPTIONS if k in old}
        widgets[V1_RENAMED.get(old_id, old_id)] = new
    profiles = {name: list(dict.fromkeys(V1_RENAMED.get(i, i) for i in ids))
                for name, ids in (data.get("profile") or {}).items()}
    kept = {k: v for k, v in data.items() if k not in ("version", "widgets", "profil", "profile")}
    return {**kept, "version": 2, "widgets": widgets, "profile": data.get("profil", ""), "profiles": profiles}


class OverlayLayout(_Strict):
    version: Literal[2] = 2
    screen: str = Field("", max_length=64)  # Ausgang (kscreen-doctor -o), leer = Hauptmonitor laut KDE
    start_mode: Literal["click", "lock"] = "click"
    fx: FX = ""  # Namenseffekt auf dem eigenen Namen in der Meter-Zeile
    gpu: bool = True  # Chromium-GPU-Compositing (unter layer-shell ohne Transparenzfehler)
    hide_unfocused: bool = True  # Fläche nur zeigen, solange AION 2 das aktive Fenster ist (KWin)
    widgets: dict[WidgetId, WidgetState] = Field(default_factory=dict, max_length=64)
    profile: str = Field("", max_length=24)  # aktives Profil, leer = keins
    # Profil = welche Widgets sichtbar sind; die Positionen gelten für alle Profile
    profiles: dict[ProfileName, list[WidgetId]] = Field(default_factory=dict, max_length=12)

    @model_validator(mode="before")
    @classmethod
    def _from_v1(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("version") == 1:
            return migrate_v1(data)
        return data

    @model_validator(mode="after")
    def _known_profile(self) -> OverlayLayout:
        if self.profile and self.profile not in self.profiles:
            raise ValueError(f"Profil {self.profile} gibt es nicht")
        return self

    def visible(self) -> list[str]:
        return [wid for wid, state in self.widgets.items() if state.enabled]

    def apply_profile(self) -> None:
        """Sichtbarkeit der Widgets aus dem aktiven Profil übernehmen."""
        shown = self.profiles[self.profile]
        for wid, state in self.widgets.items():
            state.enabled = wid in shown

    def fit(self, specs: dict[str, WidgetSpec]) -> None:
        """Auf die angemeldeten Widgets bringen: jedes hat einen Stand, Unbekanntes fällt weg."""
        self.widgets = {wid: spec.fit(self.widgets.get(wid)) for wid, spec in specs.items()}
        self.profiles = {name: [wid for wid in ids if wid in specs] for name, ids in self.profiles.items()}


def default_profiles(specs: dict[str, WidgetSpec]) -> dict[str, list[str]]:
    """Mitgelieferte Profile für eine neue layout.json, aus den Angaben der Widgets."""
    profiles: dict[str, list[str]] = {}
    for spec in specs.values():
        for name in spec.profiles:
            profiles.setdefault(name, []).append(spec.id)
    return profiles


def merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Tiefes Zusammenführen für Teil-Updates (Listen werden ersetzt)."""
    out = dict(base)
    for k, v in patch.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out
