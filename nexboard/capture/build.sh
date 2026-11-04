#!/usr/bin/env bash
# Baut deckbar-capture.   ./build.sh [--install] [cargo-Optionen]
#
# --install kopiert das Programm nach ~/.local/bin und gibt ihm cap_net_raw (fragt nach sudo).
# Der Daemon nimmt es dort vor dem Build im Repo. Ein Neubau verliert die Rechte, deshalb nach
# jedem Update erneut mit --install bauen.
#
# Der A2Tools-Kern bindet per tauri::generate_context! seine Oberfläche ein, die wir nicht
# brauchen: ein leeres dist/ genügt (in a2tools gitignored).
set -euo pipefail
cd "$(dirname "$0")"
INSTALL=0
if [[ ${1:-} == --install ]]; then
  INSTALL=1
  shift
fi
# Nur anlegen, wenn es fehlt: ein per update.sh --a2tools lokal angehobener Stand bleibt so
[[ -e a2tools/.git ]] || git -C .. submodule update --init capture/a2tools
# Eigene Änderungen am Kern (patches/*.patch, z. B. der Treffer-Haken für den Hub). Schon
# angewandt: nichts zu tun. Passt ein Patch nach einem A2Tools-Update nicht mehr: Abbruch, Patch
# an den neuen Stand anpassen.
for p in patches/*.patch; do
  git -C a2tools apply --reverse --check "../$p" 2>/dev/null && continue
  git -C a2tools apply "../$p" || { echo "Patch $p passt nicht auf diesen A2Tools-Stand." >&2; exit 1; }
done
mkdir -p a2tools/dist
[[ -e a2tools/dist/index.html ]] || echo '<!doctype html>' > a2tools/dist/index.html
cargo build --release "$@"
if (( INSTALL )); then
  DEST=~/.local/bin/deckbar-capture
  install -Dm755 target/release/deckbar-capture "$DEST"
  # Ohne Terminal (Tray-Button, update.sh --notify) grafisch nach dem Passwort fragen
  if [[ -t 0 ]]; then SUDO=sudo; else SUDO=pkexec; fi
  $SUDO /usr/bin/setcap cap_net_raw=ep "$(readlink -f "$DEST")"
  getcap "$DEST"
  echo "Installiert: $DEST (Daemon neu starten: systemctl --user restart deckbar)"
fi
