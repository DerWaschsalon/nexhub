# Parse-Plakette im DPS-Meter (Design)

Stand 2026-11-28, Wunsch Navonex.

## Wozu

Nach einem Boss-Kill soll im DPS-Meter am NexBoard direkt neben jedem Namen stehen, wie gut der Kampf war,
so wie in der Kampfansicht im Hub (#168) und im Run-Bild für Discord (#169). Vorbild ist die Plakette am
Namen in den Kampflogs von Questlog. Das Meter bleibt die Oberfläche von A2Tools, nichts wird nachgebaut.

## Ziele, Nicht-Ziele

- Ziel: Ein bis zwei Sekunden nach dem Kill steht an jeder Zeile des Meters der EU-Parse, bei
  Gildenmitgliedern zusätzlich der Gildenwert, in den Farben des Hubs.
- Ziel: Gleiche Zahlen wie später im Hub für diesen Kampf (dieselbe Rechnung, dieselben Ranglisten).
- Nicht-Ziel: Parse live während des Kampfs.
- Nicht-Ziel: eigenes Meter oder Umbau der A2Tools-Oberfläche über die Plakette hinaus.
- Anti-Ziel: Das Meter wird langsamer oder bricht, wenn der Hub nicht erreichbar ist. Ohne Hub bleibt alles
  wie heute, nur ohne Plakette.

## Ansätze

1. **Direkt nach dem Kill (gewählt).** Der Daemon schickt am Kampfende Boss und Zeilen an eine neue
   Hub-Route und bekommt die Parses zurück. Schnell, passt zum sichtbaren Kampf. Braucht eine neue Route.
2. **Nach dem Run-Upload.** Nutzt `/api/parses/device/runs/{id}`, braucht am Hub nichts Neues. Kommt aber erst,
   wenn der ganze Run hochgeladen ist, und passt dann zu keinem sichtbaren Kampf mehr. Verworfen.

Navonex hat Ansatz 1 gewählt.

## Aufbau

### Hub: `POST /api/parses/device/fight`

- Auth wie `/device/runs`: Geräte-Token (`CurrentDevice`).
- Eingabe: `{"mob": <Boss-ID wie im NexLog>, "players": [{"name", "cls", "dps"}]}`, höchstens 24 Zeilen.
- Rechnung wie `_parses` für einen getöteten Boss: Ranglisten aus `parse_boards`, Kampfkraft je Name über
  `_combat_power` (jüngste bekannte, es gibt ja noch keinen Run), Gildenwerte aus `_guild`. Die Teile von
  `_parses` so herausziehen, dass Run-Route und neue Route dieselbe Funktion für einen Boss nutzen.
- Antwort: `{"players": {"<name>": {"eu": int|null, "guild": int|null}}}`, wie `BossParse`.
- Nichts wird gespeichert. Nur lesend, kein Eintrag in der Datenbank.

### Daemon

- Neuer `fight_listener` in `hub.py` neben `on_fight`: nur wenn das NexBoard gekoppelt ist, der Kampf ein
  Boss war und getötet wurde (HP 0). Boss-ID aus derselben Quelle, die `runs.py` für den NexLog nimmt.
- Ein Aufruf je Kill, Zeitlimit 3 s, Fehler nur ins Log. Ergebnis als State-Wert `dps_parses`
  (`{"target_id", "players": {name: [eu, guild]}}`), der beim nächsten Kampfbeginn geleert wird.

### Overlay (A2Tools-Meter, `web/overlay/widgets/meter.js`)

- Hört zusätzlich auf `dps_parses`. Hängt an jede Zeile, deren Name in der Antwort steht, eine kleine
  Plakette hinter den Namen, im selben Verfahren wie der Namenseffekt (`markOwnRow`, MutationObserver, weil
  A2Tools Zeilen neu zeichnet). Stil in einer eigenen Style-Ebene im iframe, wie `effects.css`.
- Inhalt: EU-Zahl, bei Gildenmitgliedern dahinter der Gildenwert klein. Farben nach den Stufen des Hubs
  (`RatingBadge`), damit Hub, Discord-Bild und Meter gleich aussehen.
- Weg, sobald ein neuer Kampf beginnt oder A2Tools die Zeilen leert.

## Was der Builder entscheidet

- Genaue Selektoren in der A2Tools-Zeile für die Plakette, solange sie neben dem Namen steht.
- Ob der Gildenwert als zweite Zahl oder als Ring um die Plakette erscheint.
- Tests: Hub-Route mit Testdaten wie die vorhandenen Parse-Tests, Daemon-Listener mit nachgebautem Hub.
