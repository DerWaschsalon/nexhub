# NexBoard-Protokoll v1

Transport: WebSocket, Textframes, je Frame genau ein JSON-Objekt (UTF-8).
Endpunkt: `ws://<daemon>:8765/ws` (Port per Config änderbar).
Rückfall ohne WLAN: dieselben Nachrichten zeilenweise über USB mit Präfix `@@`, die USB-Brücke
des Daemons reicht sie an `/ws` weiter (Ablauf und Steuerzeilen im README, „Verbindung“).
Maschinenlesbares Schema: [`protocol.schema.json`](protocol.schema.json).

Jede Nachricht hat die Felder

| Feld   | Typ     | Bedeutung                                   |
|--------|---------|---------------------------------------------|
| `v`    | integer | Protokollversion, aktuell `1`               |
| `type` | string  | Nachrichtentyp (siehe unten)                |

Unbekannte Felder werden ignoriert (Vorwärtskompatibilität). Eine Gegenstelle mit
anderem `v` wird mit `error`/`version` abgelehnt.

## Grundidee

Das Gerät ist „dumm“. Es kennt **keine Aktionen**, sondern nur Layout und State.
Tippt man einen Button an, meldet das Gerät die `item`-ID. Welche Aktion dahinter
steckt, weiß nur der Daemon. Deshalb enthält das Layout, das zum Gerät geht, keine
Befehle, Links oder Hotkeys.

## Ablauf

```
Gerät                                Daemon
  |  ---- hello (token, device) ---->  |
  |  <--- welcome ------------------   |   (oder error + close)
  |  <--- layout -------------------   |   (entfällt, wenn hash == layout_hash)
  |  <--- state (full: true) -------   |
  |           ...                       |
  |  ---- event -------------------->  |
  |  <--- state (Diff) -------------   |
  |  <--- ping ---------------------   |   alle `heartbeat` s
  |  ---- pong --------------------->  |
```

- Das Gerät muss `hello` innerhalb von 5 s nach dem Verbindungsaufbau schicken,
  sonst trennt der Daemon.
- Der Daemon schickt alle `heartbeat` Sekunden (Standard 5) ein `ping`.
  Erhält das Gerät 3 × `heartbeat` lang **gar keine** Nachricht, baut es die
  Verbindung neu auf. Erhält der Daemon 3 × `heartbeat` lang kein `pong`, trennt er.
- Ändert sich die Konfiguration, schickt der Daemon jederzeit ein neues `layout`.

## Gerät → Daemon

### `hello`

```json
{"v":1,"type":"hello","token":"…","layout_hash":"3f2a…","page":"main","bg_id":"9c01…",
 "caps":["bin"],
 "device":{"id":"deckbar-a1b2c3","model":"waveshare-s3-lcd-3.49","fw":"0.1.0",
           "width":640,"height":172,"sim":false}}
```

`layout_hash` ist optional und gibt den Hash des gecachten Layouts an. Stimmt er,
lässt der Daemon das `layout` weg. `page` (optional) ist die gerade angezeigte Seite.
`bg_id` (optional) ist der Hintergrund, den das Gerät zeigt; das Gerät speichert ihn im Flash,
nach einem Neustart muss er also nicht neu übertragen werden. `caps` (optional): `bin` = das
Gerät nimmt Bildteile als Binärframes an (siehe `art`). Die USB-Brücke streicht `bin`, über
USB gibt es nur Textzeilen.

### `event`

| `event`         | Pflichtfelder     | Bedeutung                                              |
|-----------------|-------------------|--------------------------------------------------------|
| `button_press`  | `item`            | kurzer Tap auf button/toggle/media                     |
| `long_press`    | `item`            | ≥ 600 ms gehalten (danach kommt kein `button_press`)   |
| `slider_change` | `item`, `value`   | Slider bewegt; `final: true` beim Loslassen            |
| `page_change`   | `page`            | Gerät hat die Seite gewechselt (Wischen / Nav-Button)  |

Optional ist `part`, damit Kacheln mit mehreren Schaltflächen unterscheiden können,
welche gemeint war (für `media`: `prev` | `toggle` | `next`).

```json
{"v":1,"type":"event","event":"slider_change","item":"vol","value":42,"final":false}
{"v":1,"type":"event","event":"button_press","item":"np","part":"next"}
```

Slider-Events drosselt das Gerät auf höchstens 20 pro Sekunde. Das letzte Event
(`final: true`) wird immer gesendet.

### `art_request`

`{"v":1,"type":"art_request","size":88,"have":"3f2a9c01b2d4"}`

Kantenlänge (8–160 px) des Covers, das das Gerät für seine größte `media`-Kachel braucht.
Das Gerät schickt die Nachricht nach `welcome` und nach jedem neuen Layout. Der Daemon
antwortet sofort mit dem aktuellen Cover und schickt danach jedes neue Cover unaufgefordert.
`have` (optional): dieses Cover in dieser Größe hat das Gerät schon; ist es noch aktuell,
schickt der Daemon nichts.

### `pong`

`{"v":1,"type":"pong","t":<t aus dem ping>}`

## Daemon → Gerät

### `welcome`

`{"v":1,"type":"welcome","server":{"name":"NexBoard","version":"0.1.0"},"heartbeat":5}`

### `error`

`{"v":1,"type":"error","code":"auth"|"version"|"bad_request"|"disabled","message":"…"}`.
Bei `auth` und `version` schließt der Daemon danach die Verbindung, ebenso bei `disabled`
(Modul „Touch-Leiste“ in der Web-UI ausgeschaltet, Schließcode 4003). Das Gerät versucht es
danach wie gewohnt in Abständen erneut.

### `layout`

```json
{"v":1,"type":"layout","hash":"3f2a…",
 "theme":{"accent":"#5AC8FA","background":"default"},
 "pages":[
   {"id":"main","name":"Audio","cols":6,"rows":2,"items":[
     {"id":"mic","type":"toggle","label":"Mikro","icon":"microphone",
      "icon_on":"microphone-off","bind":"mic_muted","style":"danger","w":1,"h":1},
     {"id":"vol","type":"slider","label":"Lautstärke","icon":"volume-high",
      "bind":"out_volume","mute_bind":"out_muted","min":0,"max":100,"w":2,"h":1},
     {"id":"np","type":"media","w":2,"h":2},
     {"id":"yt","type":"button","label":"YouTube","icon":"youtube","style":"default"},
     {"id":"p2","type":"button","label":"Mehr","icon":"chevron-right","nav":"page2"}
   ]}]}
```

**Raster:** Jede Seite ist ein Raster aus `cols` × `rows` Zellen (1–8 × 1–3).
Items belegen `w` × `h` Zellen (Standard 1 × 1) und werden in Listenreihenfolge
zeilenweise in die erste freie Lücke gesetzt (wie CSS-Grid mit `auto-flow: row dense`).
Items, die nicht mehr passen, werden nicht angezeigt.

**Item-Typen**

| `type`   | Anzeige                                           | Events                          |
|----------|---------------------------------------------------|---------------------------------|
| `button` | Icon + Label                                      | `button_press`, `long_press`    |
| `toggle` | wie button; aktiv, wenn `state[bind]` truthy ist  | `button_press`, `long_press`    |
| `slider` | Kachel füllt sich mit Wert; relatives Ziehen      | `slider_change`, `long_press`   |
| `media`  | Titel/Interpret aus `state.track`, ab h ≥ 2 mit ⏮ ⏯ ⏭ | `button_press` (+ `part`)    |
| `dps`    | DPS-Rangliste aus `state.dps` (AION 2), Balken in Klassenfarbe | –                |

**Felder**

| Feld        | Typen            | Bedeutung                                                 |
|-------------|------------------|-----------------------------------------------------------|
| `label`     | alle             | max. 24 Zeichen                                           |
| `icon`      | alle             | Name aus [`icons.md`](icons.md) (Material Design Icons)   |
| `icon_on`   | toggle, slider   | Icon im aktiven Zustand bzw. bei `mute_bind` = true       |
| `style`     | alle             | `default`, `accent`, `danger`, `success`, `warning`       |
| `bind`      | toggle, slider   | State-Schlüssel                                           |
| `mute_bind` | slider           | State-Schlüssel, der den Slider als „stumm“ darstellt     |
| `min`,`max` | slider           | Wertebereich (Standard 0–100)                             |
| `nav`       | button           | Seiten-ID; das Gerät wechselt **lokal** und sendet `page_change` |
| `players`   | dps              | Anzahl Zeilen (1–8, Standard 5)                           |
| `extra`     | dps              | Zusatzwert neben der DPS-Zahl: `pct` (Anteil, Standard), `dmg` (Gesamtschaden), `none` |

Beim Toggle bestimmt `style`, wie der **aktive** Zustand aussieht. Ein gemutetes
Mikro ist also `style: danger` + `bind: mic_muted`.

Limits: max. 8 Seiten, max. 24 Items pro Seite, Nachricht max. 16 KiB.

### `state`

```json
{"v":1,"type":"state","full":true,"values":{
  "out_volume":42,"out_muted":false,"mic_volume":80,"mic_muted":true,
  "playing":true,"track":{"title":"Song","artist":"Band","player":"spotify"}}}
```

Ist `full` = `false`, enthält `values` nur geänderte Schlüssel. Sie werden in den
bestehenden State übernommen. `track: null` bedeutet, dass kein Player aktiv ist.
Eigene Schlüssel sind erlaubt (z. B. aus Shell-Statusbefehlen) und lassen sich über
`bind` nutzen.

| Schlüssel     | Typ          | Quelle                                  |
|---------------|--------------|-----------------------------------------|
| `out_volume`  | int 0–150    | `wpctl get-volume @DEFAULT_AUDIO_SINK@` |
| `out_muted`   | bool         | dito                                    |
| `mic_volume`  | int 0–150    | `@DEFAULT_AUDIO_SOURCE@`                |
| `mic_muted`   | bool         | dito                                    |
| `playing`     | bool         | `playerctl` (Status == Playing)         |
| `track`       | object\|null | `playerctl` Metadaten                   |
| `dps`         | object\|null | A2Tools DPS Meter (Stream-Overlay), siehe unten |
| `dps_active`  | bool         | gerade Schaden im Kampf                 |

`dps` ist `null`, solange keine Verbindung zum Meter besteht, sonst:

```json
{"target":"Bossname","time":83,"hp":42.5,
 "rows":[{"name":"Aria","cls":"spiritmaster","dps":18432,"dmg":1529856,"pct":31.2,"you":true}]}
```

`time` = Kampfdauer in s, `hp` = Rest-HP des Bosses in % (oder `null`), `rows` absteigend
nach DPS (höchstens 8; ans Gerät nur so viele, wie seine DPS-Kachel zeigt). Ans Gerät geht
`dps` höchstens einmal pro Sekunde und nur, solange die angezeigte Seite eine DPS-Kachel hat
(beim Wechsel dorthin sofort). `cls` ist einer von `gladiator`, `templar`, `ranger`, `assassin`,
`sorcerer`, `cleric`, `spiritmaster`, `chanter`, `brawler` oder `null` (noch unbekannt).

### `art`

```json
{"v":1,"type":"art","id":"3f2a9c01b2d4","w":88,"h":88,"y":0,"rows":34,"data":"<base64>"}
{"v":1,"type":"art","id":""}
```

Cover des aktuellen Titels (`mpris:artUrl`), mittig quadratisch zugeschnitten und genau auf
`size` aus `art_request` skaliert. `data` ist RGB565 little-endian (LVGL-Format), Zeilen
`y` bis `y + rows - 1`. Ein Bild kommt in mehreren Nachrichten zu je ≤ 2000 Byte Rohdaten,
der Reihe nach von `y = 0` an. Das Gerät zeigt das Bild erst, wenn alle Zeilen da sind.
`id: ""` heißt: kein Cover. Die URL selbst (`art_url`) bleibt im Daemon und wird nicht ans
Gerät geschickt. Der Hintergrund (`bg`, 640×172) kommt genauso.

**Binärframes** (Gerät mit `caps: ["bin"]`): Bildteile statt als JSON als WebSocket-Binärframe,
ohne base64 und mit bis zu 12000 Byte Rohdaten (Firmware: höchstens 15 KB pro Nachricht):

| Byte | Inhalt |
|---|---|
| 0–1 | `DB` |
| 2 | `a` = Cover, `b` = Hintergrund |
| 3–18 | `id`, mit Nullbytes aufgefüllt |
| 19–26 | `w`, `h`, `y`, `rows`, je uint16 little-endian |
| 27– | `rows × w × 2` Byte RGB565 |

`id: ""` (kein Bild) bleibt eine JSON-Nachricht.

### `ping`

`{"v":1,"type":"ping","t":1727712000123}`

### `goto`

`{"v":1,"type":"goto","page":"aion"}`

Das Gerät wechselt auf die Seite (wie ein `nav`-Button) und meldet das per `page_change`.
Der Daemon nutzt das für den automatischen Wechsel zur DPS-Seite bei Kampfbeginn.

## Sicherheit

- Das Token steht nur in der gitignorierten Konfiguration (Daemon:
  `~/.config/deckbar/config.yaml`, Firmware: `firmware/include/secrets.h`).
- Das Token schützt nur vor versehentlichen Clients im LAN. Der Transport ist
  unverschlüsselt (kein TLS).
- Die Konfigurations-UI und `/api/*` antworten nur Anfragen von Loopback-Adressen.
