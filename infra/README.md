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
  - **Caddy** als einziger Dienst nach außen (80/443), holt das Zertifikat selbst. In `.env`:
    `HUB_DOMAIN=<domain oder IP>`, `HUB_BIND=0.0.0.0`, `HUB_BASE_URL=https://<domain oder IP>`.
    Seit dem 21.10. läuft er so auf der IP des Servers: Let's Encrypt gibt für IPs nur kurzlebige
    Zertifikate (Profil `shortlived`, ca. 6 Tage, Caddy erneuert), und weil Browser bei IPs kein
    SNI schicken, steht die IP zusätzlich in `HUB_DEFAULT_SNI`. Mit `, http://localhost` in
    `HUB_DOMAIN` geht der SSH-Tunnel weiterhin. Leeres `HUB_BIND` = nur `127.0.0.1`.
  - **Postgres 18** im internen Netz `db` (kein Weg nach draußen, kein veröffentlichter Port),
    Daten in `/srv/nexhub/daten/postgres`.
  - Geheimnisse und Domain nur in `/srv/nexhub/.env` (Rechte 600, Vorlage `env.beispiel`).
  - **api**: der Hub (`hub/`), gebaut auf dem Server aus einem Klon in `/srv/nexhub/src`:
    `ssh waschsalon nexhub-update claude-gamunex <branch>` (Sperre nötig). Caddy leitet alles an
    ihn weiter. Zusätzlich per Tunnel: `ssh -L 8080:127.0.0.1:80 waschsalon`, dann
    http://localhost:8080 (der Login springt danach aber zu `HUB_BASE_URL`).
  - Hochgeladene Runs liegen in `/srv/nexhub/daten/hub/runs/` (gehört Nutzer 10001). Die
    nächtliche Sicherung erfasst bisher nur die Datenbank, nicht diese Dateien.
  - Übernehmen nach einem Deploy: `ssh waschsalon 'cd /srv/nexhub && docker compose up -d'`.
  - **bot**: TheWashBot (`bot/`), gebaut aus demselben Klon, läuft seit dem 21.10. hier. Startet nur
    mit `COMPOSE_PROFILES=bot` in `.env`, damit er nie parallel zu einer anderen Instanz mit
    demselben Discord-Token läuft. Einstellungen in `/srv/nexhub/bot.env` (Vorlage
    `bot.env.beispiel`), Daten in `/srv/nexhub/daten/bot/`. Keine veröffentlichten Ports: Der Hub
    spricht ihn über `BOT_CONTROL_URL=http://bot:8790` mit `BOT_CONTROL_KEY` an (Bereich „Bot“),
    Caddy leitet `/api/aion/*`, `/runs/*`, `/leaderboard/*` (Port 8789) und `/dps/*` (8787) an ihn.
- Sicherung: `nexhub-sicherung.timer` macht nachts um 03:30 UTC ein `pg_dumpall` nach
  `/srv/nexhub/sicherung` (zstd, 14 Tage). Liegt noch auf demselben Server – Abholen nach
  außen fehlt.

## Bot-Umzug vom alten Server

Erledigt am 21.10.2026 (claude-navonex, siehe `/srv/waschsalon/CHANGELOG.md`): Bot läuft im Stack,
der alte auf dem früheren Server ist gestoppt. Ablauf zum Nachlesen bzw. für einen erneuten Umzug
(Sperre halten):

1. `/srv/nexhub/bot.env` aus `bot.env.beispiel` anlegen (Rechte 600), `BOT_CONTROL_KEY` in `.env`
   setzen (`openssl rand -base64 32 | tr -d '/+='`).
2. Bot auf dem alten Server stoppen, dessen `data/` komplett nach `/srv/nexhub/daten/bot/`
   kopieren (`bot.sqlite3` und `runs/` mit den gespeicherten AION-Läufen).
3. In `.env` `COMPOSE_PROFILES=bot` einkommentieren, `nexhub-update <wer> <branch>`.
4. Im Hub unter Bot → Übersicht prüfen, ob er verbunden ist. DeckBar-Ziele (AION-API, DPS-Webhook)
   auf die neue Adresse umstellen, sobald es eine Domain gibt.

Zurück: Profil wieder auskommentieren, `docker compose up -d --remove-orphans`, alten Bot starten.

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
