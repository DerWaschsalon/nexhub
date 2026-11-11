"""Backend wählen und die Plattform festlegen, bevor die Qt-Anwendung entsteht.

Das Modul wirkt beim Import (Umgebungsvariablen für Qt und Chromium); cli lädt es vor QApplication.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .daemon_client import change_layout, fetch_layout


def choose_backend(args: list[str]) -> str:
    """layer (layer-shell unter Wayland) oder legacy (XWayland-Fenster wie früher)."""
    if "legacy" in args:
        return "legacy"
    if "layer" in args:
        return "layer"
    if not os.environ.get("WAYLAND_DISPLAY"):
        return "legacy"
    if "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        return "legacy"  # Mutter kennt kein layer-shell
    from PySide6.QtCore import QLibraryInfo
    qml = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath))
    return "layer" if (qml / "org" / "kde" / "layershell").is_dir() else "legacy"


# Plattform vor dem ersten Qt-Fenster festlegen
ARGS = [a.removeprefix("--") for a in sys.argv[1:]]
EXIT = change_layout(ARGS)
if EXIT is not None:
    sys.exit(EXIT)
BACKEND = choose_backend(ARGS)
LAYOUT = fetch_layout() if BACKEND == "layer" else {}
# Alle Seiten kommen vom Daemon (eine Herkunft): ein gemeinsamer Renderer statt einem je Fenster
_FLAGS = ["--process-per-site"]
if BACKEND == "layer":
    os.environ["QT_QPA_PLATFORM"] = "wayland"
    if not LAYOUT.get("gpu", True):
        _FLAGS.append("--disable-gpu-compositing")
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    _FLAGS.append("--disable-gpu-compositing")  # transparente Fenster ohne Artefakte
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", " ".join(_FLAGS))
