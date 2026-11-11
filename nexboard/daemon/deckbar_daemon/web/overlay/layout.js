/* Layout der Widgets: Stand vom Daemon (overlay_layout.py), eigene Änderungen gebündelt speichern.
 * Solange gezogen oder gespeichert wird, wartet ein Stand vom Daemon: sonst käme das Echo einer
 * früheren Speicherung dazwischen und das Widget spränge zurück. */
import { log } from "./host.js";

const SAVE_DELAY_MS = 350;
const SAVED_KEYS = ["enabled", "x", "y", "scale", "width", "height"];

let layout = null;
let holds = 0;
let deferred = null;
let saveTimer = 0;
const listeners = [];

export const current = () => layout;
export const cfg = (id) => layout?.widgets[id];

/** fn(layout) nach jedem übernommenen Stand. */
export function onChange(fn) { listeners.push(fn); }

export function hold() { holds += 1; }
export function release() {
  holds -= 1;
  flush();
}

/** Stand vom Daemon übernehmen, sobald nichts Eigenes mehr in Arbeit ist. */
export function apply(next) {
  if (layout && (holds || saveTimer)) {
    deferred = next;
    return;
  }
  layout = next;
  for (const fn of listeners) fn(layout);
}

function flush() {
  if (!deferred || holds || saveTimer) return;
  const next = deferred;
  deferred = null;
  apply(next);
}

async function put(patch) {
  const r = await fetch("/api/overlay/layout", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
  });
  return r.ok ? r.json() : null;
}

/** Positionen, Größen und Sichtbarkeit kurz nach der letzten Änderung speichern. */
export function saveSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    saveTimer = 0;
    hold();
    const widgets = {};
    for (const [id, c] of Object.entries(layout.widgets)) {
      widgets[id] = Object.fromEntries(SAVED_KEYS.map((key) => [key, c[key]]));
    }
    try {
      deferred = (await put({ widgets })) || deferred;
    } catch (e) {
      log(`Speichern fehlgeschlagen: ${e}`);
    }
    release();
  }, SAVE_DELAY_MS);
}

/** Profil wechseln: der Daemon schaltet die Widgets des Profils und schickt das Layout. */
export async function chooseProfile(name) {
  try {
    const next = await put({ profile: name });
    if (next) apply(next);
  } catch (e) {
    log(`Profilwechsel fehlgeschlagen: ${e}`);
  }
}
