# Path of Exile im NexHub: Merkliste, Preisalarm und Preise im Bot

Stand 12.11.2026 · Wunsch von Navonex · Fabio weiß Bescheid

## Wozu

Navonex spielt Path of Exile 1 und 2. Im Spiel nimmt er für den Preis-Check die fertigen Overlays
(Awakened PoE Trade für PoE 1, Exiled Exchange 2 für PoE 2), die bauen wir nicht nach. Der NexHub
und TheWashBot sollen das ergänzen: Preise über die Zeit verfolgen, bei Bewegung Bescheid sagen und
Preise in Discord abfragbar machen. Später kommt der Wert der eigenen Vorratskisten dazu.

Grenze von poe.ninja (offizielle API-Doku, https://poe.ninja/docs/api): Die Preis-Endpunkte dürfen
genutzt werden, aber **nicht, um die Seite nachzubauen**, sondern für etwas Neues. Wer sich nicht
daran hält oder zu viel abfragt, wird gesperrt. Deshalb gibt es im Hub **keine allgemeine
Preisliste zum Stöbern**, sondern nur, was poe.ninja nicht bietet: eine persönliche Merkliste mit
Verlauf über die ganze Liga, Alarme und den Bot. Zum Stöbern verlinkt der Hub auf poe.ninja.

## Zwei Stufen

1. **Preise (dieses Dokument):** Abruf von poe.ninja, Merkliste im Hub, Preisalarm, `/poe preis`
   und der tägliche Post „Gewinner und Verlierer“ im Bot.
2. **Vorratskisten-Wert (eigener Entwurf später):** Login mit dem PoE-Konto über die OAuth-API von
   GGG, Kisten auslesen, Wert mit den Preisen aus Stufe 1, Vermögenskurve über die Liga. Nur
   PoE 1, weil GGG den Kisten-Endpunkt nur für PoE 1 anbietet. Startet erst, wenn GGG die
   Anwendung freigeschaltet hat (Antrag stellt Navonex). Stufe 1 muss dafür nichts vorbereiten
   außer den Preisen selbst.

## Ziele (Stufe 1)

- Der Hub holt regelmäßig die Preise von poe.ninja für PoE 1 und PoE 2, jeweils für die aktuelle
  Challenge-Liga.
- Neuer Menüpunkt „Path of Exile“ im Hub, mit Schalter PoE 1 / PoE 2.
- **Merkliste:** Jeder Angemeldete legt Items an, die ihn interessieren, und sieht dafür Preis,
  Änderung über 24 h und 7 Tage und eine Kurve über die ganze Liga. Hinzufügen über eine Suche
  nach Namen.
- **Preisalarm:** Pro Eintrag eine Schwelle in Prozent. Bewegt sich der Preis darüber hinaus,
  meldet der Bot das in Discord und erwähnt den Besitzer.
- **`/poe preis`** im Bot: Spiel wählen, Item mit Autovervollständigung, Antwort mit Preis,
  Änderung und Link zum Item bei poe.ninja.
- **Täglicher Post** im Bot: je Spiel die größten Gewinner und Verlierer der aktuellen Liga.

## Nicht-Ziele

- Keine Preisliste oder Kategorie-Ansichten zum Durchstöbern (Nachbau von poe.ninja).
- Kein eigener Preis-Check im Overlay, keine Anbindung an Awakened PoE Trade oder Exiled Exchange 2.
- Keine Abfragen an die offizielle Handelsseite von GGG.
- Kein Kisten-Wert, kein PoE-Konto-Login (Stufe 2).
- Keine Liga-Countdowns oder Patchnotes (können später als Quelle in den Benachrichtigungs-
  Assistenten des Bots, `notify.feeds`).
- Nichts, was Eingaben im Spiel auslöst oder Handel automatisiert.

## Was auf keinen Fall passieren darf

- poe.ninja sperrt den Hub, weil er zu oft oder ohne Cache fragt.
- Die AION-Teile des Hubs oder des Bots gehen kaputt oder werden langsam.
- Geheimnisse, private Mailadressen oder Discord-IDs landen im Repo (öffentlich, GPL-3).

## Rahmen

- Regeln aus `CLAUDE.md` (Code-Stil und Neubau-Regeln): so wenig Code wie möglich, nichts doppelt,
  englische Bezeichner, deutsche Kommentare und Texte über die Übersetzungsdateien, Typangaben,
  `mypy --strict` im Bot, Fachlogik ohne Netz testbar.
- Hub: FastAPI + SQLAlchemy + Alembic (nächste Migration `0013`), SvelteKit-Module unter
  `hub/web/src/modules/<id>/`, Seiten unter `hub/web/src/routes/hub/…`, Kurven als eigenes SVG wie
  `logs/components/DpsChart.svelte` und `armory/components/History.svelte` (keine neue Abhängigkeit).
- Bot: Modul nach `bot/bot/core/module.py` (`BotModule`, `routes()`, `every()`, `cog()`,
  Einstellungen per `setting(...)` wie in `aion2/schedule/settings.py`).
- poe.ninja-Regeln: Antworten werden etwa 5 Minuten gecacht (ETag), Daten ändern sich bei PoE 1
  etwa alle 15 Minuten, bei PoE 2 etwa stündlich. Bedingte Anfragen nutzen, Cache-Header achten,
  eigener User-Agent mit Kontakt, wenig gleichzeitige Anfragen. Ohne Versionierung, Änderungen ohne
  Vorwarnung möglich.

## Ansätze

Betrachtet wurden drei Wege (Gespräch vom 12.11.2026):

- **A. Der Hub ergänzt die Overlays (gewählt).** Overlays bleiben unverändert, Hub und Bot bauen
  eigene Funktionen auf den Preisen von poe.ninja auf. Sauber getrennt, Updates der Overlays
  stören nicht. Nachteil: Was im Overlay geprüft wurde, landet nicht im Hub.
- **B. Overlays an den Hub anbinden.** Eigene Fassung von Awakened PoE Trade, die jeden Check an
  den Hub meldet. Verworfen: zwei fremde Programme dauerhaft nachpflegen.
- **C. Eigener Preis-Check im NexBoard-Overlay.** Verworfen: widerspricht dem Wunsch, die fertigen
  Tools zu nutzen.

Navonex hat A gewählt, mit der Änderung „Merkliste mit Alarm statt allgemeiner Preisliste“ wegen
der poe.ninja-Regeln.

## Aufbau

### Datenfluss

```
poe.ninja ──(stündlich, ETag)──► Hub: PoeNinja-Abruf ──► Tabellen poe_*
                                         │
                       Alarme + Tagespost berechnen (Hub)
                                         │
                     POST /control/poe/... ──► Bot: Modul poe.prices ──► Discord
Bot: /poe preis ──► GET Hub /api/internal/poe/... (Schlüssel) ──► Antwort in Discord
Browser ──► /api/poe/... (Login) ──► Merkliste
```

Die Preise werden **nur im Hub** abgerufen und gespeichert. Der Bot rechnet nichts, er zeigt nur an
(wie bei den Runs). Das hält die Abrufe an poe.ninja an einer Stelle.

### Hub: Abruf (`hub/api/nexhub_api/poe_ninja.py`)

- Eine Klasse für den Zugriff auf poe.ninja, ein Hintergrundauftrag in `main.py` neben den
  AION-Aufträgen, nur wenn `hub_poe_enabled` an ist.
- Je Spiel: Ligen holen (`/poe{1,2}/api/economy/leagues`), die erste ist die aktuelle
  Challenge-Liga. Die Liga lässt sich per Einstellung festnageln (`hub_poe1_league`,
  `hub_poe2_league`, leer = automatisch), für Zeiten ohne Challenge-Liga.
- Dann alle Kategorien der Exchange- und Stash-Übersichten des Spiels, nacheinander, mit
  `If-None-Match`. Die Liste der Kategorien steht genau einmal als Tabelle im Code (aus der
  poe.ninja-Doku übernommen).
- Takt: stündlich je Spiel. Schneller bringt nach der Doku keine frischeren Daten.
- User-Agent: `NexHub/<hub_version> (+https://github.com/DerWaschsalon/nexhub)`.
- Fehler einer Kategorie überspringen und loggen; der Rest läuft weiter. Ändert poe.ninja ein Feld,
  soll der Abruf scheitern, ohne alte Daten zu überschreiben.

### Hub: Daten (Migration `0013_poe`)

- `poe_items`: ein Eintrag je Item und Liga: Spiel, Liga, Kategorie, stabile Kennung von poe.ninja,
  Name, Symbol-URL, Link-Slug zur poe.ninja-Seite, letzter Preis, Einheit, Handelsvolumen bzw.
  Anzahl Angebote, Zeitpunkt. Wird bei jedem Abruf aktualisiert.
- `poe_prices`: ein Preis je Item und Tag (Tagesschnappschuss aller Items). Daraus kommen die
  Kurve über die ganze Liga, die 24-h- und 7-Tage-Änderung und der Tagespost. Auch Items, die erst
  später auf eine Merkliste kommen, haben so ihren Verlauf ab Liga-Beginn bzw. ab Start des Abrufs.
- `poe_watches`: Merkliste: Benutzer, **Spiel + feste Kennung von poe.ninja** (nicht eine Zeile
  in `poe_items`), Schwelle in Prozent, Referenzpreis und dessen Liga, Zeitpunkt des letzten
  Alarms.
- **Ligawechsel (Entscheidung Navonex 12.11.2026): die Merkliste wandert mit.** Wechselt die
  aktuelle Liga (neue Challenge-Liga oder Festlegung per Einstellung), zeigt die Merkliste dieselben
  Items in der neuen Liga. Der Referenzpreis wird dabei auf den ersten Preis der neuen Liga
  zurückgesetzt, damit kein Fehlalarm kommt. Gibt es ein Item in der neuen Liga (noch) nicht,
  bleibt der Eintrag mit dem Hinweis „in dieser Liga noch kein Preis“ stehen. Der Verlauf alter
  Ligen bleibt in `poe_prices` gespeichert, angezeigt wird die aktuelle Liga.
- Preise einheitlich in der Grundwährung, die poe.ninja für das Spiel liefert (PoE 1 Chaos, PoE 2
  laut `core.primary`), Einheit wird mit gespeichert.

### Hub: Alarm und Tagespost (`hub/api/nexhub_api/poe_alerts.py`)

- Nach jedem Abruf: für jeden Merklisten-Eintrag Preis gegen Referenzpreis. Über der Schwelle →
  Meldung an den Bot, danach wird der aktuelle Preis neuer Referenzpreis. Höchstens ein Alarm je
  Eintrag und Tag.
- Einmal am Tag (fester Zeitpunkt, Europe/Berlin): je Spiel die 5 größten Gewinner und 5 größten
  Verlierer gegenüber dem Vortag. Nur Items mit genug Handel bzw. Angeboten, sonst gewinnen
  Ausreißer mit einem einzigen Angebot.
- Versand über die bestehende Steuer-API des Bots wie `tell_bot` in `routes/runs.py` (dort in eine
  gemeinsame Hilfe ziehen statt kopieren). Fällt der Bot aus, geht nur die Meldung verloren.
- Die Discord-ID des Besitzers kennt der Hub aus dem Login, sie wird nur in der Meldung an den Bot
  mitgeschickt.

### Hub: API

```
GET    /api/poe/search?game=poe1&q=…        Items der aktuellen Liga nach Namen (für „hinzufügen“)
GET    /api/poe/watches?game=poe1            eigene Merkliste mit Preis, 24 h, 7 Tage, Verlauf
POST   /api/poe/watches                      Item merken (item, Schwelle)
PATCH  /api/poe/watches/{id}                 Schwelle ändern
DELETE /api/poe/watches/{id}                 entfernen
GET    /api/internal/poe/price?game=…&q=…    für den Bot: bester Treffer mit Preis und Änderung
GET    /api/internal/poe/complete?game=…&q=… für den Bot: Namen für die Autovervollständigung
```

- `/api/poe/*` nur mit Login, wie die Armory (`CurrentUser`). Jeder sieht nur seine Merkliste.
- `/api/internal/poe/*` nur mit dem gemeinsamen Schlüssel `BOT_CONTROL_KEY` im Header. Caddy
  reicht heute alles außer `/api/aion/*` und `/leaderboard/*` an `api:8000` weiter, also auch
  diesen Pfad. Deshalb bekommt `infra/server/srv/nexhub/Caddyfile` eine Regel, die
  `/api/internal/*` von außen mit 404 beantwortet. Der Bot erreicht die API direkt im
  Docker-Netz unter `http://api:8000`, nicht über Caddy.
- Die Suche liefert höchstens 20 Treffer. Sie dient zum Hinzufügen, nicht zum Stöbern.

### Hub: Oberfläche (`hub/web/src/modules/poe/`)

- Neues Spiel `game.poe` („Path of Exile“) in `lib/texts.ts`, Modul `poe` mit dem Reiter
  „Merkliste“, eingetragen in `lib/modules.ts`.
- Seite `routes/hub/poe/`: oben Schalter PoE 1 / PoE 2 und die aktive Liga, darunter Suchfeld
  „Item merken“, dann die Einträge als Karten: Symbol, Name, Preis, Änderung 24 h / 7 Tage, kleine
  Kurve (SVG), Schwelle zum Ändern, Entfernen, Link „bei poe.ninja ansehen“.
- Unten ein fester Hinweis „Preise: poe.ninja“ mit Link, und ein Link „Alle Preise bei poe.ninja“.
- Vorschau-Kachel für die Übersicht: die drei größten Bewegungen der eigenen Merkliste.
- Texte Deutsch und Englisch wie in den anderen Modulen.

```
Path of Exile                                    [ PoE 1 | PoE 2 ]  Liga: Runes of Aldur
┌ Item merken: [ Divine Orb…            ] ┐
┌────────────────────────────────────────────────────────────┐
│ [ico] Mirror of Kalandra     412 div    +6 % 24 h  −3 % 7 T │
│       ▁▂▃▅▆▇▆▅  Alarm ab ±20 %   [poe.ninja] [entfernen]    │
└────────────────────────────────────────────────────────────┘
Preise: poe.ninja · Alle Preise bei poe.ninja →
```

### Bot: Modul `poe.prices` (`bot/bot/modules/poe/prices/`)

- Einstellungen: Kanal für Alarme und Tagespost (leer = aus), Uhrzeit des Tagesposts ist fest im
  Hub, nicht im Bot.
- `routes()`: `r.control("poe/alert")` und `r.control("poe/daily")` nehmen fertige Daten vom Hub
  an und posten ein Embed. Der Alarm erwähnt den Besitzer.
- `cog()`: `/poe preis spiel:<PoE 1|PoE 2> item:<Name>` mit Autovervollständigung über den Hub.
  Antwort als Embed mit Symbol, Preis, Änderung und Link zu poe.ninja.
- Für die Abfrage an den Hub bekommt der Bot die Adresse der Hub-API im internen Netz als
  Einstellung (Umgebungsvariable, z. B. `HUB_INTERNAL_URL=http://api:8000`) und nutzt denselben
  Schlüssel wie die Steuer-API.

### Konfiguration

- Hub: `hub_poe_enabled` (Standard aus), `hub_poe1_league`, `hub_poe2_league` (leer = automatisch).
- Bot: `HUB_INTERNAL_URL` (Wert `http://api:8000`, Bot und Hub hängen am Netz `web`).
- Der Hub bekommt Umgebungsvariablen nur über die Liste im Dienst `api` in
  `infra/server/srv/nexhub/compose.yml`: `HUB_POE_*` dort eintragen, Werte in die `.env`. Der Bot
  liest `bot.env`: `HUB_INTERNAL_URL` in `bot.env.beispiel` aufnehmen und auf dem Server in `bot.env`
  setzen. Alles mit Sperre und Protokoll nach den Server-Regeln in `CLAUDE.md`. Keine Geheimnisse neu.

### Tests

- Hub: Abruf gegen einen nachgebauten poe.ninja (wie `tests/fake_metabot.py`) mit echten
  Beispielantworten je Endpunkt-Form: ETag-Wiederholung, kaputte Kategorie, Ligawechsel.
  Alarmlogik und Tagespost ohne Netz: Schwelle, einmal am Tag, Mindest-Handel, kein Alarm beim
  Ligawechsel, Eintrag ohne Preis in der neuen Liga.
  API: Merkliste nur für den eigenen Benutzer, interner Endpunkt nur mit Schlüssel.
- Web: `npm run check` ohne Fehler.
- Bot: Embeds für Alarm, Tagespost und `/poe preis` aus festen Eingaben; `ruff` und `mypy --strict`.

### Ausrollen

PR nach `main` mit grünen Tests, Review nach Branch-Schutz. Danach mit Sperre: geänderte
`Caddyfile` mit `infra/deploy.sh <wer> --anwenden`, `.env`-Einträge setzen, `nexhub-update <wer> main` (Migration `0013`), im Hub-Log den ersten Abruf prüfen, im Bot
den Kanal setzen, `/poe preis` und einen Test-Alarm in Discord ausprobieren.

## Dem Bauenden überlassen

- Genaue Zuordnung der Felder je Endpunkt-Form (Exchange vs. Stash, PoE 1 vs. PoE 2) auf
  `poe_items`, nach echten Antworten von poe.ninja. Insbesondere welche Kennung bei Varianten
  (Links, Gem-Stufe, verdorben) stabil und eindeutig ist.
- Schwelle für „genug Handel“ beim Tagespost, Standard-Schwelle des Alarms (Vorschlag ±20 %).
- Uhrzeit des Tagesposts (Vorschlag 18:00).
- Aufräumen von `poe_prices` alter Ligen (Vorschlag: behalten, ist klein genug).
