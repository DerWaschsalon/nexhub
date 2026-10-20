#!/usr/bin/env bash
# NexBoard-Overlay einrichten: Programm nach ~/.local/bin (Link ins Repo), User-Dienst (startet der
# Daemon mit AION 2), Starter „NexBoard Overlay ein/aus“ und „… bearbeiten“ für Tastenkürzel.
# Braucht PySide6 mit QtWebEngine, für die layer-shell-Fläche (KDE Plasma, Wayland) layer-shell-qt:
#   sudo pacman -S --needed pyside6 qt6-webengine layer-shell-qt
# Danach startet das Modul „AION 2 · Overlay“ (Web-UI) den Dienst, sobald AION 2 läuft.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
python3 -c "import PySide6.QtWebEngineWidgets" 2>/dev/null || {
  echo "PySide6/QtWebEngine fehlt: sudo pacman -S --needed pyside6 qt6-webengine layer-shell-qt" >&2; exit 1; }
python3 - <<'PY' || echo "Hinweis: layer-shell-qt fehlt – das Overlay läuft dann als einfaches Fenster (--legacy)." >&2
from pathlib import Path
from PySide6.QtCore import QLibraryInfo
qml = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath))
raise SystemExit(0 if (qml / "org/kde/layershell").is_dir() else 1)
PY
mkdir -p ~/.local/bin ~/.config/systemd/user ~/.local/share/applications
# frühere Einrichtung: Autostart beim Login abschalten (vor dem Kopieren, die neue Datei kennt ihn nicht)
systemctl --user disable deckbar-overlay.service 2>/dev/null || true
ln -sf "$PWD/deckbar-overlay" ~/.local/bin/deckbar-overlay
cp deckbar-overlay.service ~/.config/systemd/user/
rm -f ~/.local/share/applications/deckbar-overlay-toggle.desktop
cp deckbar-overlay.desktop deckbar-overlay-edit.desktop ~/.local/share/applications/
systemctl --user daemon-reload
cat <<MSG
Overlay eingerichtet. Es startet mit AION 2, solange das Modul „AION 2 · Overlay“ an ist. Tastenkürzel: Systemeinstellungen → Tastatur → Kurzbefehle → „Neu“ →
„Anwendung“ → „NexBoard Overlay ein/aus“ bzw. „NexBoard Overlay bearbeiten“, dann eine Taste
zuweisen. Ohne Spiel von Hand starten: Web-UI → AION 2 · Overlay → „Neu starten“.
MSG
