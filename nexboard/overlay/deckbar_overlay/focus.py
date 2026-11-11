"""Fokus unter KWin: Das Skript focus.js meldet jeden Fensterwechsel per D-Bus."""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import ClassInfo, QObject, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface

from .const import FOCUS_DBUS, FOCUS_SCRIPT, HERE

if TYPE_CHECKING:
    from .app import Overlay



@ClassInfo({"D-Bus Interface": FOCUS_DBUS})
class FocusWatch(QObject):
    """Lädt das KWin-Skript focus.js und nimmt dessen Meldungen (aktives Fenster) über D-Bus an.
    Ohne KWin (anderer Compositor) bleibt ok = False und das Overlay einfach immer sichtbar."""

    def __init__(self, overlay: Overlay) -> None:
        super().__init__()
        self.overlay = overlay
        self.bus = QDBusConnection.sessionBus()
        self.ok = (self.bus.isConnected() and self.bus.registerService(FOCUS_DBUS)
                   and self.bus.registerObject("/Focus", self, QDBusConnection.ExportAllSlots)
                   and self._load_script())
        if not self.ok:
            print("Fokus-Erkennung nicht verfügbar (kein KWin?), Overlay bleibt sichtbar", file=sys.stderr, flush=True)

    def _scripting(self) -> QDBusInterface:
        return QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", self.bus)

    def _load_script(self) -> bool:
        s = self._scripting()
        if not s.isValid():
            return False
        s.call("unloadScript", FOCUS_SCRIPT)  # Rest eines abgestürzten Laufs
        args = s.call("loadScript", str(HERE / "focus.js"), FOCUS_SCRIPT).arguments()
        if not args or not isinstance(args[0], int) or args[0] < 0:
            return False
        QDBusInterface("org.kde.KWin", f"/Scripting/Script{args[0]}", "org.kde.kwin.Script", self.bus).call("run")
        return True

    def unload(self) -> None:
        if self.ok:
            self._scripting().call("unloadScript", FOCUS_SCRIPT)
            self.ok = False

    @Slot(str, str, str)
    def activeWindow(self, cls: str, caption: str, pid: str) -> None:
        self.overlay.on_focus(cls, caption, pid)
