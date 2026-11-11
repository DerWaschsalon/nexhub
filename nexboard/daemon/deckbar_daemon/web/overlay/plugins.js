/* Widgets der A2Tools-Plugins auf der Overlay-Fläche. Der Stand kommt vom Daemon (plugins.py, Ereignis
 * „plugin-widgets“). Jedes Widget ist die unveränderte plugin-widget.html in einem iframe, darin sein
 * Sandbox-iframe. Klicks: gesperrt keine, sonst die vom Plugin genannten Flächen, sonst das ganze Widget
 * (wie widget_click_through im Original). Platz und Sichtbarkeit bestimmt das Plugin selbst. */
import * as host from "./host.js";
import * as stage from "./stage.js";

const frames = new Map(); // Kennung → {el, state}
let drag = null; // {label, last}: Widget, das gerade der Maus folgt

function invoke(cmd, args = {}) {
  return fetch("/api/a2/invoke", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd, args }),
  }).then((r) => r.json());
}

function place({ el, state }) {
  el.style.left = `${state.x}px`;
  el.style.top = `${state.y}px`;
  el.style.width = `${state.width}px`;
  el.style.height = `${state.height}px`;
  el.hidden = !state.open;
}

function createFrame(state) {
  const el = document.createElement("iframe");
  el.className = "plugin-widget";
  el.setAttribute("allowtransparency", "true");
  el.src = `/plugin-widget.html?plugin=${encodeURIComponent(state.plugin)}&widget=${encodeURIComponent(state.name)}`;
  document.body.append(el);
  return { el, state };
}

/** Stand vom Daemon: fehlende Widgets anlegen, alle an ihren Platz, geschlossene entfernen. */
export function sync(list) {
  if (!Array.isArray(list)) return;
  const seen = new Set();
  for (const state of list) {
    seen.add(state.label);
    const entry = frames.get(state.label) || createFrame(state);
    frames.set(state.label, entry);
    // Während des Ziehens bestimmt die Maus den Platz
    entry.state = drag?.label === state.label ? { ...state, x: entry.state.x, y: entry.state.y } : state;
    place(entry);
  }
  for (const [label, entry] of frames) {
    if (seen.has(label)) continue;
    entry.el.remove();
    frames.delete(label);
  }
  stage.regionsSoon();
}

function regions() {
  const click = [];
  for (const { state } of frames.values()) {
    if (!state.open || state.locked) continue;
    if (Array.isArray(state.areas)) {
      for (const [x, y, width, height] of state.areas) {
        click.push([Math.floor(state.x + x), Math.floor(state.y + y), Math.ceil(width), Math.ceil(height)]);
      }
    } else {
      click.push([state.x, state.y, Math.ceil(state.width), Math.ceil(state.height)]);
    }
  }
  return { click, lock: [] };
}

/* Ziehen: Die Bewegungen liest das Overlay-Programm an der Fläche mit (LayerHost.watchPointer) */
function startDrag(label) {
  const entry = frames.get(label);
  if (!entry || entry.state.locked || drag) return;
  if (host.watchPointer(pointerMoved, pointerReleased)) drag = { label, last: null };
}

function pointerMoved(x, y) {
  const entry = drag && frames.get(drag.label);
  if (!drag) return;
  if (entry && drag.last) {
    entry.state.x = Math.round(entry.state.x + x - drag.last[0]);
    entry.state.y = Math.round(entry.state.y + y - drag.last[1]);
    place(entry);
  }
  drag.last = [x, y];
}

function pointerReleased() {
  if (!drag) return;
  const { label } = drag;
  const entry = frames.get(label);
  drag = null;
  if (entry) invoke("plugin_widget_moved", { label, x: entry.state.x, y: entry.state.y }).catch(() => {});
  stage.regionsSoon();
}

function reportScreen() {
  invoke("plugin_overlay_screen", { width: innerWidth, height: innerHeight }).catch(() => {});
}

export function start() {
  reportScreen();
  addEventListener("resize", reportScreen);
  stage.addRegions(regions);
  host.handle("plugin_widget_drag", (args) => { startDrag(args.label); return null; });
  // der erste Stand; danach kommt jede Änderung als Ereignis „plugin-widgets“
  invoke("plugin_widgets_state").then((r) => sync(r.result)).catch(() => {});
}
