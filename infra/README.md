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

Änderungen unter `etc/ssh/` und an `etc/nftables.conf` spielt `deploy.sh` mit einem
Rücknahme-Timer ein: Wird er nicht innerhalb von 5 Minuten mit
`ssh waschsalon systemctl stop waschsalon-rollback.timer` gestoppt, kommt der vorherige Stand
zurück. Vorher in einer neuen Verbindung den Login testen.

## Was eingerichtet ist
- SSH nur mit Schlüssel (`etc/ssh/`), Root-Login nur per Schlüssel.
- Hostname `waschsalon`; `etc/.pve-ignore.hostname` hält Proxmox davon ab, ihn beim Start
  zurückzusetzen.
- Sicherheitsupdates automatisch (`unattended-upgrades`, `etc/apt/apt.conf.d/20auto-upgrades`).
- Firewall `etc/nftables.conf`: eigene Tabelle `inet waschsalon`, rein nur SSH und ICMP.
- Docker aus download.docker.com mit Compose-Plugin, Logs rotiert (`etc/docker/daemon.json`).
  Läuft im unprivilegierten LXC (overlayfs, cgroup v2). Docker-Updates kommen nicht automatisch.

## Besonderheiten
- **Der Anbieter filtert vor dem Server**: von außen ist nur Port 22 erreichbar, alles andere läuft
  in einen Timeout, auch ohne eigene Firewall. Für den Hub müssen 80/443 im Kundenpanel
  freigeschaltet werden.
- Docker-Ports laufen an der `input`-Kette vorbei (forward/DNAT). Container nur auf `127.0.0.1`
  veröffentlichen und über einen Reverse-Proxy nach außen geben.
- Container, die einen Dienst auf dem Host selbst erreichen wollen, laufen in die `input`-Kette
  und brauchen dort eine Regel.
- Die `sshd_config` des Anbieters hatte kein `Include /etc/ssh/sshd_config.d/*.conf`. Ohne die
  Zeile ganz oben wirken Dateien in `sshd_config.d/` nicht.
- Das Journal ist dauerhaft (`/var/log/journal`), Logs überleben einen Neustart.
- Nach einem Neustart über das Panel war das Netz noch etwa 4 Minuten weg, bevor SSH antwortete.
- 20.10.: ca. 25 Minuten kein SSH, bis zum Neustart über das Panel. Wahrscheinlich ausgelöst durch
  ein `openssh-server`-Update mit anschließendem `systemctl reload ssh`. Nach SSH-Updates lieber
  `systemctl restart ssh` mit Rücknahme-Timer und neuer Verbindung zum Testen.
