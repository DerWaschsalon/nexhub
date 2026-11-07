/* Widgets der A2Tools-Plugins auf der Overlay-Fläche. Der Stand kommt vom Daemon (plugins.py, Ereignis
 * „plugin-widgets“). Jedes Widget ist die unveränderte plugin-widget.html in einem iframe, darin sein
 * Sandbox-iframe. Klicks: gesperrt keine, sonst die vom Plugin genannten Flächen, sonst das ganze Widget
 * (wie widget_click_through im Original). */
"use strict";

const pluginWidgets = new Map(); // Kennung → {el, state}
// Gehen im Radar-Widget auf (radar.js): die Karte zeichnet es selbst, die Würfelkarte steht über den Reitern
const RADAR_KARTE = "widget:pet-souls:map";
const RADAR_WUERFEL = "widget:dice-rolls:card";

function pluginInvoke(cmd, args = {}) {
  return fetch("/api/a2/invoke", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd, args }),
  }).then((r) => r.json());
}

function pluginPlace(entry) {
  const { el, state } = entry;
  if (!el) return;
  if (state.label === RADAR_WUERFEL) {
    el.style.height = `${state.height}px`;
    el.hidden = !state.open;
    return;
  }
  el.style.left = `${state.x}px`;
  el.style.top = `${state.y}px`;
  el.style.width = `${state.width}px`;
  el.style.height = `${state.height}px`;
  el.hidden = !state.open;
}

function pluginSync(list) {
  if (!Array.isArray(list)) return;
  const seen = new Set();
  for (const state of list) {
    seen.add(state.label);
    let entry = pluginWidgets.get(state.label);
    if (!entry && state.label === RADAR_KARTE) {
      entry = { el: null, state };
      pluginWidgets.set(state.label, entry);
      szeneAntwort({ hello: true });
    } else if (!entry) {
      const el = document.createElement("iframe");
      el.className = "plugin-widget";
      el.setAttribute("allowtransparency", "true");
      el.src = `/plugin-widget.html?plugin=${encodeURIComponent(state.plugin)}&widget=${encodeURIComponent(state.name)}`;
      if (state.label === RADAR_WUERFEL) document.getElementById("wuerfel-live").append(el);
      else document.body.append(el);
      entry = { el, state };
      pluginWidgets.set(state.label, entry);
    }
    // Während des Ziehens bestimmt die Maus den Platz
    const moving = pluginDrag && pluginDrag.label === state.label;
    entry.state = moving ? { ...state, x: entry.state.x, y: entry.state.y } : state;
    pluginPlace(entry);
  }
  for (const [label, entry] of pluginWidgets) {
    if (!seen.has(label)) {
      entry.el?.remove();
      pluginWidgets.delete(label);
    }
  }
  regionsSoon();
}

/* Klickbare Flächen, für regions() in overlay.js */
function pluginRegions() {
  const out = [];
  for (const { state } of pluginWidgets.values()) {
    if (!state.open || state.locked || state.label === RADAR_KARTE || state.label === RADAR_WUERFEL) continue;
    if (Array.isArray(state.areas)) {
      for (const [x, y, width, height] of state.areas) {
        out.push([Math.floor(state.x + x), Math.floor(state.y + y), Math.ceil(width), Math.ceil(height)]);
      }
    } else {
      out.push([state.x, state.y, Math.ceil(state.width), Math.ceil(state.height)]);
    }
  }
  return out;
}

/* Ziehen: Die Bewegungen liest das Overlay-Programm an der Fläche mit (LayerHost.watchPointer) */
let pluginDrag = null;

function pluginWidgetDrag(label) {
  const entry = pluginWidgets.get(label);
  if (!entry || entry.state.locked || !bridge || pluginDrag || label === RADAR_WUERFEL) return;
  pluginDrag = { label, last: null };
  bridge.watchPointer();
}

function pluginPointerMoved(x, y) {
  if (!pluginDrag) return;
  const entry = pluginWidgets.get(pluginDrag.label);
  if (entry && pluginDrag.last) {
    entry.state.x = Math.round(entry.state.x + x - pluginDrag.last[0]);
    entry.state.y = Math.round(entry.state.y + y - pluginDrag.last[1]);
    pluginPlace(entry);
  }
  pluginDrag.last = [x, y];
}

function pluginPointerReleased() {
  if (!pluginDrag) return;
  const entry = pluginWidgets.get(pluginDrag.label);
  const label = pluginDrag.label;
  pluginDrag = null;
  if (entry) pluginInvoke("plugin_widget_moved", { label, x: entry.state.x, y: entry.state.y }).catch(() => {});
  regionsSoon();
}

function pluginScreen() {
  pluginInvoke("plugin_overlay_screen", { width: innerWidth, height: innerHeight }).catch(() => {});
}

function pluginsStart() {
  pluginScreen();
  addEventListener("resize", pluginScreen);
  pluginInvoke("plugin_widgets_state").then((r) => pluginSync(r.result)).catch(() => {});
  pluginInvoke("plugin_embedded").then((r) => eingebetteteLaden(r.result || [])).catch(() => {});
  if (bridge) {
    bridge.pointerMoved.connect(pluginPointerMoved);
    bridge.pointerReleased.connect(pluginPointerReleased);
  }
  const onText = (text) => {
    try {
      const m = JSON.parse(text);
      if (m.event === "plugin-widgets") pluginSync(m.payload);
      else if (m.event === "plugin-event" && m.payload?.__window === RADAR_KARTE && m.payload.event === "widget") karteSzene(m.payload.data);
      else if (m.event === "radar-pet-art") petArt(m.payload?.art);
      else if (m.event === "plugin-embed") {
        pluginInvoke("plugin_embedded").then((r) => eingebetteteLaden(r.result || []));
        karteNachInstallation(); // beim allerersten Start kommt der Tracker erst jetzt an
        if (m.payload?.shown) reiterZeigen(EINGEBETTET[m.payload.plugin]);
      }
    } catch {}
  };
  try {
    const worker = new SharedWorker("/__deckbar__/a2events.js", { name: "a2-events" });
    worker.port.onmessage = (e) => onText(e.data);
    worker.port.start();
  } catch {
    new EventSource("/api/a2/events").onmessage = (e) => onText(e.data);
  }
}
