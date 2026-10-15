#!/usr/bin/env bash
# NexBoard-Overlay einrichten: Programm nach ~/.local/bin (Link ins Repo), User-Dienst für den
# Autostart, Starter „NexBoard Overlay ein/aus“ und „… bearbeiten“ für Tastenkürzel.
# Braucht PySide6 mit QtWebEngine, für die layer-shell-Fläche (KDE Plasma, Wayland) layer-shell-qt:
#   sudo pacman -S --needed pyside6 qt6-webengine layer-shell-qt
# Den Dienst schaltet danach das Modul „AION 2 · Overlay“ in der Web-UI ein und aus.
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
ln -sf "$PWD/deckbar-overlay" ~/.local/bin/deckbar-overlay
cp deckbar-overlay.service ~/.config/systemd/user/
rm -f ~/.local/share/applications/deckbar-overlay-toggle.desktop
cp deckbar-overlay.desktop deckbar-overlay-edit.desktop ~/.local/share/applications/
systemctl --user daemon-reload
if [[ ${1:-} != --no-start ]]; then
  systemctl --user enable --now deckbar-overlay.service
fi
cat <<MSG
Overlay eingerichtet. Tastenkürzel: Systemeinstellungen → Tastatur → Kurzbefehle → „Neu“ →
„Anwendung“ → „NexBoard Overlay ein/aus“ bzw. „NexBoard Overlay bearbeiten“, dann eine Taste
zuweisen. Ein- und ausschalten: Web-UI → Module → „AION 2 · Overlay“.
MSG
