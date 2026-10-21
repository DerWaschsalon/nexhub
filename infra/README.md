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
- NexHub-Stack unter `/srv/nexhub` (`srv/nexhub/compose.yml`, Projekt `nexhub`):
  - **Caddy** als einziger Dienst nach außen (80/443). Solange es keine Domain gibt, lauscht er
    nur auf `127.0.0.1` (Zugang per SSH-Tunnel), weil es ohne Domain kein HTTPS gibt. Mit Domain
    in `.env`: `HUB_DOMAIN=<domain>`, `HUB_BIND=0.0.0.0`, `HUB_BASE_URL=https://<domain>`, dann
    holt Caddy das Zertifikat selbst.
  - **Postgres 18** im internen Netz `db` (kein Weg nach draußen, kein veröffentlichter Port),
    Daten in `/srv/nexhub/daten/postgres`.
  - Geheimnisse und Domain nur in `/srv/nexhub/.env` (Rechte 600, Vorlage `env.beispiel`).
  - **api**: der Hub (`hub/`), gebaut auf dem Server aus einem Klon in `/srv/nexhub/src`:
    `ssh waschsalon nexhub-update claude-gamunex <branch>` (Sperre nötig). Caddy leitet alles an
    ihn weiter. Ohne Domain erreichbar per Tunnel: `ssh -L 8080:127.0.0.1:80 waschsalon`, dann
    http://localhost:8080.
  - Übernehmen nach einem Deploy: `ssh waschsalon 'cd /srv/nexhub && docker compose up -d'`.
- Sicherung: `nexhub-sicherung.timer` macht nachts um 03:30 UTC ein `pg_dumpall` nach
  `/srv/nexhub/sicherung` (zstd, 14 Tage). Liegt noch auf demselben Server – Abholen nach
  außen fehlt.

## Besonderheiten
- **Der Anbieter filtert nicht** (21.10. geprüft: SYNs auf 80, 443 und 8081 kommen an `eth0` an,
  Caddy war auf 80 von außen erreichbar). Die frühere Annahme „nur 22 offen“ entstand, als dort
  nichts lauschte. Was nicht nach außen soll, muss also selbst gesperrt oder auf `127.0.0.1`
  gebunden werden. Das Kundenpanel kann nur neu starten.
- Docker-Ports laufen an der `input`-Kette vorbei (forward/DNAT). Container nur auf `127.0.0.1`
  veröffentlichen und über einen Reverse-Proxy nach außen geben. Die einzige Ausnahme ist Caddy
  mit 80/443 – deshalb stehen die beiden Ports nicht in `nftables.conf`.
- Container, die einen Dienst auf dem Host selbst erreichen wollen, laufen in die `input`-Kette
  und brauchen dort eine Regel.
- Die `sshd_config` des Anbieters hatte kein `Include /etc/ssh/sshd_config.d/*.conf`. Ohne die
  Zeile ganz oben wirken Dateien in `sshd_config.d/` nicht.
- Das Journal ist dauerhaft (`/var/log/journal`), Logs überleben einen Neustart.
- Nach einem Neustart über das Panel war das Netz noch etwa 4 Minuten weg, bevor SSH antwortete.
- 20.10.: ca. 25 Minuten kein SSH, bis zum Neustart über das Panel. Wahrscheinlich ausgelöst durch
  ein `openssh-server`-Update mit anschließendem `systemctl reload ssh`. Nach SSH-Updates lieber
  `systemctl restart ssh` mit Rücknahme-Timer und neuer Verbindung zum Testen.
