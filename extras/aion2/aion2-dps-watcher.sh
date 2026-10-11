#!/bin/bash
# Hält den A2Tools DPS Meter offen, solange AION 2 läuft, und beendet ihn mit dem Spiel.
# Wird er während des Spiels geschlossen, startet er nach ~2 s neu.
# Meter: A2Tools DPS Meter (/usr/bin/a2tools-dps-meter). Sein Fenster blendet die KWin-Regel aus
# install.sh aus, die Werte zeigt die DeckBar.
GAME_PATTERN='Win64[\\/]AION2\.exe'
METER=/usr/bin/a2tools-dps-meter; PROC=a2tools-dps-met  # comm ist auf 15 Zeichen gekürzt
game_was_running=false

while true; do
  if pgrep -f "$GAME_PATTERN" >/dev/null; then
    if ! $game_was_running; then
      game_was_running=true
      sleep 10  # Spiel erst hochkommen lassen
    fi
    if ! pgrep -x "$PROC" >/dev/null; then
      GDK_BACKEND=x11 "$METER" >/dev/null 2>&1 &
    fi
  elif $game_was_running; then
    game_was_running=false
    pkill -x "$PROC"
  fi
  sleep 2
done
