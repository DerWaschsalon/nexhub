"""Modul PoE 1 · Spiel: erkennt das laufende Spiel und liest sein Client.txt für die anderen PoE-Module.

Für PoE 2 genügt später eine Unterklasse mit game = POE2 und eigener ModuleInfo (ID "poe2.client").
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from nexcore import Context, ModuleInfo
from nexcore.settings import SettingsStore
from pydantic import Field

from ..config import _Strict
from ..core.live import LiveHub
from ..poe.games import POE1, PoeGame
from ..poe.session import PoeSession
from .base import WebModule


class ClientSettings(_Strict):
    client_txt: str = Field("", max_length=400, title="Client.txt",
                            description="Leer = selbst suchen (Ordner des laufenden Spiels, sonst Steam-Bibliotheken)")


class PoeClientModule(WebModule):
    game: ClassVar[PoeGame] = POE1
    info = ModuleInfo(
        "poe1.client", "PoE 1 · Spiel", "ingame", "gamepad-variant",
        "Erkennt Path of Exile und liest Zonenwechsel und Aufstiege aus Client.txt. Grundlage der PoE-Module.",
        tags=("PoE 1",),
    )

    def __init__(self, ctx: Context, live: LiveHub, config_dir: Path) -> None:
        super().__init__(ctx, live)
        self._store = SettingsStore(config_dir / f"{self.info.id}.yaml", ClientSettings,
                                    header=f"{self.info.name} – wird von der Web-UI überschrieben")
        self.session = PoeSession(ctx.bus, self.game, lambda: self._store.value.client_txt)

    @property
    def store(self) -> SettingsStore[Any]:
        return self._store

    async def start(self) -> None:
        self.spawn(self.session.run)

    def status(self) -> dict[str, Any]:
        path = self.session.path()
        zone = self.session.zone
        return {"running": self.session.running, "client_txt": str(path) if path else None,
                "found": bool(path and path.is_file()), "zone": zone.area_id if zone else None,
                "text": "läuft" if self.session.running else "nicht gestartet"}
