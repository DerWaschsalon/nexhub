#!/usr/bin/env bash
# Firmware bauen und flashen. Der Daemon hält das Board per USB-Brücke offen, deshalb wird er
# dafür kurz angehalten.  ./flash.sh [deckbar|deckbar-v1]   (Standard: deckbar = Board V2)
# Port: PORT=/dev/serial/by-id/… ./flash.sh. Hängen mehrere ESP32 am PC (z. B. WLED), wird gefragt.
set -euo pipefail
cd "$(dirname "$0")"
ENV=${1:-deckbar}
if [[ -z ${PORT:-} ]]; then
  mapfile -t ports < <(ls /dev/serial/by-id/*Espressif* 2>/dev/null)
  case ${#ports[@]} in
    0) echo "Kein ESP32 gefunden." >&2; exit 1 ;;
    1) PORT=${ports[0]} ;;
    *) echo "Mehrere ESP32 angeschlossen, welcher ist die DeckBar?"
       select PORT in "${ports[@]}"; do [[ -n $PORT ]] && break; done ;;
  esac
fi
echo "Flashe $ENV auf $PORT"
running=0
if systemctl --user -q is-active deckbar.service; then
  running=1
  systemctl --user stop deckbar.service
fi
trap 'if (( running )); then systemctl --user start deckbar.service; fi' EXIT
pio run -e "$ENV" -t upload --upload-port "$PORT"
