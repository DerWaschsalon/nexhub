# infra: VPS waschsalon

Debian 13 als unprivilegierter LXC-Container (Proxmox), 2 Kerne, 6 GB RAM, 59 GB.
Zugang nur per SSH-Schlüssel, der Anbieter hat keine Konsole.

## Aufbau
- `server/`: Dateien, wie sie auf dem Server liegen sollen, Pfade relativ zu `/`.
- `deploy.sh`: vergleicht `server/` mit dem Server und überträgt Abweichungen.
- `server/usr/local/bin/waschsalon-lock`: Sperre und Änderungsprotokoll
  (`/srv/waschsalon/CHANGELOG.md`).

## Ablauf einer Änderung
```
ssh waschsalon waschsalon-lock holen claude-gamunex "Firewall"
# Datei unter infra/server/ anlegen oder ändern, committen
infra/deploy.sh claude-gamunex             # zeigt die Unterschiede
infra/deploy.sh claude-gamunex --anwenden  # überträgt und protokolliert
ssh waschsalon waschsalon-lock freigeben claude-gamunex
```

Änderungen unter `etc/ssh/` spielt `deploy.sh` mit einem Rücknahme-Timer ein: Wird er nicht
innerhalb von 5 Minuten mit `ssh waschsalon systemctl stop waschsalon-rollback.timer` gestoppt,
kommt die vorherige SSH-Konfiguration zurück. Vorher in einer neuen Verbindung den Login testen.

## Besonderheiten
- Die `sshd_config` des Anbieters hatte kein `Include /etc/ssh/sshd_config.d/*.conf`. Ohne die
  Zeile ganz oben wirken Dateien in `sshd_config.d/` nicht.
- Das Journal ist dauerhaft (`/var/log/journal`), Logs überleben einen Neustart.
- Nach einem Neustart über das Panel war das Netz noch etwa 4 Minuten weg, bevor SSH antwortete.
