#!/usr/bin/env bash
# NexBoard aktualisieren: Repo, A2Tools-Kern, deckbar-capture, Dienste.
#
#   ./update.sh             git pull, Submodul auf den Stand des Repos, deckbar-capture nur bei
#                           Änderungen neu bauen (fragt dann nach dem Passwort für cap_net_raw),
#                           Daemon und Overlay neu starten
#   ./update.sh --a2tools   zusätzlich den A2Tools-Kern auf das neueste Release heben, z. B. nach
#                           einem Spiel-Patch. Gilt lokal, bis das Submodul im Repo nachgezogen ist.
#   --notify                Ergebnis als Desktop-Benachrichtigung (so startet es der Tray-Button)
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")"
NOTIFY=0
A2=0
for a in "$@"; do
  case $a in
    --notify) NOTIFY=1 ;;
    --a2tools) A2=1 ;;
    -h|--help) sed -n 2,10p "$0"; exit 0 ;;
    *) echo "Unbekannte Option: $a" >&2; exit 2 ;;
  esac
done

note() {
  echo "$*"
  if (( NOTIFY )) && command -v notify-send >/dev/null; then
    notify-send -a NexBoard -i system-software-update "NexBoard-Update" "$*" || true
  fi
}
fail() { note "Fehlgeschlagen: $*"; exit 1; }

# ------------------------------------------------------------------ Repo
if ! git diff --quiet --ignore-submodules || ! git diff --cached --quiet --ignore-submodules; then
  fail "lokale Änderungen im Repo. Bitte erst committen oder verwerfen."
fi
OLD=$(git rev-parse HEAD)
if git rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
  git pull --ff-only --quiet || fail "git pull ging nicht (lokale Commits? Dann von Hand zusammenführen)."
else
  # lokaler Entwicklungszweig ohne Gegenstück auf GitHub: nichts zu holen, Rest trotzdem
  echo "Zweig $(git rev-parse --abbrev-ref HEAD) hat keinen Upstream – überspringe git pull."
fi
NEW=$(git rev-parse HEAD)
changed() { [[ $OLD != "$NEW" ]] && ! git diff --quiet "$OLD" "$NEW" -- "$@"; }
SUMMARY=()
[[ $OLD != "$NEW" ]] && SUMMARY+=("NexBoard: $(git rev-list --count "$OLD..$NEW") neue Commits")

# ------------------------------------------------------------------ A2Tools-Kern
SUB=capture/a2tools
newer() { [[ -n $1 && $1 != "$2" && $(printf '%s\n%s\n' "$2" "$1" | sort -V | tail -1) == "$1" ]]; }
# Ein vorher lokal angehobener Stand (--a2tools) bleibt, solange er neuer ist als der des Repos
LOCAL_A2=$(git -C "$SUB" describe --tags --exact-match 2>/dev/null || true)
# Eigene Patches (capture/patches) zurücknehmen, sonst scheitert das Auschecken eines neuen
# Stands; capture/build.sh wendet sie beim nächsten Bauen wieder an
for p in capture/patches/*.patch; do
  [[ -e $SUB/.git ]] && git -C "$SUB" apply --reverse --quiet "../patches/${p##*/}" 2>/dev/null || true
done
git submodule update --init --quiet "$SUB" || fail "Submodul $SUB"
REPO_A2=$(git -C "$SUB" describe --tags --abbrev=0)
if newer "$LOCAL_A2" "$REPO_A2"; then
  git -C "$SUB" checkout --quiet "$LOCAL_A2"
fi
if (( A2 )); then
  git -C "$SUB" fetch --tags --quiet || fail "A2Tools-Releases nicht abrufbar"
  CURRENT=$(git -C "$SUB" describe --tags --abbrev=0)
  LATEST=$(git -C "$SUB" tag --list 'v*' --sort=-v:refname | head -1)
  if newer "$LATEST" "$CURRENT"; then
    git -C "$SUB" checkout --quiet "$LATEST" || fail "A2Tools $LATEST auschecken"
    SUMMARY+=("A2Tools $CURRENT → $LATEST (lokal, im Repo noch $REPO_A2)")
  fi
fi

# ------------------------------------------------------------------ deckbar-capture
BIN=~/.local/bin/deckbar-capture
STAMP=${XDG_DATA_HOME:-$HOME/.local/share}/deckbar/capture-build-id
BUILD_ID="$(git rev-parse HEAD:./capture)-$(git -C "$SUB" rev-parse HEAD)"
if [[ ! -x $BIN ]] || ! getcap "$BIN" 2>/dev/null | grep -q cap_net_raw || [[ "$(cat "$STAMP" 2>/dev/null)" != "$BUILD_ID" ]]; then
  note "Baue deckbar-capture neu, gleich kommt die Passwortabfrage für die Mitschnitt-Rechte …"
  capture/build.sh --install >/dev/null || fail "deckbar-capture bauen/installieren"
  mkdir -p "$(dirname "$STAMP")" && echo "$BUILD_ID" > "$STAMP"
  SUMMARY+=("deckbar-capture neu gebaut")
fi

# ------------------------------------------------------------------ Dienste
# Neu installieren, wenn sich die Abhängigkeiten geändert haben – oder wenn die Installation nicht
# zum Repo passt. Das betrifft alte Checkouts nach dem Umzug ins Monorepo: Ihr erstes update.sh
# zieht den neuen Stand und bricht dann ab, beim zweiten Lauf sieht changed() nichts mehr.
TOOL_PY="$(uv tool dir 2>/dev/null)/deckbar-daemon/bin/python"
if changed daemon/pyproject.toml daemon/uv.lock || ! "$TOOL_PY" -c 'import nexproto' 2>/dev/null; then
  uv tool install --force --editable ./daemon >/dev/null || fail "Daemon-Abhängigkeiten installieren"
fi
if changed daemon/systemd || ! cmp -s daemon/systemd/deckbar.service ~/.config/systemd/user/deckbar.service; then
  cp daemon/systemd/deckbar.service ~/.config/systemd/user/
fi
if changed overlay/deckbar-overlay.service overlay/deckbar-overlay.desktop; then
  overlay/install.sh >/dev/null || fail "Overlay einrichten"
fi
systemctl --user daemon-reload
systemctl --user restart deckbar.service
systemctl --user try-restart deckbar-overlay.service

if (( ${#SUMMARY[@]} )); then
  note "Aktualisiert: $(printf '%s; ' "${SUMMARY[@]}" | sed 's/; $//')"
else
  note "Schon aktuell, Dienste neu gestartet."
fi
