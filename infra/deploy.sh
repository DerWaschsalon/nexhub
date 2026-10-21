#!/usr/bin/env bash
# Dateien aus infra/server/ auf den VPS waschsalon bringen (Pfade relativ zu /).
#
#   infra/deploy.sh <wer>             nur anzeigen, was sich ändern würde (Standard)
#   infra/deploy.sh <wer> --anwenden  übertragen; vorher muss <wer> die Sperre halten
#                                     (ssh waschsalon waschsalon-lock holen <wer> <wofür>)
#
# Riskante Dateien (etc/ssh/, etc/nftables.conf) kommen mit einem Rücknahme-Timer: ohne
#   ssh waschsalon systemctl stop waschsalon-rollback.timer
# innerhalb von 5 Minuten stellt der Server den vorherigen Stand wieder her. Vorher in einer
# NEUEN Verbindung prüfen, dass der Login noch geht. Der Anbieter hat keine Konsole.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/server"
HOST=${WASCHSALON_HOST:-waschsalon}
WER=${1:?Aufruf: infra/deploy.sh <wer> [--anwenden]}
ANWENDEN=0
[[ ${2:-} == --anwenden ]] && ANWENDEN=1
remote() { ssh -o BatchMode=yes "$HOST" "$@"; }
riskant() { [[ $1 == etc/ssh/* || $1 == etc/nftables.conf ]]; }

mapfile -t DATEIEN < <(find . -type f -printf '%P\n' | sort)
GEAENDERT=()
for f in "${DATEIEN[@]}"; do
  if ! remote "cat /$f 2>/dev/null" | diff -u --label "server:/$f" --label "repo:/$f" - "$f"; then
    GEAENDERT+=("$f")
  fi
done
if (( ${#GEAENDERT[@]} == 0 )); then
  echo "Server entspricht infra/server/, nichts zu tun."
  exit 0
fi
echo "Abweichend: ${GEAENDERT[*]}"
(( ANWENDEN )) || { echo "(nur angezeigt – mit --anwenden übertragen)"; exit 0; }

INHABER=$(remote 'cut -d"|" -f1 /srv/waschsalon/LOCK 2>/dev/null' || true)
if [[ $INHABER != "$WER" ]]; then
  echo "Abbruch: Sperre hält '${INHABER:-niemand}', nicht $WER. Erst: ssh $HOST waschsalon-lock holen $WER <wofür>" >&2
  exit 1
fi

RISKANT=()
for f in "${GEAENDERT[@]}"; do riskant "$f" && RISKANT+=("$f"); done
SSH_NEU=0 NFT_NEU=0
for f in "${RISKANT[@]}"; do
  [[ $f == etc/ssh/* ]] && SSH_NEU=1
  [[ $f == etc/nftables.conf ]] && NFT_NEU=1
done

if (( ${#RISKANT[@]} )); then
  # Bisherigen Stand der riskanten Dateien sichern (neue Dateien merken, um sie zu löschen),
  # der Timer spielt ihn in 5 Minuten zurück und lädt SSH und Firewall neu
  remote "set -e; R=/root/deploy-rollback; rm -rf \$R; mkdir -p \$R/dateien; : > \$R/neu
    for f in ${RISKANT[*]}; do
      if [ -e /\$f ]; then cp -a --parents /\$f \$R/dateien/; else echo \$f >> \$R/neu; fi
    done
    cat > \$R/zurueck.sh <<'ZURUECK'
#!/bin/sh
R=/root/deploy-rollback
cp -a \$R/dateien/. /
while read -r f; do rm -f \"/\$f\"; done < \$R/neu
systemctl restart ssh
if [ -f /etc/nftables.conf ]; then nft -f /etc/nftables.conf; else nft delete table inet waschsalon 2>/dev/null; fi
ZURUECK
    systemctl stop waschsalon-rollback.timer 2>/dev/null || true
    systemctl reset-failed waschsalon-rollback.service 2>/dev/null || true
    systemd-run --quiet --unit=waschsalon-rollback --on-active=5min /bin/sh \$R/zurueck.sh"
fi

# --no-overwrite-dir: Rechte und Besitzer vorhandener Verzeichnisse (/, /etc, …) bleiben unangetastet
tar -cf - --owner=root --group=root "${GEAENDERT[@]}" | remote 'tar -C / --no-overwrite-dir -xf -'

if printf '%s\n' "${GEAENDERT[@]}" | grep -q '^etc/systemd/'; then
  remote 'systemctl daemon-reload'
fi
if (( SSH_NEU )); then
  remote 'sshd -t && systemctl restart ssh' ||
    echo "sshd -t schlug fehl – der Timer stellt in 5 Minuten den alten Stand her" >&2
fi
if (( NFT_NEU )); then
  remote 'nft -c -f /etc/nftables.conf && nft -f /etc/nftables.conf && systemctl enable --quiet nftables' ||
    echo "Firewall-Regeln fehlerhaft – der Timer stellt in 5 Minuten den alten Stand her" >&2
fi
remote "waschsalon-lock log $WER 'deploy: ${GEAENDERT[*]}'" >/dev/null 2>&1 || true
echo "Übertragen: ${GEAENDERT[*]}"
if printf '%s\n' "${GEAENDERT[@]}" | grep -q '^srv/nexhub/'; then
  echo "NexHub-Stack geändert – übernehmen mit: ssh $HOST 'cd /srv/nexhub && docker compose up -d'"
fi
if (( ${#RISKANT[@]} )); then
  echo "Riskante Änderung (${RISKANT[*]}): in einer NEUEN Verbindung testen, dann innerhalb von"
  echo "5 Minuten bestätigen mit: ssh $HOST systemctl stop waschsalon-rollback.timer"
fi
