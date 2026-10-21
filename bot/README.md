# Discord-Bot: Musik, Rollen, Moderation, Temp-Voice, Aufräumen

Ein Bot für alles, was ihr bisher mit mehreren Bots macht. Alle Befehle sind Slash-Befehle
(`/…`). Antworten, die nur dich betreffen, sieht auch nur du, damit die Kanäle sauber bleiben.

## Funktionen

| Bereich | Befehle | Was passiert |
|---|---|---|
| **Musik** | `/play`, `/skip`, `/stop`, `/pause`, `/weiter`, `/warteschlange`, `/jetzt`, `/lautstaerke`, `/wiederholen`, `/mischen`, `/entfernen` | YouTube-Links und -Suche, SoundCloud, Spotify-Links (Titel, Alben, Playlists, gesucht auf YouTube). Eine „Läuft gerade“-Nachricht mit Buttons, die alte wird gelöscht. Allein im Kanal geht der Bot nach 1 Min., bei leerer Warteschlange nach 5 Min. |
| **Radio** | `/radio sender:` oder `/radio url:` | Zehntausende Sender aus radio-browser.info, Vorschläge beim Tippen. Oder direkt eine Stream-Adresse. |
| **Rollen** | `/rollen-panel` | Nachricht mit Buttons, über die man sich Rollen selbst nimmt oder abgibt. Funktioniert auch nach Neustarts. |
| **Willkommen** | `/setup willkommen`, `/setup autorolle` | Begrüßung mit Platzhaltern `{user}`, `{name}`, `{server}`, `{anzahl}`, Rolle für Neue |
| **Verifizierung** | `/setup verifizierung`, `/setup regeln-text` | Panel mit Regeln + „Regeln akzeptiert“-Button. Aktiv: @everyone sieht den Server erst nach Bestätigen, nur der Regel-Kanal bleibt sichtbar. Autorolle (z. B. „Neuling“) kommt trotzdem sofort beim Beitritt. `/setup regeln-text` ändert den Text im Panel nachträglich. Mit Vorschau/Bestätigung, `aus:True` schaltet wieder ab. |
| **Moderation** | `/setup log-kanal`, `/setup spamschutz`, `/timeout` | Log für gelöschte/bearbeitete Nachrichten, Beitritte (mit Warnung bei neuen Konten), Austritte, Banns, Rollen. Spamschutz: Flut, Massen-Erwähnungen, Einladungslinks. |
| **Verwarnungen** | `/warn`, `/warnungen`, `/warnung-loeschen`, `/kick`, `/ban`, `/unban`, `/setup verwarnungen` | Verwarnungen mit Historie (DM an Betroffene), automatische Strafe ab einstellbarer Schwelle (Timeout/Kick/Ban). |
| **Temp-Voice** | `/setup temp-voice`, `/vc name/limit/sperren/freigeben/einladen/uebernehmen` | Wer „➕ Kanal erstellen“ betritt, bekommt einen eigenen Sprachkanal, der leer wieder verschwindet. |
| **Aufräumen** | `/aufraeumen nachrichten`, `/aufraeumen bots`, `/aufraeumen bericht` | Alte Nachrichten löschen (Filter nach Alter, Person, nur Bots), alte Bots entfernen, Bericht über tote Kanäle und leere Rollen. Immer erst mit Vorschau und Bestätigung. |
| **Erinnerungen** | `/erinnere wann: text: privat:` | Zeit relativ (`2h`, `30m`, `1d2h`) oder absolut (`18:30`, `24.12. 18:00`). `/erinnerungen` zeigt eigene offene Erinnerungen, `/erinnerung-loeschen` entfernt eine. |
| **Tickets** | `/setup tickets rolle:` (fügt hinzu/entfernt, mehrere möglich; im Klick-Panel per Mehrfachauswahl), `/ticket-panel` | Panel mit Buttons (❓ Frage, ⚠️ Meldung, 📋 Bewerbung) → Modal → privater Thread mit allen Team-Rollen. „Schließen“ im Thread beendet ihn, sperrt ihn und schickt den Verlauf als `.txt` in den Log-Kanal. |
| **Benachrichtigungen** | Button „🔔 Benachrichtigungen" im Klick-Panel | GitHub-Repos beobachten (Releases, Issues, Pull Requests, Commits) per Klick-Assistent, komplett über Buttons/Select-Menüs/Modals, kein Befehl nötig. Modular für weitere Dienste (YouTube, Twitch, RSS, …) — siehe `bot/notify/`. |
| **AION-2** | `/aion kanal:`, `/aion token:True` | Runs aus dem NexBoard: ein Post je Dungeon-Lauf mit Rangliste (auch wenn mehrere Mitspieler melden), Link in den NexHub und Bestenliste je Boss. Siehe „AION-2: Runs aus dem NexBoard“ unten. |
| **DJ-Rolle** | `/setup dj-rolle` | Optional: Dann dürfen nur DJ, Admins und wer den Song gewünscht hat, überspringen und stoppen. |
| **Bump-Erinnerung** | `/setup bump kanal: rolle:`, auch im Klick-Panel | Erkennt die Bump-Bestätigung von [DISBOARD](https://disboard.org) im festgelegten Kanal und erinnert nach Ablauf des 2-Stunden-Cooldowns per Ping (optionale Rolle) daran, `/bump` erneut zu tippen. Rein passiv, der Bot bumpt nicht selbst. |
| **Mitglieder-Zähler** | `/setup mitglieder-zaehler kanal:`, auch im Klick-Panel | Name eines Sprachkanals zeigt laufend die aktuelle Mitgliederzahl (z. B. „👥 Mitglieder: 123“), aktualisiert bei Beitritt/Austritt und mindestens alle 10 Minuten (Discords Limit für Kanal-Umbenennungen). |
| **Starboard** | `/setup starboard kanal: schwelle:`, auch im Klick-Panel | Nachrichten ab X ⭐-Reaktionen (ohne die des Autors selbst, Standard 3) landen als Embed in einem Highlight-Kanal, Sterne-Zähler aktualisiert sich live, Post verschwindet wieder, wenn die Reaktionen unter die Schwelle fallen. |
| **Bots-Zähler** | `/setup bots-zaehler kanal:`, auch im Klick-Panel | Zweiter, unabhängig einstellbarer Sprachkanal zeigt die Bot-Anzahl (z. B. „🤖 Bots: 12“). |
| **Voice-Statistik** | `/sprachzeit`, XP per `/setup sprachzeit-xp` oder im Klick-Panel | Zeit im Sprachkanal läuft mit (nicht allein, nicht im AFK-Kanal, nicht selbst taub/stumm), optional zusätzlich XP pro Minute für ein künftiges Levelsystem. |
| **Umfragen** | `/umfrage frage: antworten: dauer_stunden: mehrfachauswahl:` | Native Discord-Umfrage, 2–10 Antworten durch `\|` getrennt. |
| **Geburtstage** | `/geburtstag-setzen tag: monat:`, `/geburtstag-loeschen`, `/geburtstag`, Kanal per `/setup geburtstage` oder im Klick-Panel | Tägliche Gratulation um 9 Uhr (Europe/Berlin) im eingerichteten Kanal. |
| **Embed-Ersteller** | `/embed-erstellen kanal:` | Formular (Titel, Beschreibung, Hex-Farbe, Bild-URL), postet das fertige Embed. |
| **Eigene Befehle** | `/befehl-erstellen name: antwort:`, `/befehl-loeschen`, `/befehle` | `!name` im Chat antwortet mit dem hinterlegten Text, Platzhalter `{user}`/`{server}`. |
| **Zeitgesteuerte Ankündigungen** | `/ankuendigung-erstellen kanal: text: intervall_minuten:`, `/ankuendigungen`, `/ankuendigung-loeschen` | Text wird automatisch alle X Minuten in einen Kanal gepostet. |
| **Benachrichtigungen: YouTube** | Dienst „YouTube" im Klick-Assistenten (🔔) | Neue Videos per öffentlichem RSS-Feed, ohne API-Schlüssel — braucht die Kanal-ID (beginnt mit „UC…"). |
| **Giveaways** | `/giveaway-erstellen kanal: preis: dauer: gewinner:`, `/giveaway-reroll` | Embed mit „🎉 Teilnehmen"-Button (An-/Abmelden), automatische Auslosung nach Ablauf, Reroll für neue Gewinner. `dauer` im selben Format wie bei `/erinnere` (z. B. `2h`, `1d2h`). |
| **Levelsystem** | `/rang`, `/rangliste`, `/level-xp-geben`, `/level-belohnung`, `/level-kanal-ohne-xp`, `/level-rolle-ohne-xp`, an/aus per `/setup level` oder im Klick-Panel | 15–25 XP pro Nachricht (60 s Abklingzeit), Rangkarte als Bild, Level-Up-Nachricht, kumulative Rollen-Belohnungen. Standardmäßig **aus**, bis ein Server es einschaltet. |
| **Server-Status** | `/server`, `/server-neustart container:`, `/server-update` — nur für `OWNER_ID` | CPU/RAM/Uptime/Festplatte, laufende Container. `/server-update` zieht das neueste Image von GHCR und ersetzt den Bot-Container live damit (kurze Downtime). Braucht den Docker-Socket gemountet (in `docker-compose.yml` auskommentiert, siehe „Server-Status einrichten" unten) — **Root-Zugriff auf den Host**, deshalb bewusst nur eine einzelne Person statt einer Rolle. |
| **Automod erweitert** | `/setup automod`, auch im Klick-Panel | Wortfilter, Großbuchstaben-Filter, Emoji-Spam-Grenze, Link-Filter mit erlaubten Domains — jeder Verstoß zählt zusätzlich als automatische Verwarnung (zählt mit Richtung der automatischen Strafschwelle). |

`/setup anzeigen` zeigt alle Einstellungen, `/setup panel` öffnet sie zum Anklicken (Kanal-/Rollen-
Auswahl per Dropdown, Text per Formular, Ein/Aus per Knopf — kein Befehl tippen nötig). Das
Klick-Panel deckt inzwischen **alle** `/setup`-Einstellungen ab, inklusive Verwarnungs-Schwelle
und der kompletten Verifizierungs-Ersteinrichtung (mit Vorschau/Bestätigung
wie beim Befehl).
`/setup management-kanal kategorie:` legt einen festen Kanal mit genau diesem Klick-Panel an (z. B.
unter einer internen Admin-Kategorie) — bleibt dauerhaft da und funktioniert auch nach einem
Neustart des Bots weiter. Die `/setup`- und `/aufraeumen`-Befehle sehen nur Leute mit
„Server verwalten“.

## 1. Bot bei Discord anlegen

1. <https://discord.com/developers/applications> → **New Application**, Name z. B. eures Servers
2. Links **Bot** → **Reset Token** → Token kopieren (kommt in `.env`, niemals teilen)
3. Auf derselben Seite unter **Privileged Gateway Intents** einschalten:
   **Server Members Intent** und **Message Content Intent**
4. Bot einladen mit diesem Link (Client-ID von der Seite **OAuth2** einsetzen):

   ```
   https://discord.com/oauth2/authorize?client_id=DEINE_CLIENT_ID&scope=bot+applications.commands&permissions=1099800374290
   ```

   Die Rechte: Kanäle sehen, Nachrichten senden/verwalten/Verlauf lesen, Links einbetten, Dateien,
   externe Emojis, Sprache verbinden/sprechen/verschieben, Kanäle und Rollen verwalten, kicken,
   Timeout.
5. Nach dem Einladen in den **Servereinstellungen → Rollen** die Rolle des Bots **über** die Rollen
   ziehen, die er vergeben soll (Autorolle, Rollen-Panel) und über die Bots, die er entfernen soll.

## 2. Auf dem Home-Server starten (Docker)

Das Image wird von GitHub Actions gebaut und nach `ghcr.io/derwaschsalon/thewashbot` gepusht (bei jedem
Push auf `main`, der diesen Ordner betrifft). `docker-compose.yml` zieht dieses fertige Image,
kein Bauen mehr auf dem Server nötig.

```sh
cp .env.example .env        # DISCORD_TOKEN und DEV_GUILD_ID eintragen
docker compose pull
docker compose up -d
docker compose logs -f      # "Angemeldet als …" und "… Slash-Befehle registriert"
```

Ist das GHCR-Paket `thewashbot` **privat** (Standard bei privaten Repos), braucht `docker compose
pull` vorher einen Login mit einem GitHub-PAT (Scope `read:packages`):

```sh
echo "<PAT>" | docker login ghcr.io -u navonex --password-stdin
```

Alternative: Paket-Sichtbarkeit auf GitHub (Package-Einstellungen → Change visibility → Public)
umstellen, dann entfällt der Login.

**Unraid:** Ordner z. B. nach `/mnt/user/appdata/discord-bot` kopieren und dort im Terminal die
Befehle oben ausführen (Plugin „Docker Compose Manager“), oder das Image bauen und als Container
mit `/data` → `/mnt/user/appdata/discord-bot/data` und den Variablen aus `.env` anlegen.

Die Einstellungen liegen in `data/bot.sqlite3`. Bei jedem Start aktualisiert der Container
yt-dlp, weil YouTube regelmäßig etwas ändert. Spielt YouTube nicht mehr: Container neu starten.

## 3. Einrichten (in Discord)

```
/setup log-kanal kanal:#mod-log
/setup willkommen kanal:#willkommen text:Hey {user}, willkommen auf {server}! Schau in #regeln vorbei.
/setup autorolle rolle:@Mitglied
/setup temp-voice                       (legt Kategorie + „➕ Kanal erstellen“ an)
/rollen-panel rollen:🎮 @Gamer 🎵 @Musik 📢 @News titel:Wähl deine Rollen
/setup tickets rolle:@Team
/ticket-panel titel:Support text:Klick auf einen Button, um ein Ticket zu eröffnen.
```

## Aufräumen: so gehen wir vor

1. `/aufraeumen bericht` → du bekommst eine `.md`-Datei mit allen Kanälen (letzte Aktivität),
   Rollen (wie viele Mitglieder) und Bots. Die kannst du mir schicken, dann machen wir gemeinsam
   einen Plan, was weg kann.
2. `/aufraeumen bots` → Liste aller Bots, Auswahl der alten, Bestätigen. 🔒 heißt: Der Bot steht
   über meiner Rolle, also erst die Rolle verschieben.
3. `/aufraeumen nachrichten kanal:#musik nur_bots:True` → z. B. alle alten Ausgaben der früheren
   Musikbots weg. Mit `aelter_als_tage:` bleibt Neues stehen, angepinnte Nachrichten bleiben
   standardmäßig. Nachrichten älter als 14 Tage löscht Discord nur einzeln, das dauert länger.

## Gut zu wissen

- **YouTube:** Das Abspielen von YouTube über Bots verstößt gegen die YouTube-AGB, deshalb wurden
  große Bots wie Rythm abgeschaltet. Für einen privaten Server ist das Risiko gering, aber es kann
  sein, dass YouTube die IP zeitweise blockiert („Sign in to confirm you're not a bot“). Dann hilft
  eine Cookies-Datei (`YTDLP_COOKIES`, siehe yt-dlp-Doku), am besten von einem Zweitkonto.
- **Spotify** liefert kein Audio. Der Bot liest Titel und Interpret und sucht sie auf YouTube.
  Ohne API-Schlüssel liest er die öffentliche Einbettungsseite (bis ~100 Titel). Von Spotify selbst
  erstellte Playlists (z. B. „Today's Top Hits“) gibt die API seit Ende 2024 nicht mehr heraus.
- **Spamschutz** ignoriert Bots und alle mit „Nachrichten verwalten“.

## Benachrichtigungen (GitHub) einrichten

Im Klick-Panel (`/setup panel` oder `/setup management-kanal`) → Button **🔔 Benachrichtigungen**
→ **➕ Neue Benachrichtigung**: Dienst (aktuell nur GitHub) → Repository (wird geprüft) →
Ereignisse (Mehrfachauswahl: Releases, neue/geschlossene Issues, neue/geschlossene/gemergte Pull
Requests, Commits) → Ziel-Kanal → optionale Filter (Labels, Autor, Pre-Releases/Drafts) →
Zusammenfassung mit Speichern/Abbrechen. Danach sofort ein stiller erster Abgleich (postet nichts,
verhindert, dass alte Releases/Issues/PRs beim Einrichten als „neu" durchgehen).

Unter **⚙️ Benachrichtigungen verwalten**: pro Eintrag Bearbeiten (Ereignisse/Kanal), De-/Aktivieren,
Löschen, **🧪 Testbenachrichtigung** (schickt eine echte Beispiel-Meldung in den Zielkanal — prüft
damit auch, ob der Bot dort wirklich schreiben darf). **🔄 Aktualisieren** fragt sofort ab, statt
auf den nächsten Durchlauf zu warten (`NOTIFY_POLL_MINUTES`, Standard 10).

Discussions sind bewusst nicht dabei (nur über GitHub GraphQL abrufbar, nicht über die hier
genutzte REST-API). Ohne `GITHUB_TOKEN` in der `.env` erlaubt GitHub nur 60 Anfragen/Stunde
**insgesamt** — reicht nur für wenige Repos bei 10-Minuten-Takt. Mit einem Token (nur Lesen nötig,
github.com/settings/tokens) sind es 5000/Stunde.

Architektur für weitere Dienste: `bot/notify/base.py` (Schnittstelle `Provider`), `bot/notify/github.py`
(erster Provider), `bot/notify/manager.py` (Registry + Abfrage/Dedup/Fehlerbehandlung). Ein neuer
Dienst (YouTube, Twitch, RSS, …) implementiert nur `Provider` und trägt sich in `PROVIDERS` ein —
die Discord-Oberfläche in `bot/cogs/notifications.py` kennt nichts Dienst-Spezifisches.

## AION-2: Runs aus dem NexBoard

Jedes [NexBoard](../nexboard/) schickt nach einem beendeten Dungeon-Run die Eckdaten an den Bot
(Modul „Discord-Bot“, `nexboard/daemon/deckbar_daemon/bot.py`). Laufen mehrere Leute denselben
Dungeon, wartet der Bot kurz (`wartezeit`, Standard 15 s), führt alle Meldungen zu einer Rangliste
zusammen und postet genau einmal: Gesamt-Rangliste als Bild, dazu je Boss ein Bild (max. 9 pro
Nachricht, Discords Limit). Unter „📊 Analyse“ stehen „Im NexHub ansehen“ (den Link meldet der Hub
nach dem Upload, siehe `control.py`, `run-link`) und die Bestenliste je Boss
(`<AION_PUBLIC_URL>/leaderboard/<guild_id>`, öffentlich, ohne Login).

1. `AION_PUBLIC_URL` in der `.env` setzen (öffentliche Adresse ohne Slash am Ende, auf dem VPS die
   Hub-Domain; Caddy leitet `/api/aion/*` und `/leaderboard/*` auf Port 8789 des Bots).
2. `/aion kanal:#der-kanal` in Discord (auch im Klick-Panel unter „AION 2“ oder im Hub).
3. `/aion token:True` zeigt Adresse und Token. Beides im NexBoard unter Discord-Bot eintragen.
   Geheim halten, nur an NexBoards geben, die mitmachen sollen.

Das NexBoard schickt pro Run:

```
POST <AION_PUBLIC_URL>/api/aion/fight
Authorization: Bearer <Token aus /aion>
Content-Type: application/json

{
  "dungeon": "Ferocious Horn Den", "difficulty": "Normal",
  "bosses_total": 3, "bosses_killed": 3,
  "start_ms": 1760445123000, "fight_ms": 350000,
  "players": [{"name": "ReZero", "cls": "ranger", "damage": 13290000, "dps": 38000}, …],
  "bosses": [                                         // optional, für die Bilder je Boss
    {"name": "Boss 1", "players": [{"name": "ReZero", "damage": 4200000, "dps": 41000}, …]},
    …
  ]
}
```

Gleicher Lauf heißt: gleicher Dungeon, gleiche Boss-Anzahl und -Siege, Startzeit höchstens 30 s und
Kampfzeit höchstens 20 s auseinander. Bei abweichenden Werten für denselben Spieler gewinnt der höhere.

## Einstellungen im Browser

Die Einstellungen ändert man im Bereich „Bot“ des NexHub (siehe `hub/README.md`) oder in Discord
mit `/setup panel`. Das alte eigene Web-Dashboard des Bots gibt es nicht mehr.

### Steuerung über den NexHub

Für den Bereich „Bot“ im NexHub hat der Bot eine JSON-Steuer-API (`bot/cogs/control.py`, Port 8790), die nur startet, wenn
`BOT_CONTROL_KEY` gesetzt ist (mindestens 24 Zeichen, derselbe Wert wie beim Hub). Jede Anfrage
braucht `Authorization: Bearer <BOT_CONTROL_KEY>`. Den Port nie veröffentlichen: Er ist für das
interne Docker-Netz gedacht, wer den Schlüssel hat, darf alle Einstellungen ändern.

Die Formular-Bereiche stehen einmal in `SECTIONS` (Feldtyp, Beschriftung, Hinweis); der Hub
zeichnet daraus seine Formulare. Ein neues Feld = ein `Field(...)`-Eintrag dort.

## Server-Status einrichten

`/server` (Status, laufende Container), `/server-neustart container:` (ein anderer Container neu
starten) und `/server-update` (den Bot-Container selbst mit dem neuesten GHCR-Image aktualisieren)
brauchen Zugriff auf den Docker-Daemon des Hosts — das ist **Root-Zugriff auf diesen Server**,
deshalb bewusst nicht standardmäßig aktiv und auf eine einzelne Person beschränkt statt auf eine
Rolle.

1. In `docker-compose.yml` die auskommentierte Zeile beim `volumes:`-Block einkommentieren:
   `- /var/run/docker.sock:/var/run/docker.sock`
2. In der `.env`: `OWNER_ID=<deine Discord-User-ID>` eintragen (Rechtsklick auf dich selbst in
   Discord → ID kopieren, braucht den Entwicklermodus). Nur diese Person sieht die drei Befehle.
3. `docker compose up -d` — danach sind `/server`, `/server-neustart`, `/server-update` aktiv.

**Wie `/server-update` funktioniert:** zieht `ghcr.io/derwaschsalon/thewashbot:latest`, liest die
laufende Container-Konfiguration aus (Umgebungsvariablen, Volumes, Ports, Restart-Policy) und
startet damit einen kurzlebigen Helfer-Container (`bot/selfupdate_helper.py`), der wartet, bis
der alte Bot-Container gestoppt ist, ihn entfernt und den neuen mit identischer Konfiguration,
aber dem neuen Image anlegt. Läuft als eigener Container, weil sich ein laufender Prozess nicht
mitten im eigenen Lauf selbst ersetzen kann. Dauert ein paar Sekunden, in denen der Bot offline
ist. **Falls dabei etwas schiefgeht:** auf unraid-server `cd /mnt/user/appdata/thewashbot && docker
compose up -d` stellt den Bot anhand der `docker-compose.yml` wieder her — die bleibt die ganze
Zeit unverändert auf der Platte liegen, als Netz.

## Entwickeln und testen

```sh
pip install -r requirements.txt pytest
python -m pytest -q tests          # ohne Discord-Verbindung
DISCORD_TOKEN=… DB_PATH=./data/bot.sqlite3 python -m bot
```

## Lizenz

GNU General Public License v3.0, siehe [LICENSE](LICENSE).
