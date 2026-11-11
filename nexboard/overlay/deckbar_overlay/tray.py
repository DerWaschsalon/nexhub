"""Tray-Symbol mit Menü und dem Update-Stand vom Daemon."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QObject,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
)
from PySide6.QtNetwork import (
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .daemon_client import daemon_port

if TYPE_CHECKING:
    from .app import Overlay

UPDATE_POLL_MS = 10 * 60 * 1000
FIRST_UPDATE_POLL_MS = 150 * 1000


class Tray(QObject):
    """Symbol im Systemabschnitt: Menü für die Befehle des Overlays, dazu der Update-Stand vom Daemon
    (der prüft täglich)."""

    def __init__(self, overlay: Overlay) -> None:
        super().__init__(overlay)
        self.overlay = overlay
        self.daemon = f"http://127.0.0.1:{daemon_port()}"
        self.updates: dict = {}
        menu = QMenu()
        menu.addAction("Overlay zeigen/verbergen", overlay.toggle)
        self.edit_action = QAction("Bearbeiten (Widgets verschieben)", menu, checkable=True)
        self.edit_action.toggled.connect(overlay.edit_from_tray)
        self.edit_action.setVisible(overlay.backend == "layer")
        menu.addAction(self.edit_action)
        self.lock_action = QAction("Durchklicken (gesperrt)", menu, checkable=True)
        self.lock_action.toggled.connect(overlay.lock_from_tray)
        menu.addAction(self.lock_action)
        menu.addSeparator()
        menu.addAction("Details", lambda: overlay.run("details"))
        menu.addAction("Verlauf", lambda: overlay.run("history"))
        menu.addAction("Meter-Einstellungen", lambda: overlay.run("settings"))
        menu.addAction("NexBoard-Einstellungen öffnen …", lambda: QDesktopServices.openUrl(
            QUrl(f"http://localhost:{daemon_port()}/#/aion2.overlay")))
        menu.addSeparator()
        self.update_action = menu.addAction("Keine Updates", self.run_update)
        self.update_action.setEnabled(False)
        menu.addAction("Nach Updates suchen", lambda: self.api("POST", "/api/updates/check", self.on_updates))
        menu.addSeparator()
        menu.addAction("Beenden", overlay.app.quit)
        menu.aboutToShow.connect(self.poll_updates)
        self.icon = QSystemTrayIcon(overlay.icon, self)
        self.icon.setToolTip("NexBoard Overlay")
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(lambda r: overlay.toggle() if r == QSystemTrayIcon.Trigger else None)
        self.icon.messageClicked.connect(self.run_update)
        self.icon.show()
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.poll_updates)
        self.update_timer.start(UPDATE_POLL_MS)
        QTimer.singleShot(FIRST_UPDATE_POLL_MS, self.poll_updates)

    def show_mode(self, mode: str) -> None:
        """Häkchen im Menü nachziehen, ohne den Modus dadurch erneut zu setzen."""
        for action, on in ((self.lock_action, mode == "lock"), (self.edit_action, mode == "edit")):
            action.blockSignals(True)
            action.setChecked(on)
            action.blockSignals(False)

    def poll_updates(self) -> None:
        self.api("GET", "/api/updates", self.on_updates)

    def api(self, method: str, path: str, done=None) -> None:
        req = QNetworkRequest(QUrl(self.daemon + path))
        req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        reply = self.overlay.net.post(req, b"{}") if method == "POST" else self.overlay.net.get(req)

        def finished() -> None:
            body = bytes(reply.readAll()).decode(errors="replace")
            ok = reply.error() == QNetworkReply.NoError
            reply.deleteLater()
            try:
                data = json.loads(body) if body else {}
            except ValueError:
                data = {}
            if done:
                done(data if ok else {"error": data.get("error") or reply.errorString()})

        reply.finished.connect(finished)

    def on_updates(self, u: dict) -> None:
        if "error" in u and "available" not in u:
            return  # Daemon nicht erreichbar oder Modul aus: alten Stand behalten
        self.updates = u
        parts = []
        d, a = u.get("deckbar") or {}, u.get("a2tools") or {}
        if d.get("behind"):
            parts.append(f"NexBoard +{d['behind']}")
        if a.get("newer"):
            parts.append(f"A2Tools {a.get('latest')}")
        if u.get("running"):
            self.update_action.setText("Update läuft …")
            self.update_action.setEnabled(False)
        elif u.get("available"):
            self.update_action.setText(f"Jetzt aktualisieren ({', '.join(parts)})")
            self.update_action.setEnabled(True)
        else:
            self.update_action.setText("Keine Updates" + (" (Prüfung fehlgeschlagen)" if u.get("error") else ""))
            self.update_action.setEnabled(False)
        self.icon.setToolTip("NexBoard Overlay" + (f"\nUpdate verfügbar: {', '.join(parts)}" if u.get("available") else ""))
        # Einmal je neuem Stand melden
        key = f"{d.get('latest') if d.get('behind') else ''}|{a.get('latest') if a.get('newer') else ''}"
        if u.get("available") and self.overlay.store.value("notifiedUpdate") != key:
            self.overlay.store.setValue("notifiedUpdate", key)
            self.icon.showMessage("NexBoard: Update verfügbar",
                                  f"{', '.join(parts)}. Zum Aktualisieren hier klicken oder im Tray-Menü.",
                                  QSystemTrayIcon.Information, 15000)

    def run_update(self) -> None:
        if not self.updates.get("available") or self.updates.get("running"):
            return
        self.update_action.setText("Update läuft …")
        self.update_action.setEnabled(False)
        self.api("POST", "/api/updates/run", lambda r: r.get("error") and self.icon.showMessage(
            "NexBoard-Update", f"Ging nicht: {r['error']}", QSystemTrayIcon.Warning, 10000))
