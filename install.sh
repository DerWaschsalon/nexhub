#!/usr/bin/env bash
# DeckBar komplett einrichten (CachyOS / Arch, KDE Plasma): Pakete, Daemon als User-Dienst,
# A2Tools DPS Meter mit Autostart zum Spiel und ausgeblendetem Fenster, Firewall-Freigabe.
# Mehrfach ausführbar, bereits Erledigtes wird übersprungen bzw. aktualisiert.
#
#   ./install.sh                 alles
#   ./install.sh --no-a2tools    ohne DPS-Meter
#   ./install.sh --show-meter    A2Tools-Fenster auf dem Desktop sichtbar lassen
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
REPO=$PWD

WITH_A2TOOLS=1
HIDE_METER=1
for a in "$@"; do
  case $a in
    --no-a2tools) WITH_A2TOOLS=0 ;;
    --show-meter) HIDE_METER=0 ;;
    -h|--help) sed -n 2,8p "$0"; exit 0 ;;
    *) echo "Unbekannte Option: $a" >&2; exit 1 ;;
  esac
done

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
if [[ $EUID -eq 0 ]]; then
  echo "Bitte als normaler Benutzer starten, sudo wird bei Bedarf selbst gefragt." >&2
  exit 1
fi

# ------------------------------------------------------------------ Pakete
say "Pakete (pacman)"
sudo pacman -S --needed --noconfirm sdl2 playerctl ydotool wireplumber libpulse curl jq
if ! command -v uv >/dev/null; then
  sudo pacman -S --needed --noconfirm uv
fi
systemctl --user enable --now ydotool.service 2>/dev/null || echo "ydotool-Dienst nicht gefunden, Hotkeys gehen dann nicht."

# ------------------------------------------------------------------ Daemon
say "DeckBar-Daemon"
uv tool install --force --editable "$REPO/daemon"
mkdir -p ~/.config/systemd/user
cp "$REPO/daemon/systemd/deckbar.service" ~/.config/systemd/user/
systemctl --user import-environment WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable deckbar.service
systemctl --user restart deckbar.service

# Port 8765 fürs Gerät im Heimnetz freigeben (Web-UI bleibt trotzdem nur auf localhost)
if command -v ufw >/dev/null && systemctl is-active -q ufw; then
  NET=$(ip -4 route show scope link | awk '!/docker|br-|virbr|tailscale/ {print $1; exit}')
  if [[ -n $NET ]]; then
    say "Firewall: Port 8765 für $NET"
    sudo ufw allow from "$NET" to any port 8765 proto tcp comment DeckBar
  fi
fi

# ------------------------------------------------------------------ A2Tools DPS Meter
if (( WITH_A2TOOLS )); then
  say "A2Tools DPS Meter (neuestes Release von GitHub)"
  REL=$(curl -fsSL https://api.github.com/repos/taengu/A2Tools-DPS-Meter/releases/latest)
  VER=$(jq -r .tag_name <<<"$REL" | sed 's/^v//')
  ASSET=$(jq -c '.assets[] | select(.name | endswith("-x86_64.pkg.tar.zst"))' <<<"$REL")
  NAME=$(jq -r .name <<<"$ASSET")
  URL=$(jq -r .browser_download_url <<<"$ASSET")
  SHA=$(jq -r '.digest // ""' <<<"$ASSET" | sed 's/^sha256://')
  HAVE=$(pacman -Q a2tools-dps-meter 2>/dev/null | awk '{print $2}' | sed 's/-[0-9]*$//' || true)
  if [[ $HAVE == "$VER" ]]; then
    echo "Version $VER ist schon installiert."
  else
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    curl -fL -o "$TMP/$NAME" "$URL"
    if [[ -n $SHA ]]; then
      echo "$SHA  $TMP/$NAME" | sha256sum -c -
    else
      echo "Achtung: Release ohne Prüfsumme, Datei ungeprüft." >&2
    fi
    sudo pacman -U --noconfirm "$TMP/$NAME"
  fi

  say "Autostart mit AION 2"
  mkdir -p ~/.local/bin
  install -m 755 "$REPO/extras/aion2/aion2-dps-watcher.sh" ~/.local/bin/aion2-dps-watcher.sh
  cp "$REPO/extras/aion2/aion2-dps-watcher.service" ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable --now aion2-dps-watcher.service
  systemctl --user restart aion2-dps-watcher.service

  # Stream-Overlay einschalten: davon liest die DeckBar die DPS. Nur bei beendetem Meter,
  # sonst überschreibt er die Datei beim Schließen.
  SETTINGS=${XDG_DATA_HOME:-$HOME/.local/share}/com.a2tools.dps-meter/settings.json
  if pgrep -x a2tools-dps-met >/dev/null; then
    echo "Meter läuft: Stream-Overlay bitte selbst in seinen Einstellungen prüfen."
  else
    mkdir -p "$(dirname "$SETTINGS")"
    [[ -s $SETTINGS ]] || echo '{}' >"$SETTINGS"
    jq --arg hide "$HIDE_METER" '."dpsMeter.streamOverlay" = "true"
        | if $hide == "1" then ."dpsMeter.kwinRuleAdded" = "true" else . end' \
      "$SETTINGS" >"$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
    echo "Stream-Overlay eingeschaltet."
  fi

  # Fenster ausblenden: minimiert, nicht in Taskleiste/Fensterwechsler. Die Gruppe heißt wie die
  # Regel, die der Meter selbst anlegt, damit er sie nicht wieder mit „über allem“ überschreibt.
  if (( HIDE_METER )) && command -v kwriteconfig6 >/dev/null; then
    say "A2Tools-Fenster ausblenden (KWin-Regel)"
    G=a2tools-dps-meter-overlay
    k() { kwriteconfig6 --file kwinrulesrc --group "$G" --key "$1" "$2"; }
    k Description "A2Tools DPS Meter versteckt (Anzeige auf der DeckBar)"
    k wmclass a2tools-dps-meter; k wmclassmatch 1; k wmclasscomplete false
    k above false; k aboverule 2; k layerrule 0
    for r in minimize skiptaskbar skippager skipswitcher; do k $r true; k ${r}rule 2; done
    RULES=$(kreadconfig6 --file kwinrulesrc --group General --key rules)
    if [[ ",$RULES," != *",$G,"* ]]; then
      RULES=${RULES:+$RULES,}$G
      kwriteconfig6 --file kwinrulesrc --group General --key rules "$RULES"
      kwriteconfig6 --file kwinrulesrc --group General --key Order "$RULES"
      kwriteconfig6 --file kwinrulesrc --group General --key count "$(tr ',' '\n' <<<"$RULES" | grep -c .)"
    fi
    qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null || true
  fi
fi

say "Fertig"
cat <<EOF
Web-Konfiguration: http://localhost:8765
Token fürs Gerät:  $(grep '^token:' ~/.config/deckbar/config.yaml 2>/dev/null | sed 's/token: *//')

Firmware flashen (einmalig):
  cd $REPO/firmware
  cp include/secrets.example.h include/secrets.h   # WLAN + Token eintragen
  uv tool install platformio
  pio run -e deckbar -t upload       # Board V2
  pio run -e deckbar-v1 -t upload    # Board V1 (ohne „V2“-Aufkleber)
EOF
