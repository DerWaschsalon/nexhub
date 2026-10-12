#!/usr/bin/env bash
# DeckBar-Overlay einrichten: Programm nach ~/.local/bin (Link ins Repo), User-Dienst für den
# Autostart, Starter „DeckBar DPS-Meter zeigen/verbergen“ für ein Tastenkürzel.
# Braucht PySide6 mit QtWebEngine: sudo pacman -S --needed pyside6 qt6-webengine
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
python3 -c "import PySide6.QtWebEngineWidgets" 2>/dev/null || {
  echo "PySide6/QtWebEngine fehlt: sudo pacman -S --needed pyside6 qt6-webengine" >&2; exit 1; }
mkdir -p ~/.local/bin ~/.config/systemd/user ~/.local/share/applications
ln -sf "$PWD/deckbar-overlay" ~/.local/bin/deckbar-overlay
cp deckbar-overlay.service ~/.config/systemd/user/
cp deckbar-overlay-toggle.desktop ~/.local/share/applications/
systemctl --user daemon-reload
systemctl --user enable --now deckbar-overlay.service
cat <<MSG
Overlay läuft im Tray. Tastenkürzel: Systemeinstellungen → Tastatur → Kurzbefehle → „Neu“ →
„Anwendung“ → „DeckBar DPS-Meter zeigen/verbergen“, dann eine Taste zuweisen.
Oder eine DeckBar-Kachel mit der Aktion Shell: deckbar-overlay --toggle
MSG
