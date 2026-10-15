/* DeckBar-Overlay: Widgets über dem Spiel. Läuft im Overlay-Programm (layer-shell-Fläche, Qt
 * WebEngine) und zum Ausprobieren auch im Browser (http://127.0.0.1:<Port+1>/__deckbar__/overlay/).
 *
 * Daten:   GET /api/overlay/events (SSE: layout, dps), PUT /api/overlay/layout (Positionen, Effekt)
 * Host:    QWebChannel-Objekt „bridge“ (overlay/Overlay.qml): mode, setRegions, requestMode,
 *          finishEdit, call (Fenster-Befehle der Meter-Oberfläche)
 * Meter:   die Oberfläche des A2Tools-Meters als iframe (gleicher Ursprung). Ihr Shim
 *          (web/a2shim.js) schickt Fenster-Befehle an window.__DECKBAR_OVERLAY__.hostCall. */
"use strict";

const $ = (id) => document.getElementById(id);
const WIDGETS = [...document.querySelectorAll(".widget")];
const W = Object.fromEntries(WIDGETS.map((w) => [w.dataset.id, w]));
const GRID = 8;
const SNAP = 8;
const DEFAULT_POS = {
  meter: () => [48, Math.max(40, innerHeight - 380)],
  boss: () => [Math.round(innerWidth / 2 - 210), 72],
  timers: () => [innerWidth - 300, 160],
};

let bridge = null;
let layout = null;
let mode = new URLSearchParams(location.search).get("mode") || "click";
let dps = { dps: null, dps_active: false };
let lockRect = null; // Schloss-Knopf der Meter-Oberfläche, in iframe-Koordinaten
let dragging = false;

/* ================================================================ Layout */
const cfg = (id) => layout.widgets[id];

function pos(id) {
  const c = cfg(id);
  if (c.x != null && c.y != null) return [c.x, c.y];
  return DEFAULT_POS[id]().map(Math.round);
}

function place(w) {
  const c = cfg(w.dataset.id);
  const [x, y] = pos(w.dataset.id);
  w.hidden = !c.enabled;
  w.style.transform = `translate(${x}px, ${y}px) scale(${c.scale || 1})`;
  w.style.opacity = c.opacity ?? 1;
}

function placeAll() {
  WIDGETS.forEach(place);
  regionsSoon();
}

let saveTimer = 0;
let saving = false;
let deferred = null; // Layout vom Server, das während eigener Änderungen ankam
function saveSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    saveTimer = 0;
    saving = true;
    const widgets = {};
    for (const id of Object.keys(W)) {
      const c = cfg(id);
      widgets[id] = { enabled: c.enabled, x: c.x, y: c.y, scale: c.scale };
    }
    try {
      const r = await fetch("/api/overlay/layout", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fx: layout.fx, widgets }),
      });
      if (r.ok) deferred = await r.json();
    } catch (e) {
      log(`Speichern fehlgeschlagen: ${e}`);
    } finally {
      saving = false;
    }
    flushDeferred();
  }, 350);
}

/** Server-Stand übernehmen, sobald nichts Eigenes mehr in Arbeit ist. */
function flushDeferred() {
  if (!deferred || dragging || saving || saveTimer) return;
  const next = deferred;
  deferred = null;
  applyLayout(next);
}

function applyLayout(next) {
  const first = !layout;
  // Während Ziehen/Speichern käme sonst das Echo einer früheren Speicherung dazwischen
  if (!first && (dragging || saving || saveTimer)) { deferred = next; return; }
  layout = next;
  placeAll();
  applyFx();
  renderBoss();
  renderTimers();
  if (first || $("toggles").childElementCount === 0) buildToolbar();
  syncToolbar();
  const meter = $("meter");
  if (cfg("meter").enabled && meter.getAttribute("src") === "about:blank") meter.src = "/";
}

/* ================================================================ Eingabe-Regionen */
function rectOf(el) {
  const r = el.getBoundingClientRect();
  return [Math.floor(r.left), Math.floor(r.top), Math.ceil(r.width), Math.ceil(r.height)];
}

function regions() {
  const visible = (w) => !w.hidden && !w.classList.contains("idle");
  const click = WIDGETS.filter((w) => visible(w) && w.hasAttribute("data-click")).map(rectOf);
  let lock = [];
  if (lockRect && visible(W.meter)) {
    const r = W.meter.getBoundingClientRect();
    const s = cfg("meter").scale || 1;
    lock = [[Math.floor(r.left + lockRect.x * s), Math.floor(r.top + lockRect.y * s),
      Math.ceil(lockRect.width * s), Math.ceil(lockRect.height * s)]];
  }
  return { click, lock };
}

let regionFrame = 0;
function regionsSoon() {
  if (regionFrame) return;
  regionFrame = requestAnimationFrame(() => {
    regionFrame = 0;
    if (bridge) bridge.setRegions(JSON.stringify(regions()));
  });
}

/* ================================================================ Modus */
function setMode(m) {
  mode = m;
  document.body.classList.toggle("edit", m === "edit");
  document.body.dataset.mode = m;
  if (m !== "edit") hideGuides();
  renderBoss();
  regionsSoon();
}

function requestMode(m) {
  if (bridge) bridge.requestMode(m);
  else setMode(m);
}

function finishEdit() {
  if (bridge) bridge.finishEdit();
  else setMode("click");
}

/* ================================================================ Bearbeiten */
function hideGuides() { document.querySelectorAll("#guides div").forEach((g) => (g.style.display = "none")); }

function guide(cls, p) {
  const g = document.querySelector(`#guides .${cls}`);
  g.style.display = "block";
  if (cls === "gv") g.style.left = `${p}px`; else g.style.top = `${p}px`;
}

/** Einrasten an Bildschirmkanten, Bildschirmmitte, Kanten und Mitten der anderen Widgets. */
function snap(w, x, y, wd, ht) {
  const xs = [0, innerWidth / 2, innerWidth];
  const ys = [0, innerHeight / 2, innerHeight];
  for (const o of WIDGETS) {
    if (o === w || o.hidden) continue;
    const r = o.getBoundingClientRect();
    xs.push(r.left, r.left + r.width / 2, r.right);
    ys.push(r.top, r.top + r.height / 2, r.bottom);
  }
  const fit = (p, size, lines) => {
    for (const edge of [0, size / 2, size]) for (const l of lines) if (Math.abs(p + edge - l) <= SNAP) return [l - edge, l];
    return null;
  };
  let gx = null, gy = null;
  const fx = fit(x, wd, xs);
  if (fx) [x, gx] = fx; else x = Math.round(x / GRID) * GRID;
  const fy = fit(y, ht, ys);
  if (fy) [y, gy] = fy; else y = Math.round(y / GRID) * GRID;
  hideGuides();
  if (gx != null) guide("gv", gx);
  if (gy != null) guide("gh", gy);
  return [x, y];
}

for (const w of WIDGETS) {
  w.addEventListener("pointerdown", (e) => {
    if (mode !== "edit" || e.button !== 0) return;
    e.preventDefault();
    const c = cfg(w.dataset.id);
    [c.x, c.y] = pos(w.dataset.id);
    const r = w.getBoundingClientRect();
    const off = [e.clientX - c.x, e.clientY - c.y];
    w.setPointerCapture(e.pointerId);
    w.classList.add("dragging");
    dragging = true;
    const move = (ev) => {
      let x = ev.clientX - off[0], y = ev.clientY - off[1];
      if (!ev.shiftKey) [x, y] = snap(w, x, y, r.width, r.height);
      else hideGuides();
      c.x = Math.round(x);
      c.y = Math.round(y);
      place(w);
    };
    const up = () => {
      w.removeEventListener("pointermove", move);
      w.classList.remove("dragging");
      dragging = false;
      hideGuides();
      regionsSoon();
      saveSoon();
    };
    w.addEventListener("pointermove", move);
    w.addEventListener("pointerup", up, { once: true });
    w.addEventListener("pointercancel", up, { once: true });
  });
  w.addEventListener("wheel", (e) => {
    if (mode !== "edit") return;
    e.preventDefault();
    const c = cfg(w.dataset.id);
    c.scale = Math.min(3, Math.max(0.5, Math.round(((c.scale || 1) - Math.sign(e.deltaY) * 0.05) * 100) / 100));
    place(w);
    regionsSoon();
    saveSoon();
  }, { passive: false });
}

function buildToolbar() {
  const box = $("toggles");
  box.replaceChildren();
  for (const w of WIDGETS) {
    const l = document.createElement("label");
    const c = document.createElement("input");
    c.type = "checkbox";
    c.dataset.id = w.dataset.id;
    c.addEventListener("change", () => {
      cfg(w.dataset.id).enabled = c.checked;
      place(w);
      if (w.dataset.id === "meter" && c.checked && $("meter").getAttribute("src") === "about:blank") $("meter").src = "/";
      regionsSoon();
      saveSoon();
    });
    l.append(c, w.dataset.title);
    box.append(l);
  }
}

function syncToolbar() {
  for (const c of $("toggles").querySelectorAll("input")) c.checked = !!cfg(c.dataset.id).enabled;
  $("fx").value = layout.fx || "";
}

$("fx").addEventListener("change", () => { layout.fx = $("fx").value; applyFx(); saveSoon(); });
$("done").addEventListener("click", finishEdit);
$("reset").addEventListener("click", () => {
  for (const id of Object.keys(W)) Object.assign(cfg(id), { x: null, y: null, scale: 1 });
  placeAll();
  saveSoon();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && mode === "edit") finishEdit(); });

/* ================================================================ Namenseffekt */
let effectsCss = null;

async function applyFx() {
  if (layout) await meterFx();
}

/** Effekt auf die eigene Zeile in der Meter-Oberfläche legen (gleicher Ursprung, also direkt). */
async function meterFx() {
  const doc = $("meter").contentDocument;
  if (!doc || !doc.head) return;
  if (!doc.getElementById("deckbar-fx")) {
    effectsCss ??= await (await fetch("effects.css")).text();
    const st = doc.createElement("style");
    st.id = "deckbar-fx";
    st.textContent = effectsCss;
    doc.head.append(st);
    new MutationObserver(() => markOwnRow(doc)).observe(doc.documentElement,
      { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
  }
  markOwnRow(doc);
}

function markOwnRow(doc) {
  const fx = layout?.fx || "";
  for (const el of doc.querySelectorAll(".item .content .name")) {
    const want = fx && el.closest(".item.isUser") ? `dbx-fx dbx-fx-${fx}` : "";
    const cur = [...el.classList].filter((c) => c.startsWith("dbx-fx"));
    if (cur.join(" ") === want) continue; // das Meter rendert Zeilen neu → Klassen ggf. wieder setzen
    el.classList.remove(...cur);
    if (want) el.classList.add(...want.split(" "));
  }
}

$("meter").addEventListener("load", () => { watchMeterDown(); meterFx(); regionsSoon(); });

/* ================================================================ Meter-Fenster-Befehle */
let meterDown = null; // letzter Mausdruck im Meter, in Seitenkoordinaten

function watchMeterDown() {
  const win = $("meter").contentWindow;
  if (!win || win.__deckbarDown) return;
  win.__deckbarDown = true;
  // am Fenster und in der Capture-Phase: vor dem Listener des Meters, der start_drag auslöst
  win.addEventListener("mousedown", (e) => {
    const r = W.meter.getBoundingClientRect();
    const s = cfg("meter").scale || 1;
    meterDown = [r.left + e.clientX * s, r.top + e.clientY * s];
  }, true);
}

function startMeterDrag() {
  // Das Meter meldet einen Mausdruck auf Kopf- oder Fußzeile (start_drag). Ab jetzt folgt das Widget
  // der Maus. Eine durchsichtige Fläche über allem fängt die Bewegungen, auch wenn die Maus das
  // iframe verlässt; Bewegungen, die das iframe noch selbst bekommt, zählen ebenso.
  const doc = $("meter").contentDocument;
  if (!doc || mode === "edit" || dragging) return;
  const c = cfg("meter");
  [c.x, c.y] = pos("meter");
  let last = meterDown; // wo der Mausdruck war, sonst ginge die erste Bewegung verloren
  const shield = document.createElement("div");
  shield.style.cssText = "position:fixed;inset:0;z-index:99;cursor:grabbing";
  document.body.append(shield);
  const inFrame = (e) => {
    const r = W.meter.getBoundingClientRect();
    const s = c.scale || 1;
    return [r.left + e.clientX * s, r.top + e.clientY * s];
  };
  const follow = (p) => {
    if (last) {
      c.x = Math.round(c.x + p[0] - last[0]);
      c.y = Math.round(c.y + p[1] - last[1]);
      place(W.meter);
    }
    last = p;
  };
  const onPage = (e) => (e.buttons & 1 ? follow([e.clientX, e.clientY]) : up());
  // Seitenkoordinaten zum Zeitpunkt des Ereignisses (vor dem Verschieben des iframes gerechnet)
  const onFrame = (e) => (e.buttons & 1 ? follow(inFrame(e)) : up());
  const up = () => {
    if (!dragging) return;
    dragging = false;
    shield.remove();
    removeEventListener("pointermove", onPage, true);
    removeEventListener("pointerup", up, true);
    doc.removeEventListener("mousemove", onFrame, true);
    doc.removeEventListener("mouseup", up, true);
    regionsSoon();
    saveSoon();
  };
  dragging = true;
  addEventListener("pointermove", onPage, true);
  addEventListener("pointerup", up, true);
  doc.addEventListener("mousemove", onFrame, true);
  doc.addEventListener("mouseup", up, true);
}

function hostForward(cmd, args) {
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

window.__DECKBAR_OVERLAY__ = {
  hostCall(cmd, args = {}) {
    switch (cmd) {
      case "resize_window": {
        W.meter.style.width = `${Math.ceil(Number(args.width) || 1)}px`;
        W.meter.style.height = `${Math.ceil(Number(args.height) || 1)}px`;
        regionsSoon();
        return Promise.resolve(null);
      }
      case "start_drag":
        startMeterDrag();
        return Promise.resolve(null);
      case "start_tool_drag": case "window_resize_drag": case "begin_tool_resize":
      case "main_window_ready": case "window_show": case "details_window_ready":
        return Promise.resolve(null);
      case "begin_window_resize": return Promise.resolve(false);
      case "finish_window_resize": case "tool_window_ready": case "window_focus": return Promise.resolve(true);
      case "overlay_lock_supported": return Promise.resolve(true);
      case "set_overlay_locked":
        requestMode(args.locked ? "lock" : "click");
        return Promise.resolve(null);
      case "set_lock_button_rect":
        lockRect = { x: +args.x || 0, y: +args.y || 0, width: +args.width || 0, height: +args.height || 0 };
        regionsSoon();
        return Promise.resolve(null);
      case "capture_screenshot": {
        // Rechteck aus Meter-Koordinaten in die der ganzen Fläche umrechnen
        const r = W.meter.getBoundingClientRect();
        const s = cfg("meter").scale || 1;
        return hostForward(cmd, { ...args, x: r.left + (+args.x || 0) * s, y: r.top + (+args.y || 0) * s,
          width: (+args.width || r.width) * s, height: (+args.height || r.height) * s });
      }
      default:
        return hostForward(cmd, args);
    }
  },
};

/* ================================================================ Boss */
const ttk = { target: null, samples: [] };

function fmt(s) {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  if (h >= 24) return `${Math.floor(h / 24)} T ${h % 24} h`;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
}

function onDps(part) {
  Object.assign(dps, part);
  const d = dps.dps;
  if (d && d.target && d.hp != null) {
    if (ttk.target !== d.target) { ttk.target = d.target; ttk.samples = []; }
    const now = performance.now() / 1000;
    ttk.samples.push([now, d.hp]);
    while (ttk.samples.length > 2 && now - ttk.samples[0][0] > 40) ttk.samples.shift();
  }
  renderBoss();
}

function renderBoss() {
  if (!layout) return;
  const c = cfg("boss");
  const d = dps.dps;
  const has = !!(d && d.target && d.hp != null);
  W.boss.classList.toggle("idle", c.hide_idle && !(has && dps.dps_active) && mode !== "edit");
  regionsSoon();
  if (!has) {
    $("boss-name").textContent = mode === "edit" ? "Boss-Leiste" : "Kein Ziel";
    $("boss-pct").textContent = "";
    $("boss-fill").style.transform = "scaleX(1)";
    $("boss-glow").style.left = "calc(100% - 2px)";
    $("boss-time").textContent = "";
    $("boss-ttk").textContent = "";
    return;
  }
  const hp = Math.max(0, Math.min(100, d.hp));
  $("boss-name").textContent = d.target;
  $("boss-pct").textContent = `${hp.toFixed(1).replace(".", ",")} %`;
  $("boss-fill").style.transform = `scaleX(${hp / 100})`;
  $("boss-glow").style.left = `calc(${hp}% - 2px)`;
  $("boss-time").innerHTML = d.time ? `Kampf <b>${fmt(d.time)}</b>` : "";
  let text = "";
  if (c.show_ttk && ttk.samples.length >= 2) {
    const [t0, h0] = ttk.samples[0];
    const [t1, h1] = ttk.samples[ttk.samples.length - 1];
    const rate = (h0 - h1) / Math.max(0.001, t1 - t0);
    if (t1 - t0 >= 4 && rate > 0 && hp > 0) text = `Kill in <b>${fmt(hp / rate)}</b>`;
  }
  $("boss-ttk").innerHTML = text;
}

/* ================================================================ Event-Timer */
/** Nächster Start bzw. Restzeit eines Ereignisses. `at` zählt in Minuten ab Montag 00:00 (tz). */
function nextEvent(ev, nowMs) {
  const offset = ev.tz === "utc" ? 0 : -new Date(nowMs).getTimezoneOffset();
  const minutes = nowMs / 60000 + offset + 3 * 1440; // 0 = Montag 00:00 (1.1.1970 war ein Donnerstag)
  const since = (((minutes - ev.at) % ev.every) + ev.every) % ev.every;
  if (since < ev.open) return { open: true, left: (ev.open - since) * 60 };
  return { open: false, left: (ev.every - since) * 60 };
}

function renderTimers() {
  if (!layout || W.timers.hidden) return;
  const now = Date.now();
  const list = $("timer-list");
  const evs = (cfg("timers").events || []).filter((e) => e.enabled !== false);
  if (!evs.length) {
    list.innerHTML = '<div class="empty">Keine Ereignisse – in der Web-UI eintragen.</div>';
    return;
  }
  const rows = evs.map((ev) => ({ ev, n: nextEvent(ev, now) }))
    .sort((a, b) => (b.n.open - a.n.open) || a.n.left - b.n.left);
  list.replaceChildren(...rows.map(({ ev, n }) => {
    const row = document.createElement("div");
    row.className = n.open ? "open" : n.left < 600 ? "soon" : "";
    const a = document.createElement("span");
    a.textContent = ev.name;
    const b = document.createElement("span");
    b.textContent = n.open ? `offen · ${fmt(n.left)}` : fmt(n.left);
    row.append(a, b);
    return row;
  }));
}

/* ================================================================ Daten */
function log(text) {
  if (bridge) bridge.log(String(text));
  else console.log(text);
}

function connect() {
  const es = new EventSource("/api/overlay/events");
  let offlineTimer = 0;
  es.addEventListener("layout", (e) => applyLayout(JSON.parse(e.data)));
  es.addEventListener("dps", (e) => onDps(JSON.parse(e.data)));
  es.onopen = () => { clearTimeout(offlineTimer); $("offline").hidden = true; };
  es.onerror = () => {
    clearTimeout(offlineTimer);
    offlineTimer = setTimeout(() => { $("offline").hidden = es.readyState === EventSource.OPEN; }, 4000);
  };
}

function start() {
  setMode(mode);
  connect();
  setInterval(renderTimers, 1000);
  new ResizeObserver(regionsSoon).observe(document.body);
  for (const w of WIDGETS) new ResizeObserver(regionsSoon).observe(w);
  addEventListener("resize", () => { placeAll(); });
}

if (typeof QWebChannel !== "undefined" && window.qt?.webChannelTransport) {
  new QWebChannel(qt.webChannelTransport, (ch) => {
    bridge = ch.objects.bridge;
    mode = bridge.mode;
    bridge.modeChanged.connect(() => setMode(bridge.mode));
    start();
    bridge.ready(); // erst jetzt zeigt der Host die Fläche
  });
} else {
  start();
}
