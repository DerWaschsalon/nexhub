"""layer-shell-Fläche über dem Spielmonitor: Modus, Klickbereiche, Brücke zur Overlay-Seite."""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QEvent, QObject, QRect, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QRegion

from .const import MODES

if TYPE_CHECKING:
    from .app import Overlay



class LayerHost(QObject):
    """Kontext-Objekt „host“ in Overlay.qml: Modus, Monitor, Eingabe-Region, Fenster-Befehle des Meters."""

    modeChanged = Signal()
    screenChanged = Signal()
    readyChanged = Signal()
    pointerMoved = Signal(float, float)
    pointerReleased = Signal()

    def __init__(self, overlay: Overlay, page: QUrl, start_mode: str) -> None:
        super().__init__()
        self.overlay = overlay
        self._page = page
        self._mode = start_mode if start_mode in ("click", "lock") else "click"
        self.last = self._mode  # Modus vor dem Bearbeiten
        self.regions: dict[str, list[QRect]] = {"click": [], "lock": []}
        self.window = None
        self._screen = None
        self._ready = False

    @Property(bool, notify=readyChanged)
    def ready(self) -> bool:
        return self._ready

    @Slot()
    def pageReady(self) -> None:
        if not self._ready:
            self._ready = True
            self.readyChanged.emit()

    @Slot()
    def pageGone(self) -> None:
        """Neu laden beginnt: Seite verstecken und nichts mehr abfangen, bis sie sich meldet."""
        self.regions = {"click": [], "lock": []}
        if self._ready:
            self._ready = False
            self.readyChanged.emit()
        if self._mode != "edit":
            self.apply_input()

    @Property(QObject, notify=screenChanged)
    def screen(self):
        return self._screen

    def set_screen(self, screen) -> None:
        if screen is not self._screen:
            self._screen = screen
            self.screenChanged.emit()

    @Property(str, notify=modeChanged)
    def mode(self) -> str:
        return self._mode

    @Property(QUrl, constant=True)
    def pageUrl(self) -> QUrl:
        return self._page

    def set_mode(self, mode: str) -> None:
        if mode not in MODES or mode == self._mode:
            return
        if mode != "edit":
            self.last = mode
        self._mode = mode
        self.apply_input()
        self.modeChanged.emit()
        self.overlay.mode_changed(mode)

    def apply_input(self) -> None:
        """Eingabe-Region: alles (edit), nur Widgets mit data-click (click), nur Schloss (lock)."""
        w = self.window
        if w is None:
            return
        if self._mode == "edit":
            w.setFlag(Qt.WindowTransparentForInput, False)
            w.setMask(QRegion())  # leere Maske = keine Maske = ganze Fläche
            return
        rects = self.regions.get(self._mode) or []
        if not rects:
            # zuerst die Flagge, sonst ist kurz die ganze Fläche klickbar (13.10. gemessen)
            w.setFlag(Qt.WindowTransparentForInput, True)
            w.setMask(QRegion())
            return
        region = QRegion()
        for r in rects:
            region = region.united(QRegion(r))
        w.setFlag(Qt.WindowTransparentForInput, False)
        w.setMask(region)

    @Slot(str)
    def setRegions(self, text: str) -> None:
        try:
            data = json.loads(text)
            regions = {k: [QRect(*(int(round(v)) for v in r)) for r in data.get(k) or []] for k in ("click", "lock")}
        except (ValueError, TypeError, AttributeError):
            return
        if regions == self.regions:
            return  # unverändert: kein neues setMask/Commit
        self.regions = regions
        if self._mode != "edit":
            self.apply_input()

    @Slot(str)
    def requestMode(self, mode: str) -> None:
        self.set_mode(mode)

    @Slot()
    def finishEdit(self) -> None:
        self.set_mode(self.last)

    @Slot(str, str, result=str)
    def call(self, cmd: str, args_json: str) -> str:
        return self.overlay.call_json(None, cmd, args_json)

    @Slot()
    def watchPointer(self) -> None:
        """Ein Plugin-Widget wird gezogen. Den Mausdruck hat sein Sandbox-iframe bekommen, und es behält
        alle Bewegungen bis zum Loslassen; die Seite sieht sie nie. Also hier an der Fläche mitlesen."""
        if self.window is not None:
            self.window.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.MouseMove:
            at = event.position()
            self.pointerMoved.emit(at.x(), at.y())
        elif event.type() == QEvent.MouseButtonRelease:
            obj.removeEventFilter(self)
            self.pointerReleased.emit()
        return False

    @Slot(str)
    def log(self, text: str) -> None:
        if os.environ.get("DECKBAR_OVERLAY_DEBUG"):
            print(f"[seite] {text}", flush=True)
