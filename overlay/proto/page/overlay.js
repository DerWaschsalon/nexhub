/* DeckBar-Overlay (Prototyp): Widgets, Layout, Bearbeiten-Modus. Daten sind hier noch Attrappen
 * (außer Meter und Event-Uhrzeiten). Host-Brücke: QWebChannel-Objekt „bridge“ aus Overlay.qml. */
"use strict";

const GRID = 8;
const SNAP = 8;
const WIDGETS = [...document.querySelectorAll(".widget")];
const DEFAULTS = {
  "w-meter": { x: 40, y: 320 },
  "w-name": { x: 40, y: 250 },
  "w-boss": { x: () => innerWidth / 2 - 210, y: 90 },
  "w-timer": { x: () => innerWidth - 300, y: 120 },
  "w-auras": { x: () => innerWidth / 2 - 100, y: () => innerHeight - 260 },
};

let bridge = null;
let layout = { widgets: {}, fx: "brennen" };
let editing = false;

// ---------- Layout ----------

function val(v) { return typeof v === "function" ? v() : v; }

function place(w) {
  const d = DEFAULTS[w.id] || { x: 20, y: 20 };
  const s = layout.widgets[w.id] || (layout.widgets[w.id] = {});
  if (s.x == null) { s.x = Math.round(val(d.x)); s.y = Math.round(val(d.y)); }
  s.scale = s.scale || 1;
  w.hidden = !!s.hidden;
  w.style.transform = `translate(${s.x}px, ${s.y}px) scale(${s.scale})`;
}

function placeAll() { WIDGETS.forEach(place); reportClickRects(); }

let saveTimer = 0;
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => bridge && bridge.saveLayout(JSON.stringify(layout, null, 1)), 300);
}

/** Rechtecke der Widgets mit data-click an den Host (Eingabe-Region im Modus „click“). */
function reportClickRects() {
  if (!bridge) return;
  const rects = WIDGETS.filter((w) => !w.hidden && w.hasAttribute("data-click")).map((w) => {
    const r = w.getBoundingClientRect();
    return [r.left, r.top, r.width, r.height];
  });
  bridge.setClickRects(JSON.stringify(rects));
}

// ---------- Bearbeiten-Modus ----------

function setEditing(on) {
  editing = on;
  document.body.classList.toggle("edit", on);
  if (!on) hideGuides();
}

function hideGuides() { document.querySelectorAll("#guides div").forEach((g) => (g.style.display = "none")); }

function guide(cls, pos) {
  const g = document.querySelector(`#guides .${cls}`);
  g.style.display = "block";
  if (cls === "gv") g.style.left = pos + "px"; else g.style.top = pos + "px";
}

/** Einrasten: Bildschirmkanten, Bildschirmmitte, Kanten und Mitten der anderen Widgets. */
function snap(w, x, y, wd, ht) {
  const xs = [0, innerWidth / 2, innerWidth];
  const ys = [0, innerHeight / 2, innerHeight];
  for (const o of WIDGETS) {
    if (o === w || o.hidden) continue;
    const r = o.getBoundingClientRect();
    xs.push(r.left, r.left + r.width / 2, r.right);
    ys.push(r.top, r.top + r.height / 2, r.bottom);
  }
  let gx = null, gy = null;
  const fit = (pos, size, lines) => {
    for (const edge of [0, size / 2, size]) {
      for (const l of lines) if (Math.abs(pos + edge - l) <= SNAP) return [l - edge, l];
    }
    return null;
  };
  const fx = fit(x, wd, xs); if (fx) { x = fx[0]; gx = fx[1]; } else x = Math.round(x / GRID) * GRID;
  const fy = fit(y, ht, ys); if (fy) { y = fy[0]; gy = fy[1]; } else y = Math.round(y / GRID) * GRID;
  hideGuides();
  if (gx != null) guide("gv", gx);
  if (gy != null) guide("gh", gy);
  return [x, y];
}

for (const w of WIDGETS) {
  w.addEventListener("pointerdown", (e) => {
    if (!editing || e.button !== 0) return;
    e.preventDefault();
    const s = layout.widgets[w.id];
    const r = w.getBoundingClientRect();
    const off = [e.clientX - s.x, e.clientY - s.y];
    w.setPointerCapture(e.pointerId);
    w.classList.add("dragging");
    const move = (ev) => {
      let x = ev.clientX - off[0], y = ev.clientY - off[1];
      if (!ev.shiftKey) [x, y] = snap(w, x, y, r.width, r.height);
      else hideGuides();
      s.x = Math.round(x); s.y = Math.round(y);
      place(w);
    };
    const up = () => {
      w.removeEventListener("pointermove", move);
      w.classList.remove("dragging");
      hideGuides();
      save();
    };
    w.addEventListener("pointermove", move);
    w.addEventListener("pointerup", up, { once: true });
  });
  w.addEventListener("wheel", (e) => {
    if (!editing) return;
    e.preventDefault();
    const s = layout.widgets[w.id];
    s.scale = Math.min(3, Math.max(0.5, Math.round(((s.scale || 1) - Math.sign(e.deltaY) * 0.05) * 100) / 100));
    place(w);
    save();
  }, { passive: false });
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && editing && bridge) bridge.requestMode("lock");
});
document.getElementById("done").addEventListener("click", () => bridge && bridge.requestMode("lock"));

function buildToggles() {
  const box = document.getElementById("toggles");
  for (const w of WIDGETS) {
    const l = document.createElement("label");
    const c = document.createElement("input");
    c.type = "checkbox";
    c.checked = !layout.widgets[w.id].hidden;
    c.addEventListener("change", () => { layout.widgets[w.id].hidden = !c.checked; place(w); reportClickRects(); save(); });
    l.append(c, " " + w.dataset.title);
    box.append(l);
  }
}

// ---------- Namenseffekt ----------

const fxSelect = document.getElementById("fx");
const nameDemo = document.getElementById("name-demo");

function applyFx() {
  const fx = layout.fx || "";
  nameDemo.className = "name-demo" + (fx ? ` dbx-fx dbx-fx-${fx}` : "");
  nameDemo.querySelector(".dbx-embers")?.remove();
  if (fx === "brennen") nameDemo.append(embers());
  fxSelect.value = fx;
  // eigene Zeile im Meter: das per Host eingehängte frame-effects.js hört darauf
  document.getElementById("meter").contentWindow?.postMessage({ deckbarNameFx: fx }, "*");
}

function embers() {
  const box = document.createElement("span");
  box.className = "dbx-embers";
  return box;
}

fxSelect.addEventListener("change", () => { layout.fx = fxSelect.value; applyFx(); save(); });

// ---------- Event-Timer (echte Uhrzeiten; Global, laut Recherche 13.10., noch zu prüfen) ----------

const EVENTS = [
  { name: "Shugo-Festival", every: 60, at: 0, open: 5, tz: "local" },
  { name: "Spacetime Rift", every: 180, at: 120, open: 10, tz: "local" }, // 2/5/8/11/14/17/20/23 Uhr
  { name: "Daily Reset", every: 1440, at: 7 * 60, open: 0, tz: "utc" },
];

function nextEvent(ev, now) {
  const d = new Date(now);
  const minsNow = ev.tz === "utc" ? d.getUTCHours() * 60 + d.getUTCMinutes() : d.getHours() * 60 + d.getMinutes();
  const secs = d.getSeconds();
  const since = ((minsNow - ev.at) % ev.every + ev.every) % ev.every; // Minuten seit letztem Start
  if (since < ev.open) return { open: true, left: (ev.open - since) * 60 - secs };
  return { open: false, left: (ev.every - since) * 60 - secs };
}

function weeklyReset(now) {
  const d = new Date(now);
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 7));
  let add = (3 - t.getUTCDay() + 7) % 7; // Mittwoch
  if (add === 0 && t <= d) add = 7;
  t.setUTCDate(t.getUTCDate() + add);
  return (t - d) / 1000;
}

function fmt(s) {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  if (h >= 24) return `${Math.floor(h / 24)} T ${h % 24} h`;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
}

function renderTimers() {
  const now = Date.now();
  const rows = EVENTS.map((ev) => {
    const n = nextEvent(ev, now);
    const cls = n.open ? "open" : n.left < 600 ? "soon" : "";
    return `<div class="${cls}"><span>${ev.name}</span><span>${n.open ? "offen " + fmt(n.left) : fmt(n.left)}</span></div>`;
  });
  rows.push(`<div><span>Weekly Reset</span><span>${fmt(weeklyReset(now))}</span></div>`);
  document.getElementById("timer-list").innerHTML = rows.join("");
}

// ---------- Attrappen: Boss und Auren ----------

const FIGHT = 150, ENRAGE = 300;
function renderBoss() {
  const t = (Date.now() / 1000) % FIGHT;
  const hp = Math.max(0, 1 - Math.pow(t / FIGHT, 0.9));
  document.getElementById("boss-fill").style.width = (hp * 100).toFixed(1) + "%";
  document.getElementById("boss-pct").textContent = (hp * 100).toFixed(1) + " %";
  const dps = t > 3 ? (1 - hp) / t : 0;
  document.getElementById("boss-ttk").textContent = dps ? fmt(hp / dps) : "–";
  const left = ENRAGE - t;
  const el = document.getElementById("boss-enrage");
  el.textContent = fmt(left);
  el.className = left < 30 ? "bad" : left < 60 ? "warn" : "";
}

const AURAS = [
  { label: "B1", cd: 12 }, { label: "B2", cd: 30 }, { label: "D1", cd: 8 }, { label: "CD", cd: 45 },
];
const auraBox = document.getElementById("auras");
AURAS.forEach((a, i) => {
  a.el = document.createElement("div");
  a.el.className = "aura";
  a.el.innerHTML = `<div class="sweep"></div><span class="t">${a.label}</span>`;
  a.offset = i * 3.7;
  auraBox.append(a.el);
});
function renderAuras() {
  const now = Date.now() / 1000;
  for (const a of AURAS) {
    const cycle = a.cd + 4; // 4 s „bereit“
    const t = (now + a.offset) % cycle;
    const ready = t >= a.cd;
    const left = a.cd - t;
    a.el.classList.toggle("ready", ready);
    a.el.classList.toggle("low", !ready && left < 3);
    a.el.querySelector(".sweep").style.setProperty("--p", ready ? "0%" : (left / a.cd * 100).toFixed(1) + "%");
    a.el.querySelector(".t").textContent = ready ? a.label : Math.ceil(left);
  }
}

// ---------- Start ----------

function tick() { renderTimers(); renderBoss(); renderAuras(); }

function start() {
  placeAll();
  buildToggles();
  applyFx();
  tick();
  setInterval(tick, 250);
  new ResizeObserver(reportClickRects).observe(document.body);
  document.getElementById("meter").addEventListener("load", applyFx);
}

new QWebChannel(qt.webChannelTransport, (ch) => {
  bridge = ch.objects.bridge;
  document.getElementById("meter").src = bridge.meterUrl;
  setEditing(bridge.mode === "edit");
  bridge.modeChanged.connect(() => { setEditing(bridge.mode === "edit"); reportClickRects(); });
  bridge.loadLayout((text) => {
    try { Object.assign(layout, JSON.parse(text)); } catch (e) { /* Standard-Layout */ }
    start();
  });
});
