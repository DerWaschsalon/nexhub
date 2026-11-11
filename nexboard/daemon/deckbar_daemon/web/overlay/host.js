/* Verbindung zum Overlay-Programm (QWebChannel-Objekt „bridge“, overlay/Overlay.qml). Im Browser fehlt
 * sie: dann läuft die Seite zum Ausprobieren ohne Fenster-Befehle.
 *
 * Die Oberfläche des A2Tools-Meters und die Plugin-Seiten schicken ihre Fenster-Befehle über
 * web/a2shim.js an window.__DECKBAR_OVERLAY__.hostCall. Was die Seite selbst beantwortet, meldet der
 * zuständige Teil mit handle() an; alles andere geht ans Programm. */

let bridge = null;
let modeListener = () => {};
const handlers = new Map(); // Befehl → Funktion(args)

export const hasBridge = () => !!bridge;

/** Verbinden; liefert den Startmodus (vom Programm, im Browser aus ?mode=). */
export function connect() {
  const urlMode = new URLSearchParams(location.search).get("mode") || "click";
  if (typeof QWebChannel === "undefined" || !window.qt?.webChannelTransport) return Promise.resolve(urlMode);
  return new Promise((resolve) => {
    new QWebChannel(window.qt.webChannelTransport, (channel) => {
      bridge = channel.objects.bridge;
      bridge.modeChanged.connect(() => modeListener(bridge.mode));
      resolve(bridge.mode);
    });
  });
}

/** Die Seite ist bereit: erst jetzt zeigt das Programm die Fläche. */
export function ready() { bridge?.ready(); }

export function onMode(fn) { modeListener = fn; }
export function requestMode(mode) { if (bridge) bridge.requestMode(mode); else modeListener(mode); }
export function finishEdit() { if (bridge) bridge.finishEdit(); else modeListener("click"); }

/** Eingabe-Regionen ans Programm (Wayland-Commit). */
export function setRegions(json) { bridge?.setRegions(json); }

export function log(text) {
  if (bridge) bridge.log(String(text));
  else console.log(text);
}

/** Mausbewegungen der ganzen Fläche mitlesen, bis die Taste losgelassen wird (Plugin-Widget ziehen). */
export function watchPointer(onMove, onRelease) {
  if (!bridge) return false;
  if (!watchPointer.connected) {
    bridge.pointerMoved.connect((x, y) => watchPointer.onMove?.(x, y));
    bridge.pointerReleased.connect(() => watchPointer.onRelease?.());
    watchPointer.connected = true;
  }
  Object.assign(watchPointer, { onMove, onRelease });
  bridge.watchPointer();
  return true;
}

/** Befehl ans Overlay-Programm. Ohne Programm (Browser) gibt es nur harmlose Antworten. */
export function forward(cmd, args) {
  if (!bridge) {
    if (cmd === "request_details_view") return Promise.reject("kein Overlay"); // Meter zeigt Details dann selbst
    if (cmd === "open_url") return Promise.resolve(void window.open(args.url, "_blank"));
    if (cmd === "list_monitors") return Promise.resolve([]);
    return Promise.resolve(null);
  }
  return new Promise((resolve, reject) => {
    bridge.call(cmd, JSON.stringify(args || {}), (text) => {
      let res;
      try { res = JSON.parse(text); } catch { return reject("ungültige Antwort"); }
      if (res && "error" in res) reject(res.error);
      else resolve(res ? res.result : null);
    });
  });
}

/** Einen Fenster-Befehl selbst beantworten statt ihn ans Programm zu geben. */
export function handle(cmd, fn) { handlers.set(cmd, fn); }

window.__DECKBAR_OVERLAY__ = {
  hostCall(cmd, args = {}) {
    const fn = handlers.get(cmd);
    return fn ? Promise.resolve(fn(args)) : forward(cmd, args);
  },
};
