"""Fenster der Meter-Oberfläche (Legacy-Meter, Details, Verlauf, Einstellungen, Plugins)."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRect, QSize, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView

from .const import MAIN_TITLE, PLUGIN_TITLE

if TYPE_CHECKING:
    from .app import Overlay



class Host(QObject):
    """Objekt "host" im QWebChannel jedes Meter-Fensters: call(cmd, argsJson) → JSON, Signal event."""

    event = Signal(str, str)

    def __init__(self, win: A2Window) -> None:
        super().__init__(win)
        self.win = win

    @Slot(str, str, result=str)
    def call(self, cmd: str, args_json: str) -> str:
        return self.win.overlay.call_json(self.win, cmd, args_json)


class A2Window(QWebEngineView):
    """Fenster mit der Meter-Oberfläche: Details, Verlauf, Einstellungen – und im Legacy-Betrieb das Meter."""

    def __init__(self, overlay: Overlay, label: str, view: str, plugin: dict | None = None) -> None:
        super().__init__()
        self.overlay, self.label, self.view = overlay, label, view
        self.plugin = plugin  # Hauptfenster eines Plugins (Kennung, Name, Größe), siehe Overlay.plugin_command
        self.fitted_from: QSize | None = None
        self.locked = False
        self.card_open = False  # Karte im Meter offen: auch gesperrt ganz klickbar
        self.lock_rect = QRect()
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Werkzeugfenster (Details, Verlauf, Einstellungen) beim Schließen freigeben: versteckt liefen
        # ihre Seiten weiter (Event-Stream, Abfragen alle 1–10 s, Details-Neuberechnung alle 2 s)
        self.setAttribute(Qt.WA_DeleteOnClose, label != "main")
        flags = Qt.FramelessWindowHint
        if label == "main":
            flags |= Qt.Tool | Qt.WindowStaysOnTopHint  # nicht in der Taskleiste
            self.setWindowTitle(MAIN_TITLE)
        elif plugin:
            flags |= Qt.WindowStaysOnTopHint
            self.setWindowTitle(f"{plugin['name']}{PLUGIN_TITLE}")  # KWin-Regel: über dem Spiel
        else:
            self.setWindowTitle(f"NexBoard – {view.capitalize()}")
        self.setWindowFlags(flags)
        self.setWindowIcon(overlay.icon)

        page = QWebEnginePage(overlay.profile, self)
        page.setBackgroundColor(QColor(0, 0, 0, 0))
        script = QWebEngineScript()
        script.setName("deckbar-window")
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(overlay.qwebchannel_js + f"\nwindow.__DECKBAR_WINDOW__ = {json.dumps({'label': label, 'view': view})};")
        page.scripts().insert(script)
        self.host = Host(self)
        channel = QWebChannel(page)
        channel.registerObject("host", self.host)
        page.setWebChannel(channel)
        self.setPage(page)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.url = QUrl(overlay.url)
        if plugin:
            self.url.setPath("/plugin-host.html")
            self.url.setQuery(f"plugin={plugin['id']}")
        elif view != "main":
            self.url.setQuery(f"view={view}")
        # Daemon noch nicht da (Autostart vor dem Daemon, Neustart): später erneut laden
        self.loadFinished.connect(lambda ok: ok or QTimer.singleShot(3000, lambda: self.load(self.url)))
        self.load(self.url)

    def emit(self, name: str, payload=None) -> None:
        self.host.event.emit(name, json.dumps(payload) if payload is not None else "")

    def apply_lock(self) -> None:
        if self.label != "main" or not self.isVisible():
            return
        rects = None
        if self.locked and not self.card_open:
            rects = [self.lock_rect] if self.lock_rect.isValid() else []
        self.overlay.shape.set(int(self.winId()), rects)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        QTimer.singleShot(0, self.apply_lock)

    def closeEvent(self, e) -> None:
        self.overlay.remember(self)
        super().closeEvent(e)
