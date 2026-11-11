/* Bühne der Widgets: hängt je angemeldetem Widget (Ereignis „widgets“ vom Daemon) das Modul
 * widgets/<id>.js ein, setzt es an seinen Platz, verteilt Ereignisse und nennt dem Programm die
 * Flächen, die Klicks annehmen.
 *
 * Ein Widget-Modul exportiert als default:
 *   events       Namen der Ereignisse, die es braucht, z. B. ["dps"]
 *   click        true: nimmt Klicks an (sonst gehen sie ans Spiel)
 *   hud          true: bekommt den dunklen HUD-Rahmen
 *   defaultPos() Platz [x, y], solange keiner gespeichert ist
 *   mount(el, ctx) baut das Widget in el und gibt zurück, was es davon braucht:
 *     onEvent(name, data)  ein Ereignis; nur solange das Widget eingeschaltet ist
 *     onLayout()           Layout hat sich geändert (Optionen, Größe)
 *     onMode(mode)         click, lock oder edit; im Bearbeiten-Modus zeigt es Beispieldaten
 *     regions()            eigene Klickflächen {click, lock} statt des ganzen Rechtecks
 *     destroy()            aufräumen (Timer), wenn sein Modul ausgeschaltet wird
 * ctx: id, cfg(), mode(), setIdle(bool), regionsChanged(), place(), save()
 *
 * Ein ausgeschaltetes Widget bekommt nichts; beim Einschalten folgt der letzte Stand jedes Ereignisses. */
import * as host from "./host.js";
import * as layout from "./layout.js";
import { $, rectOf } from "./util.js";

const widgets = new Map(); // id → {id, spec, def, el, instance, shown}
const lastEvent = new Map(); // Ereignis → letzter Stand
const regionProviders = []; // weitere Klickflächen (Plugin-Widgets, Bearbeiten-Knopf)
const mountListeners = [];
const syncListeners = [];
let mode = "click";
let veiled = false;

export const all = () => [...widgets.values()];
export const getMode = () => mode;
export function onMount(fn) { mountListeners.push(fn); }
/** fn() nach jeder Änderung der eingehängten Widgets. */
export function onSync(fn) { syncListeners.push(fn); }
export function addRegions(fn) { regionProviders.push(fn); }

/* ================================================================ Einhängen */
/** Liste vom Daemon: Widgets eingeschalteter Module einhängen, die anderen entfernen. */
export async function sync(specs) {
  const active = specs.filter((spec) => spec.active);
  for (const w of all()) {
    if (!active.some((spec) => spec.id === w.id)) unmount(w);
  }
  for (const spec of active) {
    if (!widgets.has(spec.id)) await mount(spec);
  }
  for (const fn of syncListeners) fn();
  regionsSoon();
}

async function mount(spec) {
  let def;
  try {
    def = (await import(`./widgets/${spec.id}.js`)).default;
  } catch (e) {
    host.log(`Widget ${spec.id} nicht geladen: ${e}`);
    return;
  }
  const el = document.createElement("section");
  el.id = `w-${spec.id}`;
  el.className = def.hud ? "widget hud" : "widget";
  el.dataset.title = spec.title;
  el.hidden = true;
  $("stage").append(el);
  const w = { id: spec.id, spec, def, el, instance: null, shown: false };
  w.instance = def.mount(el, context(w)) || {};
  widgets.set(w.id, w);
  new ResizeObserver(regionsSoon).observe(el);
  for (const fn of mountListeners) fn(w);
  w.instance.onMode?.(mode);
  if (layout.current()) w.instance.onLayout?.();
  place(w);
}

function unmount(w) {
  w.instance.destroy?.();
  w.el.remove();
  widgets.delete(w.id);
}

function context(w) {
  return {
    id: w.id,
    cfg: () => layout.cfg(w.id),
    mode: () => mode,
    setIdle(idle) {
      w.el.classList.toggle("idle", idle);
      regionsSoon();
    },
    regionsChanged: regionsSoon,
    place: () => place(w),
    save: layout.saveSoon,
  };
}

/* ================================================================ Platz */
function position(w) {
  const c = layout.cfg(w.id);
  if (c.x != null && c.y != null) return [c.x, c.y];
  return w.def.defaultPos().map(Math.round);
}

/** Gespeicherten Platz festschreiben (vor dem Ziehen: der Standardplatz hängt sonst an der Fenstergröße). */
export function pin(w) {
  const c = layout.cfg(w.id);
  [c.x, c.y] = position(w);
  return c;
}

export function place(w) {
  const c = layout.cfg(w.id);
  if (!c) return; // Layout kommt gleich
  const [x, y] = position(w);
  w.el.hidden = !c.enabled;
  w.el.style.transform = `translate(${x}px, ${y}px) scale(${c.scale || 1})`;
  w.el.style.opacity = c.opacity ?? 1;
  if (c.width) {
    w.el.style.width = `${c.width}px`;
    w.el.style.height = `${c.height}px`;
  }
  if (c.enabled && !w.shown) replay(w);
  w.shown = c.enabled;
}

export function placeAll() {
  all().forEach(place);
  regionsSoon();
}

function layoutChanged() {
  placeAll();
  for (const w of all()) w.instance.onLayout?.();
}

/* ================================================================ Ereignisse */
export function dispatch(name, data) {
  lastEvent.set(name, data);
  for (const w of all()) {
    if (w.shown && w.def.events?.includes(name)) w.instance.onEvent?.(name, data);
  }
}

function replay(w) {
  for (const name of w.def.events || []) {
    if (lastEvent.has(name)) w.instance.onEvent?.(name, lastEvent.get(name));
  }
}

/* ================================================================ Modus und Vorhang */
export function setMode(next) {
  mode = next;
  document.body.classList.toggle("edit", mode === "edit");
  document.body.dataset.mode = mode;
  applyVeil();
  for (const w of all()) w.instance.onMode?.(mode);
  regionsSoon();
}

/** Ein Modul bittet, das ganze Overlay auszublenden (Karte im Spiel offen). Nicht beim Anordnen. */
export function setVeil(hidden) {
  veiled = hidden;
  applyVeil();
  regionsSoon();
}

function applyVeil() {
  document.body.classList.toggle("veiled", veiled && mode !== "edit");
}

/* ================================================================ Eingabe-Regionen */
function regions() {
  const out = { click: [], lock: [] };
  const hidden = document.body.classList.contains("veiled");
  for (const w of all()) {
    if (hidden || w.el.hidden || w.el.classList.contains("idle")) continue;
    const own = w.instance.regions?.();
    if (own) {
      out.click.push(...own.click);
      out.lock.push(...own.lock);
    } else if (w.def.click) {
      out.click.push(rectOf(w.el));
    }
  }
  for (const provide of regionProviders) {
    const more = provide(mode);
    out.click.push(...more.click);
    out.lock.push(...more.lock);
  }
  return out;
}

let regionFrame = 0;
let regionsSent = "";
/** Flächen neu melden; ans Programm geht es nur, wenn sich etwas geändert hat. */
export function regionsSoon() {
  if (regionFrame) return;
  regionFrame = requestAnimationFrame(() => {
    regionFrame = 0;
    const text = JSON.stringify(regions());
    if (text !== regionsSent) {
      regionsSent = text;
      host.setRegions(text);
    }
  });
}

layout.onChange(layoutChanged);
