# Regeln für Claude-Instanzen in diesem Repo

An NexHub arbeiten zwei Claude-Instanzen: die von Fabio (gamunex) und die von Navonex.
Diese Regeln gelten für beide.

## Wer bist du?
Kürzel für Sperre, Protokoll und Commits: `claude-gamunex` oder `claude-navonex`. Weißt du nicht,
wessen Instanz du bist, frag nach, bevor du am Server etwas machst.

## VPS waschsalon
- Zugang: `ssh waschsalon` als root, nur mit Schlüssel. Die Adresse steht nicht im Repo, sondern
  im Eintrag `Host waschsalon` der eigenen `~/.ssh/config`. Der Anbieter hat **keine Konsole**, nur
  einen Neustart-Knopf. Wer SSH kaputt macht, sperrt alle aus.
- **Ersteinrichtung leitet claude-gamunex.** Bis Fabio oder Navonex sagen, dass sie abgeschlossen
  ist, schaut claude-navonex am Server nur nach und ändert nichts.
- **Vor jeder Änderung die Sperre holen**, danach protokollieren und freigeben:
  ```
  ssh waschsalon waschsalon-lock status
  ssh waschsalon waschsalon-lock holen claude-… "<wofür>"
  ssh waschsalon waschsalon-lock log claude-… "<was gemacht>"
  ssh waschsalon waschsalon-lock freigeben claude-…
  ```
  Ist die Sperre belegt: nichts ändern, warten oder über Fabio/Navonex nachfragen. Eine fremde
  Sperre mit `--erzwingen` lösen nur auf ausdrückliche Anweisung von Fabio oder Navonex.
- **Konfiguration gehört ins Repo.** Dateien liegen unter `infra/server/` (Pfade relativ zu `/`)
  und kommen mit `infra/deploy.sh <wer> --anwenden` auf den Server – erst committen, dann
  ausrollen. Was du von Hand am Server änderst, überschreibt beim nächsten Deploy jemand anderes.
- **SSH, Firewall, Netzwerk nur mit Rücknahme-Timer** (`systemd-run --on-active=5min …`, siehe
  `infra/deploy.sh`), Login danach in einer neuen Verbindung prüfen, erst dann den Timer stoppen.
- Nichts löschen, abschalten oder umbauen, was die andere Seite eingerichtet hat, ohne zu fragen.

## Repo
- Öffentlich, GPL-3. **Keine Geheimnisse und keine personenbezogenen Daten** in Code, Doku oder
  Commits: keine Tokens, keine privaten Mailadressen (Commits mit der GitHub-noreply-Adresse),
  keine echten Hostnamen, internen IPs oder Discord-IDs von Personen. Beispielwerte:
  `bot.example.com`, `unraid-server`, `192.168.1.10`.
- Aufbau: `nexboard/` (Touch-Leiste, Daemon, Overlay), `bot/` (TheWashBot), `hub/` (Kern + Module, auch die Log-Ansicht), `proto/`,
  `planner/`, `infra/` (VPS). Jeder Teil hat eine eigene README mit Tests.
- Tests vor dem Push: Daemon `cd nexboard/daemon && uv run python -m pytest -q`, Bot
  `cd bot && python -m pytest -q tests`, Hub `cd hub/api && uv run pytest -q` und
  `cd hub/web && npm run check`, Formate `cd proto && uv run pytest -q`.
- **Ein Arbeitszweig: `main`** (seit 21.10.2026; `monorepo` ist darin aufgegangen und gelöscht).
  `main` und `modular` sind außerdem die Zweige, auf denen laufende NexBoard-Installationen per
  `update.sh` aktualisieren (`modular` zieht nur noch nach). Dort keine Force-Pushes und keine
  Pfadänderungen ohne Absprache, sonst bricht das Update beim nächsten Klick ab oder der Daemon
  findet seine Dateien nicht. Hub ausrollen: `nexhub-update <wer> main`.
- Die Symlinks `daemon`, `capture`, `overlay` und `update.sh` an der Wurzel sind Übergänge für
  NexBoard-Checkouts aus der Zeit vor dem Monorepo (systemd-Unit, uv-Installation und Tray-Knopf
  zeigen dorthin). Nicht entfernen, solange es solche Installationen gibt.
