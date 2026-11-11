"""Die Anwendung: hält Fläche, Fenster, Tray und Fokus zusammen und führt Befehle aus."""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QFile,
    QIODevice,
    QObject,
    QPoint,
    QRect,
    QSettings,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWidgets import QApplication

from .boot import LAYOUT
from .const import FOCUS_HIDE_MS, GAME_CLASS, GAME_TITLE, HERE, ICON, TOOL_SIZES
from .daemon_client import daemon_url
from .focus import FocusWatch
from .kwin import ensure_kwin_rule, ensure_plugin_kwin_rule, kde_primary
from .layer import LayerHost
from .legacy import InputShape
from .tray import Tray
from .windows import A2Window

EDGES = {
    "North": Qt.TopEdge, "South": Qt.BottomEdge, "East": Qt.RightEdge, "West": Qt.LeftEdge,
    "NorthEast": Qt.TopEdge | Qt.RightEdge, "NorthWest": Qt.TopEdge | Qt.LeftEdge,
    "SouthEast": Qt.BottomEdge | Qt.RightEdge, "SouthWest": Qt.BottomEdge | Qt.LeftEdge,
}


class Overlay(QObject):
    def __init__(self, app: QApplication, backend: str) -> None:
        super().__init__()
        self.app = app
        self.backend = backend
        self.url = daemon_url()
        self.store = QSettings("deckbar", "overlay")
        self.icon = QIcon(str(ICON)) if ICON.is_file() else QIcon.fromTheme("utilities-system-monitor")
        self.shape = InputShape()
        f = QFile(":/qtwebchannel/qwebchannel.js")
        f.open(QIODevice.ReadOnly)
        self.qwebchannel_js = bytes(f.readAll()).decode()
        data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "deckbar" / "overlay"
        self.profile = QWebEngineProfile("deckbar-overlay", self)  # gemeinsames localStorage aller Fenster
        self.profile.setPersistentStoragePath(str(data / "storage"))
        self.profile.setCachePath(str(data / "cache"))
        self.profile.settings().setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        self.windows: dict[str, A2Window] = {}
        self.pending: dict[str, dict] = {}
        self.seq = 0
        self.main: A2Window | None = None
        self.layer: LayerHost | None = None
        self.surface = None
        self.focus: FocusWatch | None = None
        self.manual_hidden = False  # per Befehl/Tray verborgen
        self.focus_away = False  # anderes Fenster als AION 2 aktiv
        self.autohide = bool(LAYOUT.get("hide_unfocused", True))
        self.focus_timer = QTimer(self)
        self.focus_timer.setSingleShot(True)
        self.focus_timer.timeout.connect(self._focus_left)
        self.net = QNetworkAccessManager(self)
        self.tray = Tray(self)
        if backend == "layer":
            self._layer()
        else:
            self.main = self._window("main", "main")
            ensure_kwin_rule()
        ensure_plugin_kwin_rule()
        self.restore_plugins()

    # ------------------------------------------------------------ layer-shell
    def _layer(self) -> None:
        from PySide6.QtQml import QQmlApplicationEngine

        self.layer = LayerHost(self, QUrl(self.url + "__deckbar__/overlay/"), str(LAYOUT.get("start_mode") or "click"))
        self.layer.set_screen(self._target_screen())
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty("host", self.layer)
        self.engine.load(QUrl.fromLocalFile(str(HERE / "Overlay.qml")))
        if not self.engine.rootObjects():
            raise RuntimeError("Overlay.qml ließ sich nicht laden (layer-shell-qt installiert?)")
        self.surface = self.engine.rootObjects()[0]
        self.layer.window = self.surface
        self._place_on_screen()
        QGuiApplication.instance().screenAdded.connect(lambda *_: QTimer.singleShot(500, self._place_on_screen))
        QGuiApplication.instance().screenRemoved.connect(lambda *_: QTimer.singleShot(500, self._place_on_screen))
        self.layer.apply_input()  # vor dem Zeigen: sonst blockiert die Fläche kurz das Spiel
        self.surface.show()
        self.tray.lock_action.setChecked(self.layer.mode == "lock")
        self.focus = FocusWatch(self)  # meldet sofort das aktive Fenster

    # ------------------------------------------------------------ Fokus
    def on_focus(self, cls: str, caption: str, pid: str) -> None:
        if pid == str(os.getpid()):
            return  # eigene Fenster (Fläche beim Bearbeiten, Details, Einstellungen) ändern nichts
        if cls == GAME_CLASS or caption == GAME_TITLE:
            self.focus_timer.stop()
            if self.focus_away:
                self.focus_away = False
                self._sync_surface()
        elif not self.focus_away:
            self.focus_timer.start(FOCUS_HIDE_MS)

    def _focus_left(self) -> None:
        self.focus_away = True
        self._sync_surface()

    def _sync_surface(self) -> None:
        """Fläche zeigen, solange sie nicht von Hand verborgen ist und das Spiel den Fokus hat
        (oder Autohide aus ist, oder gerade bearbeitet wird)."""
        if self.surface is None:
            return
        want = not self.manual_hidden and (self.layer.mode == "edit" or not (self.autohide and self.focus_away))
        if want == self.surface.isVisible():
            return
        if want:
            self.layer.apply_input()
            self.surface.show()
        else:
            self.surface.hide()

    @staticmethod
    def _target_screen():
        want = str(LAYOUT.get("screen") or "") or kde_primary()
        return next((s for s in QGuiApplication.screens() if s.name() == want), None) or QGuiApplication.primaryScreen()

    def _place_on_screen(self) -> None:
        screen = self._target_screen()
        if screen is None or self.surface is None:
            return
        self.layer.set_screen(screen)
        self.surface.setScreen(screen)
        self.surface.resize(screen.size())

    def mode_changed(self, mode: str) -> None:
        self.tray.show_mode(mode)
        if mode == "edit":
            self.manual_hidden = False
        self._sync_surface()

    # ------------------------------------------------------------ Fenster
    def _window(self, label: str, view: str) -> A2Window:
        w = A2Window(self, label, view)
        self.windows[label] = w
        w.destroyed.connect(lambda *_: self.windows.pop(label, None))
        geo = self.store.value(f"geometry/{label if not label.startswith('details-') else 'details'}")
        if label == "main":
            w.resize(400, 300)
            pos = self.store.value("geometry/main-pos")
            if isinstance(pos, QPoint):
                w.move(pos)
        elif isinstance(geo, QByteArray) and not label.startswith("details-"):
            w.restoreGeometry(geo)
        else:
            width, height, minw, minh = TOOL_SIZES.get(view, (1180, 760, 520, 360))
            w.resize(width, height)
            w.setMinimumSize(minw, minh)
            if label.startswith("details-"):  # Kampf-Fenster kaskadieren
                n = sum(1 for k in self.windows if k.startswith("details-"))
                w.move(w.pos() + QPoint(28 * n, 28 * n))
        return w

    def remember(self, w: A2Window) -> None:
        if w.label == "main":
            self.store.setValue("geometry/main-pos", w.pos())
        elif not w.label.startswith("details-"):
            self.store.setValue(f"geometry/{w.label}", w.saveGeometry())

    # ------------------------------------------------------------ Plugin-Fenster
    def plugin_command(self, c: dict) -> None:
        """Befehle des Daemons (plugins.py). Ein Plugin läuft auch versteckt weiter: Sein Fenster
        besteht, bis es ausgeschaltet wird."""
        plugin = str(c.get("id"))
        label = f"plugin-{plugin}"
        w = self.windows.get(label)
        match c.get("action"):
            case "open":
                if w is None:
                    w = A2Window(self, label, "main", plugin=c)
                    self.windows[label] = w
                    w.destroyed.connect(lambda *_: self.windows.pop(label, None))
                    w.setMinimumSize(int(c.get("minWidth") or 240), int(c.get("minHeight") or 60))
                    geo = self.store.value(f"geometry/{label}")
                    if isinstance(geo, QByteArray):
                        w.restoreGeometry(geo)
                    else:
                        w.resize(int(c.get("width") or 360), int(c.get("height") or 510))
                if c.get("shown"):
                    self.reveal(w)
            case "show" if w:
                self.reveal(w)
            case "hide" if w:
                self.remember(w)
                w.hide()
            case "close" if w:
                w.close()
            case "reload" if w:
                w.reload()
            case "fit" if w:
                height = c.get("height")
                if height is None:  # zurück auf die Größe von vorher
                    if w.fitted_from:
                        w.resize(w.fitted_from)
                        w.fitted_from = None
                else:
                    w.fitted_from = w.fitted_from or w.size()
                    w.setMinimumHeight(min(w.minimumHeight(), int(height)))
                    w.resize(w.width(), int(height))

    def restore_plugins(self) -> None:
        """Beim Start: alle eingeschalteten Plugins laufen, sichtbar wie zuletzt. Daemon noch nicht
        da: gleich noch einmal."""
        url = QUrl(self.url)
        url.setPath("/api/a2/invoke")
        req = QNetworkRequest(url)
        req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        reply = self.net.post(req, json.dumps({"cmd": "plugin_windows", "args": {}}).encode())

        def finished() -> None:
            body = bytes(reply.readAll())
            ok = reply.error() == QNetworkReply.NoError
            reply.deleteLater()
            if not ok:
                QTimer.singleShot(5000, self.restore_plugins)
                return
            for window in json.loads(body).get("result") or []:
                self.plugin_command({"action": "open", **window})

        reply.finished.connect(finished)

    def tool(self, label: str, view: str) -> A2Window:
        return self.windows.get(label) or self._window(label, view)

    def reveal(self, w: A2Window) -> None:
        w.show()
        w.raise_()
        w.activateWindow()

    def visible(self) -> bool:
        if self.surface is not None:
            return self.surface.isVisible()
        return bool(self.main and self.main.isVisible())

    def show_main(self) -> None:
        if self.surface is not None:
            # ausdrücklich zeigen gilt auch ohne Spielfokus, bis zum nächsten Fensterwechsel
            self.manual_hidden = False
            self.focus_timer.stop()
            self.focus_away = False
            self._sync_surface()
        elif self.main:
            self.reveal(self.main)

    def toggle(self) -> None:
        if self.visible():
            self.hide_all()
        else:
            self.show_main()

    def hide_all(self) -> None:
        if self.surface is not None:
            self.manual_hidden = True
            if self.layer.mode == "edit":
                self.layer.finishEdit()
            self.surface.hide()
        for w in list(self.windows.values()):
            if w.label == "main":
                if w.isVisible():
                    self.remember(w)
                    w.hide()
            else:
                w.close()  # merkt die Position (closeEvent) und gibt das Fenster frei

    def request_details(self, payload: dict) -> None:
        kind = payload.get("kind")
        if kind == "history":
            label, view = "history", "history"
        elif kind == "fight":
            label, view = "details-" + re.sub(r"[^A-Za-z0-9]", "_", str(payload.get("fightId"))), "details"
        else:
            label, view = "details", "details"
        self.seq += 1
        payload = {**payload, "seq": self.seq}
        w = self.windows.get(label)
        if w:
            self.reveal(w)
            w.emit("details-request", payload)
        else:
            self.pending[label] = payload
            self.reveal(self.tool(label, view))

    def on_screen(self, w: A2Window, index: int) -> None:
        screens = QGuiApplication.screens()
        if 0 <= index < len(screens):
            g = screens[index].availableGeometry()
            w.move(g.center() - QPoint(w.width() // 2, w.height() // 2))

    # ------------------------------------------------------------ Fenster-Commands der Seiten
    def call_json(self, w: A2Window | None, cmd: str, args_json: str) -> str:
        try:
            args = json.loads(args_json or "{}")
            return json.dumps({"result": self.command(w, cmd, args)})
        except Exception as e:  # noqa: BLE001 – die Seite bekommt den Fehler als Reject
            return json.dumps({"error": str(e)})

    def command(self, w: A2Window | None, cmd: str, a: dict):
        """w = Meter-Fenster der Oberfläche, None = Meter in der layer-shell-Fläche (Seite übernimmt
        dort Ziehen, Größe und Sperre selbst und reicht nur den Rest durch)."""
        handle = w.windowHandle() if w else None
        match cmd:
            case "start_drag":
                if handle and not w.locked:
                    handle.startSystemMove()
            case "start_tool_drag":
                if handle:
                    handle.startSystemMove()
            case "window_resize_drag":
                if handle and a.get("direction") in EDGES:
                    handle.startSystemResize(EDGES[a["direction"]])
            case "begin_tool_resize":
                if w:
                    w.setMinimumSize(int(a.get("minWidth") or 0), int(a.get("minHeight") or 0))
            case "begin_window_resize":
                return False
            case "finish_window_resize":
                return True
            case "resize_window":
                if w and w.label == "main":
                    # CSS-Pixel = logische Pixel in Qt; obere linke Ecke bleibt stehen
                    w.setFixedSize(max(1, math.ceil(float(a.get("width") or 1))), max(1, math.ceil(float(a.get("height") or 1))))
                    QTimer.singleShot(0, w.apply_lock)
            case "overlay_lock_supported":
                return self.shape.ok or self.layer is not None
            case "set_overlay_locked":
                if w:
                    w.locked = bool(a.get("locked"))
                    self.tray.lock_action.setChecked(w.locked)
                    w.apply_lock()
            case "set_overlay_card_open":
                if w:
                    w.card_open = bool(a.get("open"))
                    w.apply_lock()
            case "set_lock_button_rect":
                if w:
                    w.lock_rect = QRect(math.floor(float(a.get("x") or 0)), math.floor(float(a.get("y") or 0)),
                                        math.ceil(float(a.get("width") or 0)), math.ceil(float(a.get("height") or 0)))
                    w.apply_lock()
            case "main_window_ready" | "window_show":
                if w:
                    w.show()
            case "tool_window_ready" | "window_focus":
                if w:
                    self.reveal(w)
                return True
            case "details_window_ready":
                pass
            case "open_settings_window":
                s = self.windows.get("settings")
                if s:
                    s.emit("settings-shown")
                self.reveal(s or self.tool("settings", "settings"))
            case "close_settings_window":
                if s := self.windows.get("settings"):
                    s.close()
            case "request_details_view":
                self.request_details(a.get("payload") or {})
            case "take_pending_details_request":
                return self.pending.pop(w.label, None) if w else None
            case "open_details_window":
                d = self.tool("details", "details")
                self.on_screen(d, int(a.get("monitorIndex") or 0))
                self.reveal(d)
            case "close_details_window":
                if d := self.windows.get("details"):
                    d.close()
            case "close_tool_window":
                if w:
                    w.close()
            case "list_monitors":
                return self.monitors()
            case "open_url":
                QDesktopServices.openUrl(QUrl(str(a.get("url"))))
            case "quit_app":
                self.hide_all()  # Overlay bleibt im Tray, Beenden dort
            case "capture_screenshot":
                return self.screenshot(w, a)
            case _:
                raise RuntimeError(f"unbekannter Fenster-Command {cmd}")
        return None

    def monitors(self) -> list[dict]:
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        ordered = [primary] + [s for s in screens if s is not primary]
        pg = primary.geometry()
        out = []
        for i, s in enumerate(ordered):
            g, dpr = s.geometry(), s.devicePixelRatio()
            side = ""
            if s is not primary:
                side = ("left" if g.right() < pg.left() else "right" if g.left() > pg.right()
                        else "above" if g.bottom() < pg.top() else "below")
            out.append({"index": i, "name": s.name(), "x": round(g.x() * dpr), "y": round(g.y() * dpr),
                        "width": round(g.width() * dpr), "height": round(g.height() * dpr),
                        "scaleFactor": dpr, "isPrimary": s is primary, "side": side})
        return out

    def screenshot(self, w: A2Window | None, a: dict) -> dict:
        if w is None and self.surface is not None:
            img = self.surface.grabWindow()
            dpr = img.devicePixelRatio() or 1
            rect = QRect(round(float(a.get("x") or 0) * dpr), round(float(a.get("y") or 0) * dpr),
                         round(float(a.get("width") or 1) * dpr), round(float(a.get("height") or 1) * dpr))
            img = img.copy(rect)
            QApplication.clipboard().setImage(img)
            save = img.save
        else:
            rect = QRect(int(a.get("x") or 0), int(a.get("y") or 0), int(a.get("width") or w.width()), int(a.get("height") or w.height()))
            pix = w.grab(rect)
            QApplication.clipboard().setPixmap(pix)
            save = pix.save
        path = None
        if a.get("saveFile") and a.get("folder"):
            name = re.sub(r"[/\\\0]", "_", str(a.get("filename") or "a2tools.png"))
            path = str(Path(str(a["folder"])).expanduser() / name)
            save(path, "PNG")

    # ------------------------------------------------------------ Befehle
    def edit_from_tray(self, on: bool) -> None:
        if self.layer is not None and on != (self.layer.mode == "edit"):
            self.run("edit")

    def lock_from_tray(self, on: bool) -> None:
        if self.layer is not None:
            self.layer.set_mode("lock" if on else "click")
            return
        if self.main and self.main.locked != on:
            # Über die Seite, damit Schloss-Knopf und Einstellung mitziehen
            self.main.page().runJavaScript(
                f"window.javaBridge?.setSetting?.('dpsMeter.overlayLocked', '{str(on).lower()}');"
                f"document.querySelector('.lockBtn, #lockBtn')?.click();")
            self.main.locked = on
            self.main.apply_lock()

    def run(self, cmd: str) -> None:
        if cmd.startswith("plugin "):
            try:
                self.plugin_command(json.loads(cmd[7:]))
            except ValueError:
                pass
            return
        match cmd:
            case "toggle":
                self.toggle()
            case "show":
                self.show_main()
            case "hide":
                self.hide_all()
            case "edit":
                if self.layer is not None:
                    if self.layer.mode == "edit":
                        self.layer.finishEdit()
                    else:
                        self.show_main()
                        self.layer.set_mode("edit")
            case "lock" | "click":
                if self.layer is not None:
                    self.layer.set_mode(cmd)
                else:
                    self.lock_from_tray(cmd == "lock")
            case "reload":
                if self.surface is not None:
                    view = self.surface.findChild(QObject, "view")
                    if view is not None:
                        view.reload()
                elif self.main:
                    self.main.reload()
            case "details":
                self.request_details({"kind": "all"})
            case "history":
                self.request_details({"kind": "history"})
            case "settings":
                self.command(self.main, "open_settings_window", {})
            case "autohide-on" | "autohide-off":
                self.autohide = cmd == "autohide-on"
                self._sync_surface()
            case "quit":
                self.app.quit()
