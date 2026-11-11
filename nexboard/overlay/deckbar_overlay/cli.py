"""Programmstart: Befehl an die laufende Instanz geben oder das Overlay starten."""
from __future__ import annotations

import os
import signal
import sys

from PySide6.QtCore import QSocketNotifier, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from . import __doc__ as __package_doc__
from . import boot  # wirkt beim Import: Umgebung für Qt und Chromium, vor QApplication
from .app import Overlay
from .const import APP, COMMANDS
from .daemon_client import socket_path
from .ipc import send_to_running


def main() -> int:
    args = boot.ARGS
    if any(a in ("h", "help", "-h") for a in args):
        print(__package_doc__)
        return 0
    cmd = next((a for a in args if a in COMMANDS), None)
    if boot.BACKEND == "layer":
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
    QGuiApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication([sys.argv[0], "-name", APP])
    app.setApplicationName(APP)
    app.setDesktopFileName(APP)
    app.setQuitOnLastWindowClosed(False)
    if send_to_running(cmd or "show"):
        return 0  # läuft schon: Befehl weitergegeben
    if cmd == "quit":
        return 0
    path = socket_path()
    QLocalServer.removeServer(path)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(path):
        print(f"Socket {path}: {server.errorString()}", file=sys.stderr)
    try:
        overlay = Overlay(app, boot.BACKEND)
    except RuntimeError as e:
        print(f"{e} – starte das alte Meter-Fenster: deckbar-overlay --legacy", file=sys.stderr)
        return 1
    print(f"NexBoard-Overlay läuft ({'layer-shell' if boot.BACKEND == 'layer' else 'Legacy-Fenster'})", flush=True)

    def incoming() -> None:
        conn = server.nextPendingConnection()
        conn.readyRead.connect(lambda: [overlay.run(line.strip()) for line in bytes(conn.readAll()).decode().splitlines()])

    server.newConnection.connect(incoming)
    if cmd and cmd not in ("hide",):
        QTimer.singleShot(300, lambda: overlay.run(cmd))
    autosave = QTimer()
    autosave.timeout.connect(lambda: [overlay.remember(w) for w in overlay.windows.values() if w.isVisible()])
    autosave.start(5000)
    if overlay.focus is not None:
        app.aboutToQuit.connect(overlay.focus.unload)
    # SIGTERM (systemctl stop) sauber beenden, damit das KWin-Skript entladen wird. Python-Handler
    # laufen nur, wenn der Interpreter dran ist: das Wakeup-Fd weckt die Qt-Schleife (kein Polling).
    rfd, wfd = os.pipe()
    os.set_blocking(wfd, False)
    signal.set_wakeup_fd(wfd)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: app.quit())
    wake = QSocketNotifier(rfd, QSocketNotifier.Read)
    wake.activated.connect(lambda *_: os.read(rfd, 64))
    return app.exec()
