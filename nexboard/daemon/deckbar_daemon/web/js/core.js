/* Kern der Web-UI: DOM-Helfer, API, Live-Verbindung (Store + Ereignisse), Bausteine. Kein
   Framework, keine Build-Stufe: ES-Module direkt aus /static/js/. */

export const $ = (id, root = document) => root.querySelector(`#${id}`);

/** el("div", {class, text, onclick, …}, ...kinder) */
export function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else if (k === "text") e.textContent = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value" && "value" in e) e.value = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}

/** Inhalt ersetzen; null/false fallen weg (replaceChildren würde „null“ als Text einsetzen). */
export const fill = (box, ...kids) => box.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false));

/* ---------------------------------------------------------------- Icons */
const ICONS = { ui: {}, deck: {} };
export async function loadIcons() {
  const [ui, deck] = await Promise.all([fetch("/static/ui-icons.json").then((r) => r.json()), fetch("/static/icons.json").then((r) => r.json())]);
  ICONS.ui = ui;
  ICONS.deck = deck;
  await document.fonts.load('20px "mdi"').catch(() => {});
}
export const deckIcons = () => ICONS.deck;
/** Zeichen eines MDI-Icons (Web-UI-Liste oder Kachel-Liste). */
export const glyph = (name) => {
  const cp = ICONS.ui[name] ?? ICONS.deck[name];
  return cp ? String.fromCodePoint(cp) : "";
};
export const icon = (name, cls = "") => el("span", { class: `ic ${cls}`.trim(), "aria-hidden": "true", text: glyph(name) });

/* ---------------------------------------------------------------- API */
export async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let r;
  try {
    r = await fetch(path, opts);
  } catch {
    throw new Error("Daemon nicht erreichbar");
  }
  let data = {};
  try { data = await r.json(); } catch { /* leere Antwort */ }
  if (!r.ok) throw new Error(data.error || `Fehler ${r.status}`);
  return data;
}

/* ---------------------------------------------------------------- Store und Live-Verbindung */
export const S = {
  online: false,
  modules: null, // {categories, modules:[…]}
  layout: null,
  layoutError: null,
  state: {},
  devices: [],
  status: {},
  dps: null,
  runs: null,
  updates: null,
  bot: null,
  hub: null,
  overlay: null,
  settings: null,
};
const listeners = new Map();

export function on(type, fn) {
  if (!listeners.has(type)) listeners.set(type, new Set());
  listeners.get(type).add(fn);
  return () => listeners.get(type)?.delete(fn);
}
export function emit(type, data) {
  for (const fn of [...(listeners.get(type) || [])]) {
    try { fn(data); } catch (e) { console.error(`Listener ${type}`, e); }
  }
}

let ws = null;
export function connectLive() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/live`);
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    switch (msg.type) {
      case "hello":
        Object.assign(S, {
          online: true, modules: msg.modules, state: msg.state, devices: msg.devices, status: msg.status,
          dps: msg.dps, runs: msg.runs, updates: msg.updates, bot: msg.bot, hub: msg.hub, overlay: msg.overlay, settings: msg.settings,
          layoutError: msg.error,
        });
        emit("hello", msg);
        emit("layout", { layout: msg.layout, initial: true });
        emit("online", true);
        break;
      case "state":
        Object.assign(S.state, msg.values);
        emit("state", msg.values);
        break;
      case "devices": S.devices = msg.devices; emit("devices", msg.devices); break;
      case "layout": S.layoutError = null; emit("layout", { layout: msg.layout }); break;
      case "layout_error": S.layoutError = `layout.yaml: ${msg.error}`; emit("layout_error", msg.error); break;
      case "dps": S.dps = msg.dps; emit("dps", msg.dps); break;
      case "runs": S.runs = msg.runs; emit("runs", msg.runs); break;
      case "updates": S.updates = msg.updates; emit("updates", msg.updates); break;
      case "bot": S.bot = msg.bot; emit("bot", msg.bot); break;
      case "hub": S.hub = msg.hub; emit("hub", msg.hub); break;
      case "overlay": S.overlay = msg.overlay; emit("overlay", msg.overlay); break;
      case "modules": S.modules = msg.modules; emit("modules", msg.modules); break;
      case "settings": S.settings = msg.settings; emit("settings", msg.settings); break;
      case "background": emit("background", msg.id); break;
      case "error": toast(msg.error, true); break;
      default: break;
    }
  };
  ws.onclose = () => {
    if (S.online) {
      S.online = false;
      S.devices = [];
      emit("online", false);
    }
    setTimeout(connectLive, 1500);
  };
}
export function sendLive(obj) {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

/* ---------------------------------------------------------------- Module */
export const mod = (id) => S.modules?.modules.find((m) => m.id === id);
export const modOn = (id) => !!mod(id)?.enabled;
export async function setModule(id, enabled) {
  const res = await api("PUT", `/api/modules/${encodeURIComponent(id)}`, { enabled });
  S.modules = { categories: res.categories, modules: res.modules };
  emit("modules", S.modules);
  const names = res.changed.map((c) => mod(c)?.name || c);
  if (names.length) toast(`${enabled ? "Eingeschaltet" : "Ausgeschaltet"}: ${names.join(", ")}`);
  return res;
}
// Farbverlauf je Modul (Icon-Kachel)
const COLORS = {
  deck: ["#5ac8fa", "#3d7bff"],
  "aion2.dps": ["#ff7a45", "#ff3d6e"],
  "aion2.overlay": ["#8f7cff", "#4f6bff"],
  "aion2.runs": ["#ffc93d", "#ff8a1f"],
  "discord.bot": ["#7c8cff", "#5865f2"],
  updates: ["#34d17a", "#13a3a0"],
  system: ["#9aa4bf", "#5d6782"],
};
export function modIcon(m, cls = "") {
  const [c1, c2] = COLORS[m.id] || COLORS.system;
  const e = el("span", { class: `mod-icon ${cls}`.trim(), style: `--c1:${c1};--c2:${c2}` }, icon(m.icon));
  return e;
}

/* ---------------------------------------------------------------- Rückmeldungen */
export function toast(text, err = false) {
  const box = document.getElementById("toasts");
  if (!box || !text) return;
  const t = el("div", { class: `toast glass ${err ? "err" : ""}`, role: err ? "alert" : "status" }, icon(err ? "alert-circle" : "check-circle"), el("span", { text }));
  box.append(t);
  setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; }, err ? 6000 : 2800);
  setTimeout(() => t.remove(), err ? 6400 : 3200);
}

export function setSaveState(text, err = false) {
  const s = document.getElementById("save-state");
  if (!s) return;
  s.textContent = text || "";
  s.classList.toggle("err", !!err);
}

/* ---------------------------------------------------------------- Bausteine */
export function sw(checked, onChange, attrs = {}) {
  const input = el("input", { type: "checkbox", role: "switch", ...attrs });
  input.checked = !!checked;
  input.addEventListener("change", () => onChange(input.checked, input));
  return el("label", { class: "switch", title: attrs.title }, input, el("span"));
}

export function field(label, control, help, cls = "") {
  return el("label", { class: `field ${cls}`.trim() }, el("span", { text: label }), control, help ? el("span", { class: "help", text: help }) : null);
}

export function input(value, onChange, attrs = {}) {
  const i = el("input", attrs);
  i.value = value ?? "";
  i.addEventListener(attrs.type === "number" || attrs.lazy ? "change" : "input", () => onChange(i.value, i));
  i.removeAttribute("lazy");
  return i;
}

export function select(options, value, onChange, attrs = {}) {
  const s = el("select", attrs, Object.entries(options).map(([k, v]) => el("option", { value: k, text: v })));
  s.value = value ?? "";
  s.addEventListener("change", () => onChange(s.value, s));
  return s;
}

export function button(text, onClick, cls = "", ic = null, attrs = {}) {
  return el("button", { type: "button", class: `btn ${cls}`.trim(), onclick: onClick, ...attrs }, ic ? icon(ic) : null, text ? el("span", { text }) : null);
}

export function chip(text, kind = "") {
  return el("span", { class: `chip ${kind}`.trim() }, el("span", { class: "dot" }), text);
}

export function callout(kind, ic, content, ...actions) {
  return el("div", { class: `callout ${kind}` }, icon(ic), el("div", { class: "grow" }, content), ...actions);
}

export function card(title, sub, actions, ...body) {
  const head = title || actions
    ? el("div", { class: "card-head" }, el("div", {}, title ? el("h2", { text: title }) : null, sub ? el("div", { class: "sub", text: sub }) : null), actions ? el("div", { class: "row" }, actions) : null)
    : null;
  return el("section", { class: "card glass" }, head, ...body);
}

export function settingsRow(title, text, control) {
  return el("div", { class: "settings-row" }, el("div", { class: "txt" }, el("b", { text: title }), text ? el("span", { text }) : null), control);
}

/** Segmente: items [{id, label, icon}], aktiv, onClick(id) */
export function seg(items, active, onClick) {
  return el("div", { class: "seg", role: "tablist" }, items.map((t) =>
    el("button", { type: "button", role: "tab", class: t.id === active ? "on" : "", "aria-selected": t.id === active ? "true" : "false", onclick: () => onClick(t.id) },
      t.icon ? icon(t.icon) : null, t.label)));
}

export function debounce(fn, ms) {
  let t = 0;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  d.flush = (...a) => { clearTimeout(t); fn(...a); };
  return d;
}

/** Einstellungen eines Moduls speichern: Teil-Patch, entprellt, Ergebnis an onSaved. */
/** Höchstens einmal pro `ms` ausführen, den letzten Aufruf aber nie verlieren. `.cancel()` beim Abbau. */
export function throttle(fn, ms) {
  let last = 0, timer = 0;
  const run = () => { timer = 0; last = performance.now(); fn(); };
  const t = () => {
    if (timer) return;
    const wait = ms - (performance.now() - last);
    if (wait <= 0) run(); else timer = setTimeout(run, wait);
  };
  t.cancel = () => { clearTimeout(timer); timer = 0; };
  return t;
}

/* Kommt mit einem State-Diff etwas, das die DPS-Anzeige betrifft? */
export const dpsDiff = (v) => !!v && ("dps" in v || "dps_active" in v);

export function saver(method, path, onSaved, ms = 400, okText = "Gespeichert") {
  let pending = {};
  const run = debounce(async () => {
    const body = pending;
    pending = {};
    setSaveState("Speichere …");
    try {
      const res = await api(method, path, body);
      setSaveState(`${okText} ✓`);
      onSaved?.(res);
    } catch (e) {
      setSaveState("Nicht gespeichert", true);
      toast(e.message, true);
    }
  }, ms);
  return (patch) => { pending = deepMerge(pending, patch); run(); };
}

const isObj = (v) => v && typeof v === "object" && !Array.isArray(v);
export function deepMerge(a, b) {
  const out = { ...a };
  for (const [k, v] of Object.entries(b)) out[k] = isObj(v) && isObj(out[k]) ? deepMerge(out[k], v) : v;
  return out;
}

export function clampInt(v, lo, hi, def) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : def;
}

/* ---------------------------------------------------------------- Formate */
/** 8432 · 18,4k · 1,23M wie fmt_amount in ui.c */
export function fmtAmount(v) {
  v = Math.max(0, v || 0);
  const s = v >= 1e9 ? (v / 1e9).toFixed(2) + "G" : v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e4 ? (v / 1e3).toFixed(1) + "k" : String(Math.round(v));
  return s.replace(".", ",");
}
export const fmtTime = (s) => `${Math.floor((s || 0) / 60)}:${String(Math.round(s || 0) % 60).padStart(2, "0")}`;
export function fmtWhen(ts) {
  if (!ts) return "";
  const d = new Date(ts > 1e12 ? ts : ts * 1000);
  const today = new Date().toDateString() === d.toDateString();
  return today ? d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export const CLASS_COLORS = { gladiator: "#E8A33D", templar: "#5B8DEF", ranger: "#6CCB5F", assassin: "#B46AE6", sorcerer: "#4FC3F7", cleric: "#F4E07A", spiritmaster: "#EC7FB8", chanter: "#4DD4B0", brawler: "#F0624D" };
export const CLASS_LABELS = { gladiator: "Gladiator", templar: "Templer", assassin: "Assassine", ranger: "Waldläufer", sorcerer: "Magier", spiritmaster: "Beschwörer", cleric: "Kleriker", chanter: "Kantor", brawler: "Faustkämpfer" };
