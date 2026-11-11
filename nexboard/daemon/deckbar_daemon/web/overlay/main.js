/* NexBoard-Overlay: Widgets über dem Spiel. Läuft im Overlay-Programm (layer-shell-Fläche, Qt
 * WebEngine) und zum Ausprobieren auch im Browser (http://127.0.0.1:<Port+1>/__deckbar__/overlay/,
 * mit ?mode=edit im Bearbeiten-Modus).
 *
 * Aufbau:  host.js      Verbindung zum Overlay-Programm und Fenster-Befehle
 *          layout.js    Positionen und Sichtbarkeit (laden, speichern)
 *          stage.js     Widgets einhängen, platzieren, Ereignisse verteilen, Klickflächen
 *          edit.js      Bearbeiten-Modus
 *          plugins.js   Widgets der A2Tools-Plugins
 *          widgets/     je Widget eine Datei, angemeldet vom Modul im Daemon
 * Daten:   eine Verbindung, GET /api/overlay/events (Server-Sent Events) */
import * as edit from "./edit.js";
import * as host from "./host.js";
import * as layout from "./layout.js";
import * as plugins from "./plugins.js";
import * as stage from "./stage.js";
import { $ } from "./util.js";

const OFFLINE_AFTER_MS = 4000;

// Was der Kern selbst braucht; alles andere geht an die Widgets (stage.dispatch)
const CORE_EVENTS = {
  widgets: (specs) => stage.sync(specs),
  layout: (next) => layout.apply(next),
  veil: (veil) => stage.setVeil(veil.hidden),
  "plugin-widgets": (list) => plugins.sync(list),
};

function connect() {
  const source = new EventSource("/api/overlay/events");
  source.onmessage = (e) => {
    const { event, payload } = JSON.parse(e.data);
    if (event in CORE_EVENTS) CORE_EVENTS[event](payload);
    else stage.dispatch(event, payload);
  };
  let offlineTimer = 0;
  source.onopen = () => {
    clearTimeout(offlineTimer);
    $("offline").hidden = true;
  };
  source.onerror = () => {
    clearTimeout(offlineTimer);
    offlineTimer = setTimeout(() => { $("offline").hidden = source.readyState === EventSource.OPEN; }, OFFLINE_AFTER_MS);
  };
}

async function start() {
  host.onMode(stage.setMode);
  stage.setMode(await host.connect());
  edit.start();
  plugins.start();
  connect();
  new ResizeObserver(stage.regionsSoon).observe(document.body);
  addEventListener("resize", stage.placeAll);
  host.ready();
}

start();
