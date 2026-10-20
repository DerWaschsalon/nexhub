#!/usr/bin/env bash
# Dateien aus infra/server/ auf den VPS waschsalon bringen (Pfade relativ zu /).
#
#   infra/deploy.sh <wer>             nur anzeigen, was sich ändern würde (Standard)
#   infra/deploy.sh <wer> --anwenden  übertragen; vorher muss <wer> die Sperre halten
#                                     (ssh waschsalon waschsalon-lock holen <wer> <wofür>)
#
# Änderungen unter etc/ssh/ werden mit einem Rücknahme-Timer eingespielt: ohne
#   ssh waschsalon systemctl stop waschsalon-rollback.timer
# innerhalb von 5 Minuten stellt der Server den vorherigen Stand wieder her. Vorher in einer
# NEUEN Verbindung prüfen, dass der Login noch geht. Der Anbieter hat keine Konsole.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/server"
HOST=${WASCHSALON_HOST:-waschsalon}
WER=${1:?Aufruf: infra/deploy.sh <wer> [--anwenden]}
ANWENDEN=0
[[ ${2:-} == --anwenden ]] && ANWENDEN=1

mapfile -t DATEIEN < <(find . -type f -printf '%P\n' | sort)
GEAENDERT=()
for f in "${DATEIEN[@]}"; do
  if ! ssh -o BatchMode=yes "$HOST" "cat /$f 2>/dev/null" | diff -u --label "server:/$f" --label "repo:/$f" - "$f"; then
    GEAENDERT+=("$f")
  fi
done
if (( ${#GEAENDERT[@]} == 0 )); then
  echo "Server entspricht infra/server/, nichts zu tun."
  exit 0
fi
echo "Abweichend: ${GEAENDERT[*]}"
(( ANWENDEN )) || { echo "(nur angezeigt – mit --anwenden übertragen)"; exit 0; }

INHABER=$(ssh -o BatchMode=yes "$HOST" 'cut -d"|" -f1 /srv/waschsalon/LOCK 2>/dev/null' || true)
if [[ $INHABER != "$WER" ]]; then
  echo "Abbruch: Sperre hält '${INHABER:-niemand}', nicht $WER. Erst: ssh $HOST waschsalon-lock holen $WER <wofür>" >&2
  exit 1
fi

SSH_AENDERUNG=0
for f in "${GEAENDERT[@]}"; do [[ $f == etc/ssh/* ]] && SSH_AENDERUNG=1; done
if (( SSH_AENDERUNG )); then
  # Sicherung der bisherigen SSH-Konfiguration, Timer spielt sie in 5 Minuten zurück
  ssh -o BatchMode=yes "$HOST" 'set -e; rm -rf /root/ssh-rollback; cp -a /etc/ssh /root/ssh-rollback
    systemctl stop waschsalon-rollback.timer 2>/dev/null || true
    systemd-run --quiet --unit=waschsalon-rollback --on-active=5min /bin/sh -c \
      "rm -rf /etc/ssh.zurueck && cp -a /root/ssh-rollback /etc/ssh.zurueck && rm -rf /etc/ssh && mv /etc/ssh.zurueck /etc/ssh && systemctl restart ssh"'
fi

# --no-overwrite-dir: Rechte und Besitzer vorhandener Verzeichnisse (/, /etc, …) bleiben unangetastet
tar -cf - --owner=root --group=root "${GEAENDERT[@]}" |
  ssh -o BatchMode=yes "$HOST" 'tar -C / --no-overwrite-dir -xf -'

if (( SSH_AENDERUNG )); then
  ssh -o BatchMode=yes "$HOST" 'sshd -t && systemctl restart ssh' ||
    echo "sshd -t schlug fehl – der Timer stellt in 5 Minuten den alten Stand her" >&2
fi
ssh -o BatchMode=yes "$HOST" "waschsalon-lock log $WER 'deploy: ${GEAENDERT[*]}'" 2>/dev/null || true
echo "Übertragen: ${GEAENDERT[*]}"
if (( SSH_AENDERUNG )); then
  echo "SSH geändert: in einer NEUEN Verbindung testen, dann innerhalb von 5 Minuten"
  echo "  ssh $HOST systemctl stop waschsalon-rollback.timer"
fi
