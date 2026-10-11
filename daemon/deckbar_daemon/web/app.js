"use strict";
/* DeckBar-Konfiguration: Editor + Live-Vorschau. Jede Änderung wird nach kurzer Pause
   gespeichert und vom Daemon sofort an alle Geräte (und den Simulator) geschickt. */

const W = 640, H = 172, PAD = 8, GAP = 8;
const STYLES = { default: "#ffffff", accent: null, danger: "#ff453a", success: "#30d158", warning: "#ff9f0a" };
const STYLE_NAMES = { default: "Standard", accent: "Akzent", danger: "Rot", success: "Grün", warning: "Orange" };
const TYPE_NAMES = { button: "Button", toggle: "Toggle", slider: "Slider", media: "Media", dps: "DPS-Meter" };
const BUILTIN_KEYS = ["mic_muted", "out_muted", "playing", "out_volume", "mic_volume", "art_url", "dps", "dps_active"];
const CLASS_COLORS = { gladiator: "#E8A33D", templar: "#5B8DEF", ranger: "#6CCB5F", assassin: "#B46AE6", sorcerer: "#4FC3F7", cleric: "#F4E07A", spiritmaster: "#EC7FB8", chanter: "#4DD4B0", brawler: "#F0624D" };
const EXTRA_NAMES = { pct: "Anteil in %", dmg: "Gesamtschaden", none: "nichts" };
// Vorschau im Bearbeiten-Modus, solange das Meter nichts liefert
const DPS_DEMO = { target: "Beispiel-Boss", time: 92, hp: 37.4, rows: [
  { name: "Du", cls: "spiritmaster", dps: 22950, dmg: 2111400, pct: 28.4, you: true },
  { name: "Gladiator", cls: "gladiator", dps: 20080, dmg: 1847360, pct: 24.9 },
  { name: "Zauberer", cls: "sorcerer", dps: 18110, dmg: 1666120, pct: 22.4 },
  { name: "Templer", cls: "templar", dps: 10600, dmg: 975200, pct: 13.1 },
  { name: "Kleriker", cls: "cleric", dps: 4337, dmg: 399004, pct: 5.4 },
  { name: "Kantor", cls: "chanter", dps: 3900, dmg: 358800, pct: 4.8 },
] };
const ID_RE = /^[A-Za-z0-9_-]{1,32}$/;

const TEMPLATES = [
  { name: "Mikro stumm", icon: "microphone-off", item: { type: "toggle", label: "Mikro", icon: "microphone", icon_on: "microphone-off", bind: "mic_muted", style: "danger", action: { do: "volume", target: "source", op: "toggle_mute" } } },
  { name: "Ausgang stumm", icon: "volume-off", item: { type: "toggle", label: "Ausgang", icon: "volume-high", icon_on: "volume-off", bind: "out_muted", style: "warning", action: { do: "volume", target: "sink", op: "toggle_mute" } } },
  { name: "Lautstärke-Slider", icon: "volume-high", item: { type: "slider", label: "Lautstärke", icon: "volume-high", icon_on: "volume-off", bind: "out_volume", mute_bind: "out_muted", w: 2, action: { do: "volume", target: "sink", op: "set" }, long_action: { do: "volume", target: "sink", op: "toggle_mute" } } },
  { name: "Mikro-Pegel", icon: "microphone", item: { type: "slider", label: "Mikro", icon: "microphone", icon_on: "microphone-off", bind: "mic_volume", mute_bind: "mic_muted", w: 2, action: { do: "volume", target: "source", op: "set" }, long_action: { do: "volume", target: "source", op: "toggle_mute" } } },
  { name: "Media-Kachel", icon: "music", item: { type: "media", w: 2, h: 2 } },
  { name: "Play/Pause", icon: "play-pause", item: { type: "toggle", label: "Play", icon: "play", icon_on: "pause", bind: "playing", style: "accent", action: { do: "media", op: "play_pause" } } },
  { name: "Nächster Titel", icon: "skip-next", item: { label: "Weiter", icon: "skip-next", action: { do: "media", op: "next" } } },
  { name: "Vorheriger Titel", icon: "skip-previous", item: { label: "Zurück", icon: "skip-previous", action: { do: "media", op: "previous" } } },
  { name: "Link öffnen", icon: "web", item: { label: "Link", icon: "web", action: { do: "open", url: "https://" } } },
  { name: "Hotkey", icon: "keyboard", item: { label: "Hotkey", icon: "keyboard", action: { do: "hotkey", keys: "ctrl+shift+m" } } },
  { name: "Befehl", icon: "console", item: { label: "Befehl", icon: "console", action: { do: "shell", cmd: "notify-send DeckBar Hallo" } } },
  { name: "Seite wechseln", icon: "chevron-right", item: { label: "Mehr", icon: "chevron-right", nav: "" } },
  { name: "AION 2 DPS-Meter", icon: "flash", item: { type: "dps" } },
];

const ACTION_FIELDS = {
  media: [["op", "select", "Befehl", { play_pause: "Play/Pause", play: "Play", pause: "Pause", stop: "Stop", next: "Weiter", previous: "Zurück" }], ["player", "text", "Player (leer = aktiver)"]],
  volume: [["target", "select", "Gerät", { sink: "Ausgang (Sink)", source: "Mikrofon (Source)" }], ["op", "select", "Aktion", { toggle_mute: "Stumm umschalten", mute: "Stumm", unmute: "Ton an", step: "Schritt", set: "Wert setzen (Slider)" }], ["step", "number", "Schritt in %"], ["limit", "number", "Obergrenze %"]],
  open: [["url", "text", "URL oder Pfad"]],
  hotkey: [["keys", "text", "Tasten, z. B. ctrl+shift+m"]],
  shell: [["cmd", "text", "Befehl (/bin/sh -c; Slider-Wert in $DECKBAR_VALUE)"]],
};
const ACTION_DEFAULTS = {
  media: { do: "media", op: "play_pause" },
  volume: { do: "volume", target: "sink", op: "toggle_mute" },
  open: { do: "open", url: "https://" },
  hotkey: { do: "hotkey", keys: "ctrl+shift+m" },
  shell: { do: "shell", cmd: "" },
};

const S = {
  layout: null,
  state: {},
  devices: [],
  status: {},
  dps: null,         // Verbindung zum A2Tools-Meter (GET /api/dps)
  runs: null,        // Dungeon-Runs → Discord (GET /api/runs)
  icons: {},
  page: 0,
  sel: null,         // Index des ausgewählten Items auf der aktuellen Seite
  mode: "edit",
  saveTimer: null,
  saving: false,
  dirty: false,
  lastSaved: "",
  ws: null,
};

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) e.append(kid.nodeType ? kid : document.createTextNode(kid));
  return e;
};
const glyph = (name) => (name && S.icons[name] ? String.fromCodePoint(S.icons[name]) : "");
const accent = () => S.layout?.theme?.accent || "#5AC8FA";
const styleColor = (s) => (s === "accent" ? accent() : STYLES[s] || "#ffffff");
const truthy = (v) => !!v && v !== 0;
const curPage = () => S.layout.pages[S.page];
const selItem = () => (S.sel == null ? null : curPage().items[S.sel]);

/* ================================================================= Raster (wie shared-ui/src/ui.c) */
function placeItems(page) {
  const cols = Math.min(8, Math.max(1, page.cols || 6));
  const rows = Math.min(3, Math.max(1, page.rows || 2));
  const used = Array.from({ length: rows }, () => Array(cols).fill(false));
  const aw = W - 2 * PAD + GAP, ah = H - 2 * PAD + GAP;
  return page.items.map((it) => {
    const w = Math.min(cols, Math.max(1, it.w || 1));
    const h = Math.min(rows, Math.max(1, it.h || 1));
    for (let r = 0; r + h <= rows; r++) {
      for (let c = 0; c + w <= cols; c++) {
        let fits = true;
        for (let rr = r; rr < r + h && fits; rr++) for (let cc = c; cc < c + w && fits; cc++) fits = !used[rr][cc];
        if (!fits) continue;
        for (let rr = r; rr < r + h; rr++) for (let cc = c; cc < c + w; cc++) used[rr][cc] = true;
        const x0 = PAD + Math.floor((c * aw) / cols), x1 = PAD + Math.floor(((c + w) * aw) / cols) - GAP;
        const y0 = PAD + Math.floor((r * ah) / rows), y1 = PAD + Math.floor(((r + h) * ah) / rows) - GAP;
        return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
      }
    }
    return null;
  });
}

/* ================================================================= Vorschau */
function renderPreview() {
  const pv = $("preview");
  pv.replaceChildren();
  pv.classList.toggle("test", S.mode === "test");
  pv.style.setProperty("--accent", accent());
  const page = curPage();
  const boxes = placeItems(page);
  page.items.forEach((it, i) => {
    const b = boxes[i];
    if (!b) return;
    pv.append(renderTile(it, b, i));
  });
  if (S.layout.pages.length > 1) {
    pv.append(el("div", { class: "dots" }, S.layout.pages.map((_, i) => el("span", { class: i === S.page ? "on" : null }))));
  }
  fitPreview();
}

function renderTile(it, b, idx) {
  const type = it.type || "button";
  const style = it.style || "default";
  const t = el("div", { class: "tile", style: `left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px` });
  t.style.setProperty("--c", styleColor(style));
  if (S.mode === "edit" && idx === S.sel) t.classList.add("sel");

  if (type === "button" || type === "toggle") {
    const on = type === "toggle" && truthy(S.state[it.bind]);
    if (type === "button" && style !== "default") t.classList.add("tint");
    if (on) t.classList.add("on");
    const big = b.h >= 100, row = !big && b.w >= 150;
    const ic = on && it.icon_on ? it.icon_on : it.icon;
    const inner = el("div", { class: "in" + (row ? " row" : "") });
    if (ic) inner.append(el("span", { class: "ic" + (big ? " big" : b.h < 60 ? " sm" : ""), text: glyph(ic) || glyph("dots-horizontal") }));
    if (it.label && b.h >= 60) inner.append(el("span", { class: "lb", text: it.label }));
    t.append(inner);
    t.addEventListener("click", () => onTileClick(it, idx));
  } else if (type === "slider") {
    const min = it.min ?? 0, max = it.max ?? 100;
    const v = Number(S.state[it.bind] ?? min);
    const pct = Math.max(0, Math.min(100, ((v - min) * 100) / (max - min || 1)));
    const muted = it.mute_bind && truthy(S.state[it.mute_bind]);
    if (muted) t.classList.add("muted");
    const compact = b.w < 150;
    const fill = el("div", { class: "fill", style: `width:${pct}%` });
    const ic = muted && it.icon_on ? it.icon_on : it.icon;
    t.append(fill);
    if (ic) t.append(el("span", { class: "ic" + (b.h < 60 ? " sm" : ""), style: `position:absolute;z-index:2;${compact ? "left:10px;top:8px" : "left:14px;top:50%;transform:translateY(-50%)"}`, text: glyph(ic) }));
    if (!compact && it.label && b.h >= 60) t.append(el("span", { class: "lb", style: `position:absolute;z-index:2;left:${ic ? 52 : 16}px;top:50%;transform:translateY(-50%)`, text: it.label }));
    t.append(el("span", { class: "val" + (compact ? " sm" : ""), text: `${Math.round(v)}%` }));
    attachSliderTest(t, it, min, max);
    t.addEventListener("click", () => S.mode === "edit" && select(idx));
  } else if (type === "media") {
    const tall = b.h >= 100;
    const tr = S.state.track;
    const m = el("div", { class: "media" });
    let tx = 16;
    if (tall ? b.w >= 180 : b.w >= 260) {
      m.append(el("span", { class: "ic", style: tall ? "" : `top:${(b.h - 28) / 2}px`, text: glyph("music-note") }));
      tx = 54;
    }
    const right = tall ? 16 : 62;
    const title = tr?.title || "Nichts läuft";
    const artist = tr?.artist || "";
    const tiY = tall ? 14 : artist ? b.h / 2 - 22 : (b.h - 23) / 2;
    m.append(el("div", { class: "ti", style: `left:${tx}px;top:${tiY}px;width:${b.w - tx - right}px;opacity:${tr?.title ? 1 : 0.59}`, text: title }));
    if (artist) m.append(el("div", { class: "ar", style: `left:${tx}px;top:${tall ? 38 : b.h / 2 + 2}px;width:${b.w - tx - right}px`, text: artist }));
    const playG = glyph(S.state.playing ? "pause" : "play");
    const mini = (g, part, size) => el("span", { class: "mini", style: `width:${size}px;height:${size}px;font-size:${size >= 44 ? 28 : 20}px`, text: g, onclick: (e) => { if (S.mode === "test") { e.stopPropagation(); sendEvent({ event: "button_press", item: it.id, part }); } } });
    if (tall) {
      m.append(el("div", { class: "bar" }, mini(glyph("skip-previous"), "prev", 48), mini(playG, "toggle", 58), mini(glyph("skip-next"), "next", 48)));
    } else {
      const p = mini(playG, "toggle", 44);
      p.style.cssText += ";position:absolute;right:12px;top:50%;transform:translateY(-50%)";
      m.append(p);
    }
    t.append(m);
    t.addEventListener("click", () => onTileClick(it, idx));
  } else if (type === "dps") {
    t.append(renderDps(it, b));
    t.addEventListener("click", () => S.mode === "edit" && select(idx));
  }
  return t;
}

/* 8432 · 18,4k · 1,23M wie fmt_amount in ui.c */
function fmtAmount(v) {
  v = Math.max(0, v || 0);
  const s = v >= 1e9 ? (v / 1e9).toFixed(2) + "G" : v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e4 ? (v / 1e3).toFixed(1) + "k" : String(Math.round(v));
  return s.replace(".", ",");
}

function renderDps(it, b) {
  const box = el("div", { class: "dps" });
  let d = S.state.dps;
  const demo = (!d || !d.rows?.length) && S.mode === "edit";
  if (demo) d = DPS_DEMO;
  const extra = it.extra || "pct";
  let y = 7;
  if (b.h >= 90) {
    const rows = d?.rows?.length;
    const time = rows ? `${Math.floor(d.time / 60)}:${String(d.time % 60).padStart(2, "0")}` : "";
    box.append(el("div", { class: "hd" }, el("span", { text: d?.target || "AION 2" }), el("span", { text: rows && d.hp != null ? `${Math.round(d.hp)} % · ${time}` : time })));
    y += 15 + 3;
    if (rows && d.hp != null) box.append(el("div", { class: "hp", style: `top:${y}px` }, el("i", { style: `width:${Math.max(0, Math.min(100, d.hp))}%` })));
    y += 6;
  }
  const avail = b.h - y - 7, gap = 3;
  let n = Math.max(1, Math.min(8, it.players || 5));
  while (n > 1 && (avail - (n - 1) * gap) / n < 16) n--;
  const rowH = Math.min(Math.floor((avail - (n - 1) * gap) / n), 40);
  const font = rowH >= 34 ? "font-size:17px;font-weight:600" : `font-size:${rowH >= 20 ? 14 : 12}px`;
  const rows = (d?.rows || []).slice(0, n);
  const best = Math.max(1, ...rows.map((r) => r.dps));
  rows.forEach((r, i) => {
    const row = el("div", { class: "r" + (r.you ? " you" : ""), style: `top:${y + i * (rowH + gap)}px;height:${rowH}px;${font}` });
    row.append(el("span", { class: "b", style: `width:${Math.max(6, (100 * r.dps) / best)}%;background:${CLASS_COLORS[r.cls] || "#8E8E93"}` }));
    row.append(el("span", { class: "n", text: `${i + 1}  ${r.name}` }), el("span", { class: "v", text: fmtAmount(r.dps) }));
    if (extra !== "none") row.append(el("span", { class: "x", style: `width:${extra === "dmg" ? 58 : 44}px`, text: extra === "dmg" ? fmtAmount(r.dmg) : `${Math.round(r.pct || 0)} %` }));
    box.append(row);
  });
  if (!rows.length) box.append(el("div", { class: "msg", style: b.h >= 90 ? "top:16px" : "", text: d ? "Warte auf Kampf …" : "DPS-Meter nicht verbunden" }));
  if (demo) box.append(el("span", { class: "demo", text: "Beispieldaten" }));
  return box;
}

function onTileClick(it, idx) {
  if (S.mode === "edit") return select(idx);
  if (it.nav) {
    const p = S.layout.pages.findIndex((pg) => pg.id === it.nav);
    if (p >= 0) setPage(p);
    return;
  }
  sendEvent({ event: "button_press", item: it.id, part: it.type === "media" ? "toggle" : undefined });
}

function attachSliderTest(t, it, min, max) {
  let startX = 0, startV = 0, moved = false, last = 0;
  t.addEventListener("pointerdown", (e) => {
    if (S.mode !== "test") return;
    t.setPointerCapture(e.pointerId);
    startX = e.clientX;
    startV = Number(S.state[it.bind] ?? min);
    moved = false;
    const scale = previewScale();
    const move = (ev) => {
      const dx = (ev.clientX - startX) / scale;
      if (!moved && Math.abs(dx) > 6) moved = true;
      if (!moved) return;
      const v = Math.round(Math.max(min, Math.min(max, startV + (dx * (max - min)) / (t.offsetWidth - 12))));
      t.querySelector(".fill").style.width = `${((v - min) * 100) / (max - min)}%`;
      t.querySelector(".val").textContent = `${v}%`;
      const now = performance.now();
      if (now - last > 50) {
        last = now;
        sendEvent({ event: "slider_change", item: it.id, value: v, final: false });
      }
      t.dataset.v = v;
    };
    const up = () => {
      t.removeEventListener("pointermove", move);
      t.removeEventListener("pointerup", up);
      t.removeEventListener("pointercancel", up);
      if (moved) sendEvent({ event: "slider_change", item: it.id, value: Number(t.dataset.v), final: true });
      else if (it.long_action) sendEvent({ event: "long_press", item: it.id });
    };
    t.addEventListener("pointermove", move);
    t.addEventListener("pointerup", up);
    t.addEventListener("pointercancel", up);
  });
}

function previewScale() {
  const wrap = $("preview-wrap");
  const avail = wrap.clientWidth - 28;
  return Math.max(0.5, Math.min(2, avail / W));
}

function fitPreview() {
  const s = previewScale();
  const avail = $("preview-wrap").clientWidth - 28;
  $("preview").style.transform = `scale(${s})`;
  $("preview").style.marginLeft = `${Math.max(0, (avail - W * s) / 2)}px`;
  $("preview-wrap").style.height = `${H * s + 28}px`;
}

/* ================================================================= Seiten */
function renderTabs() {
  const tabs = $("page-tabs");
  tabs.replaceChildren(
    ...S.layout.pages.map((p, i) =>
      el("button", { class: "tab" + (i === S.page ? " on" : ""), type: "button", role: "tab", text: p.name || p.id, onclick: () => setPage(i) }),
    ),
  );
}

function setPage(i) {
  S.page = Math.max(0, Math.min(S.layout.pages.length - 1, i));
  S.sel = null;
  if (S.mode === "test") sendEvent({ event: "page_change", page: curPage().id });
  renderAll();
}

function renderPageCard() {
  const p = curPage();
  $("page-name").value = p.name || "";
  $("page-id").value = p.id;
  $("page-cols").value = p.cols || 6;
  $("page-rows").value = p.rows || 2;
  $("page-left").disabled = S.page === 0;
  $("page-right").disabled = S.page === S.layout.pages.length - 1;
  $("page-del").disabled = S.layout.pages.length === 1;
  $("accent").value = accent().toLowerCase();
  const bg = S.layout.theme?.background || "default";
  const kind = bg === "default" || bg === "wallpaper" ? bg : "file";
  $("background").value = kind;
  $("bg-file-row").hidden = kind !== "file";
  if (kind === "file" && document.activeElement !== $("bg-file")) $("bg-file").value = bg;
}

function bindPageCard() {
  $("page-name").addEventListener("input", (e) => { curPage().name = e.target.value || undefined; changed({ tabs: true }); });
  $("page-id").addEventListener("change", (e) => {
    const v = e.target.value.trim();
    const p = curPage();
    if (!ID_RE.test(v) || S.layout.pages.some((q) => q !== p && q.id === v)) { e.target.value = p.id; return toast("ID ungültig oder schon vergeben", true); }
    for (const q of S.layout.pages) for (const it of q.items) if (it.nav === p.id) it.nav = v;
    p.id = v;
    changed({ tabs: true });
  });
  $("page-cols").addEventListener("input", (e) => { curPage().cols = clampInt(e.target.value, 1, 8, 6); changed(); });
  $("page-rows").addEventListener("input", (e) => { curPage().rows = clampInt(e.target.value, 1, 3, 2); changed(); });
  $("page-add").addEventListener("click", () => {
    const id = uniqueId("seite", S.layout.pages.map((p) => p.id));
    S.layout.pages.push({ id, name: `Seite ${S.layout.pages.length + 1}`, cols: 6, rows: 2, items: [] });
    S.page = S.layout.pages.length - 1;
    S.sel = null;
    changed({ tabs: true });
  });
  $("page-del").addEventListener("click", () => {
    const p = curPage();
    if (!confirm(`Seite „${p.name || p.id}“ mit ${p.items.length} Kachel(n) löschen?`)) return;
    S.layout.pages.splice(S.page, 1);
    for (const q of S.layout.pages) for (const it of q.items) if (it.nav === p.id) delete it.nav;
    S.page = Math.max(0, S.page - 1);
    S.sel = null;
    changed({ tabs: true });
  });
  const move = (d) => {
    const ps = S.layout.pages, i = S.page, j = i + d;
    if (j < 0 || j >= ps.length) return;
    [ps[i], ps[j]] = [ps[j], ps[i]];
    S.page = j;
    changed({ tabs: true });
  };
  $("page-left").addEventListener("click", () => move(-1));
  $("page-right").addEventListener("click", () => move(1));
  $("accent").addEventListener("input", (e) => {
    S.layout.theme = { ...(S.layout.theme || {}), accent: e.target.value.toUpperCase() };
    changed();
  });
  const setBg = (v) => {
    S.layout.theme = { ...(S.layout.theme || {}), background: v || "default" };
    changed();
  };
  $("background").addEventListener("change", (e) => {
    const v = e.target.value;
    $("bg-file-row").hidden = v !== "file";
    if (v === "file") {
      $("bg-file").focus();
      if ($("bg-file").value.trim()) setBg($("bg-file").value.trim());
    } else setBg(v);
  });
  $("bg-file").addEventListener("input", (e) => { if (e.target.value.trim()) setBg(e.target.value.trim()); });
  $("bg-upload").addEventListener("click", () => $("bg-upload-input").click());
  $("bg-upload-input").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) return toast("Bild zu groß (max. 20 MB)", true);
    toast("Lade Bild hoch …");
    try {
      const r = await fetch("/api/background", { method: "POST", headers: { "Content-Type": f.type || "application/octet-stream" }, body: f });
      const j = await r.json();
      if (!r.ok) return toast(j.error || "Upload fehlgeschlagen", true);
      $("bg-file").value = j.path;
      setBg(j.path);
    } catch {
      toast("Upload fehlgeschlagen", true);
    }
  });
}

/* ================================================================= Kachel-Liste */
function renderItemList() {
  const list = $("item-list");
  const page = curPage();
  const boxes = placeItems(page);
  list.replaceChildren(
    ...page.items.map((it, i) => {
      const li = el(
        "li",
        { class: i === S.sel ? "sel" : null, draggable: "true", onclick: () => select(i) },
        el("span", { class: "ic", text: glyph(it.icon) || (it.type === "media" ? glyph("music") : it.type === "dps" ? glyph("flash") : "") }),
        el("span", { class: "nm", text: it.label || (it.type === "media" ? "Media" : it.type === "dps" ? "DPS-Meter" : it.id) }),
        boxes[i] ? el("span", { class: "meta", text: `${TYPE_NAMES[it.type || "button"]} · ${it.w || 1}×${it.h || 1}` }) : el("span", { class: "warn", text: "passt nicht" }),
      );
      li.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/plain", String(i)); li.classList.add("dragging"); });
      li.addEventListener("dragend", () => li.classList.remove("dragging"));
      li.addEventListener("dragover", (e) => {
        e.preventDefault();
        const after = e.offsetY > li.offsetHeight / 2;
        li.classList.toggle("drop-after", after);
        li.classList.toggle("drop-before", !after);
      });
      li.addEventListener("dragleave", () => li.classList.remove("drop-after", "drop-before"));
      li.addEventListener("drop", (e) => {
        e.preventDefault();
        li.classList.remove("drop-after", "drop-before");
        const from = Number(e.dataTransfer.getData("text/plain"));
        let to = i + (e.offsetY > li.offsetHeight / 2 ? 1 : 0);
        if (from === to || from + 1 === to) return;
        const items = curPage().items;
        const [moved] = items.splice(from, 1);
        if (from < to) to--;
        items.splice(to, 0, moved);
        S.sel = to;
        changed();
      });
      return li;
    }),
  );
}

function renderAddMenu() {
  const menu = $("add-menu");
  menu.replaceChildren(
    ...TEMPLATES.map((t) =>
      el("button", { type: "button", onclick: () => { addItem(t.item); menu.hidden = true; } }, el("span", { class: "ic", text: glyph(t.icon) }), t.name),
    ),
  );
}

function addItem(template) {
  const item = structuredClone(template);
  item.id = uniqueId((item.label || item.type || "item").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "item", allItemIds());
  if (item.type === "dps") {
    // ganze Seite; w/h werden ohnehin auf das Raster begrenzt
    const p = curPage();
    if ((p.cols || 6) > 1) item.w = p.cols || 6;
    if ((p.rows || 2) > 1) item.h = p.rows || 2;
  }
  if ("nav" in item) {
    const other = S.layout.pages.find((p) => p !== curPage());
    if (other) item.nav = other.id;
    else delete item.nav;
  }
  curPage().items.push(item);
  S.sel = curPage().items.length - 1;
  changed();
}

/* ================================================================= Eigenschaften */
function select(i) {
  S.sel = i;
  renderPreview();
  renderItemList();
  renderProps();
}

function field(label, input, cls) {
  return el("label", { class: cls }, label, input);
}

function input(value, onInput, attrs = {}) {
  const i = el("input", { value: value ?? "", ...attrs });
  i.addEventListener(attrs.type === "number" ? "change" : "input", () => onInput(i.value, i));
  return i;
}

function select_(options, value, onChange) {
  const s = el("select", {}, Object.entries(options).map(([k, v]) => el("option", { value: k, selected: k === value, text: v })));
  s.addEventListener("change", () => onChange(s.value));
  return s;
}

function renderProps() {
  const box = $("props");
  const it = selItem();
  if (!it) {
    box.replaceChildren(el("p", { class: "empty", text: "Keine Kachel ausgewählt. Klicke eine Kachel in der Vorschau oder in der Liste an." }));
    return;
  }
  const type = it.type || "button";
  const set = (k, v, opts) => {
    if (v === "" || v == null) delete it[k];
    else it[k] = v;
    changed(opts);
  };

  const head = el(
    "div",
    { class: "props-head" },
    el("h2", { text: "Kachel" }),
    el(
      "div",
      { class: "btns" },
      el("button", { type: "button", text: "Duplizieren", onclick: () => { const c = structuredClone(it); c.id = uniqueId(it.id, allItemIds()); curPage().items.splice(S.sel + 1, 0, c); S.sel++; changed(); } }),
      el("button", { type: "button", class: "danger", text: "Löschen", onclick: () => { curPage().items.splice(S.sel, 1); S.sel = null; changed(); } }),
    ),
  );

  const basics = el(
    "div",
    { class: "grid2" },
    field("Typ", select_(TYPE_NAMES, type, (v) => { changeType(it, v); changed({ props: true }); })),
    field("ID", input(it.id, (v, i) => {
      if (!ID_RE.test(v) || allItemIds().some((x) => x !== it.id && x === v)) { i.setCustomValidity("ungültig oder doppelt"); return; }
      i.setCustomValidity("");
      it.id = v;
      changed({ list: false });
    }, { maxlength: 32 })),
    type !== "media" && type !== "dps" ? field("Beschriftung", input(it.label, (v) => set("label", v, { list: true }), { maxlength: 24 }), "span2") : null,
    field("Breite (Zellen)", input(it.w || 1, (v) => set("w", clampInt(v, 1, 8, 1) === 1 ? undefined : clampInt(v, 1, 8, 1)), { type: "number", min: 1, max: 8 })),
    field("Höhe (Zellen)", input(it.h || 1, (v) => set("h", clampInt(v, 1, 3, 1) === 1 ? undefined : clampInt(v, 1, 3, 1)), { type: "number", min: 1, max: 3 })),
  );

  const look = el("div", { class: "section" }, el("h3", { text: "Aussehen" }));
  if (type !== "media") {
    look.append(
      el("div", { class: "grid2" },
        field("Icon", iconPicker(it.icon, (v) => set("icon", v, { list: true }))),
        type === "toggle" || type === "slider" ? field(type === "toggle" ? "Icon aktiv" : "Icon stumm", iconPicker(it.icon_on, (v) => set("icon_on", v))) : null,
      ),
    );
  }
  look.append(
    el("div", { style: "margin-top:10px" },
      el("label", {}, type === "toggle" ? "Farbe im aktiven Zustand" : "Farbe"),
      el("div", { class: "styles", style: "margin-top:6px" },
        Object.keys(STYLES).map((s) =>
          el("button", { type: "button", class: "sw" + ((it.style || "default") === s ? " on" : ""), title: STYLE_NAMES[s], style: `background:${s === "default" ? "rgba(255,255,255,.25)" : styleColor(s)}`, onclick: () => { set("style", s === "default" ? undefined : s); renderProps(); } }),
        ),
      ),
    ),
  );

  const parts = [head, basics];
  if (type === "dps") {
    const sec = el("div", { class: "section" }, el("h3", { text: "Anzeige" }));
    sec.append(el("div", { class: "grid2" },
      field("Spieler (Zeilen)", input(it.players || 5, (v) => set("players", clampInt(v, 1, 8, 5) === 5 ? undefined : clampInt(v, 1, 8, 5)), { type: "number", min: 1, max: 8 })),
      field("Neben der DPS-Zahl", select_(EXTRA_NAMES, it.extra || "pct", (v) => set("extra", v === "pct" ? undefined : v))),
    ));
    sec.append(el("p", { class: "hint small", text: "Passen nicht alle Spieler in die Kachel, zeigt sie so viele wie möglich. Die Daten kommen vom A2Tools DPS Meter, siehe Karte „AION 2 DPS-Meter“ links." }));
    parts.push(sec);
    box.replaceChildren(...parts);
    return;
  }
  parts.push(look);

  if (type === "toggle" || type === "slider") {
    const keys = type === "toggle" ? ["mic_muted", "out_muted", "playing"] : ["out_volume", "mic_volume"];
    const bindSec = el("div", { class: "section" }, el("h3", { text: "Status" }));
    const g = el("div", { class: "grid2" });
    g.append(field(type === "toggle" ? "Aktiv, wenn State-Wert wahr ist" : "Wert aus State", keyInput(it.bind, keys, (v) => set("bind", v)), "span2"));
    if (type === "slider") {
      g.append(field("Stumm-Anzeige (State)", keyInput(it.mute_bind, ["out_muted", "mic_muted"], (v) => set("mute_bind", v)), "span2"));
      g.append(field("Minimum", input(it.min ?? 0, (v) => set("min", v === "0" ? undefined : Number(v)), { type: "number" })));
      g.append(field("Maximum", input(it.max ?? 100, (v) => set("max", v === "100" ? undefined : Number(v)), { type: "number" })));
    }
    bindSec.append(g);
    parts.push(bindSec);
  }

  if (type === "button") {
    const navSec = el("div", { class: "section" }, el("h3", { text: "Seitenwechsel" }));
    const opts = { "": "— keiner —", ...Object.fromEntries(S.layout.pages.filter((p) => p !== curPage()).map((p) => [p.id, p.name || p.id])) };
    navSec.append(field("Tippen wechselt zu Seite (auf dem Gerät, ohne Aktion)", select_(opts, it.nav || "", (v) => { set("nav", v); renderProps(); })));
    parts.push(navSec);
  }

  if (!(type === "button" && it.nav)) {
    parts.push(actionEditor(type === "media" ? "Aktion beim Tippen (leer = Play/Pause)" : "Aktion beim Tippen" + (type === "slider" ? " / Ziehen" : ""), it.action, (a) => set("action", a)));
    parts.push(actionEditor("Aktion bei langem Drücken", it.long_action, (a) => set("long_action", a)));
    parts.push(
      el("div", { class: "test-row" },
        el("button", { type: "button", text: "▶ Aktion testen", onclick: () => trigger(it, "button_press") }),
        it.long_action ? el("button", { type: "button", text: "▶ Lang drücken testen", onclick: () => trigger(it, "long_press") }) : null,
      ),
    );
  }
  box.replaceChildren(...parts);
}

function changeType(it, v) {
  it.type = v === "button" ? undefined : v;
  if (!it.type) delete it.type;
  if (v === "toggle" && !it.bind) it.bind = "mic_muted";
  if (v === "slider") {
    if (!it.bind || !["out_volume", "mic_volume"].includes(it.bind)) it.bind = "out_volume";
    if (!it.action || it.action.op !== "set") it.action = { do: "volume", target: it.bind === "mic_volume" ? "source" : "sink", op: "set" };
  }
  if (v !== "toggle" && v !== "slider") { delete it.bind; delete it.mute_bind; delete it.icon_on; delete it.min; delete it.max; }
  if (v !== "slider") { delete it.mute_bind; delete it.min; delete it.max; }
  if (v !== "button") delete it.nav;
  if (v === "media") { delete it.icon; delete it.label; if (!it.h) it.h = 2; if (!it.w) it.w = 2; }
  if (v === "dps") { delete it.icon; delete it.label; delete it.style; delete it.action; delete it.long_action; }
  else { delete it.players; delete it.extra; }
}

function keyInput(value, suggestions, onChange) {
  const id = "keys-" + Math.random().toString(36).slice(2);
  const custom = Object.keys(S.state).filter((k) => !BUILTIN_KEYS.includes(k) && k !== "track");
  const wrap = el("div", {});
  const i = input(value, onChange, { list: id, placeholder: "State-Schlüssel" });
  wrap.append(i, el("datalist", { id }, [...suggestions, ...custom].map((k) => el("option", { value: k }))));
  return wrap;
}

function actionEditor(title, action, onChange) {
  const sec = el("div", { class: "section" }, el("h3", { text: title }));
  const kinds = { "": "— keine —", media: "Medien (playerctl)", volume: "Lautstärke / Mute (wpctl)", open: "Link / Datei öffnen", hotkey: "Hotkey (ydotool)", shell: "Shell-Befehl" };
  const g = el("div", { class: "grid2" });
  g.append(field("Art", select_(kinds, action?.do || "", (v) => { onChange(v ? structuredClone(ACTION_DEFAULTS[v]) : undefined); renderProps(); }), "span2"));
  if (action?.do) {
    for (const [key, kind, label, opts] of ACTION_FIELDS[action.do]) {
      if (action.do === "volume" && key === "step" && action.op !== "step") continue;
      const update = (v) => {
        const a = { ...action };
        if (v === "" || v == null) delete a[key];
        else a[key] = kind === "number" ? Number(v) : v;
        onChange(a);
      };
      let ctl;
      if (kind === "select") ctl = select_(opts, action[key] ?? Object.keys(opts)[0], (v) => { update(v); renderProps(); });
      else ctl = input(action[key], update, kind === "number" ? { type: "number" } : {});
      g.append(field(label, ctl, kind === "text" ? "span2" : null));
    }
  }
  sec.append(g);
  if (action?.do === "hotkey" && !S.status.tools?.ydotool) sec.append(el("p", { class: "hint small", text: "⚠ ydotool ist nicht installiert – Hotkeys funktionieren erst danach (und ydotoold muss laufen)." }));
  if (action?.do === "media" && !S.status.tools?.playerctl) sec.append(el("p", { class: "hint small", text: "⚠ playerctl ist nicht installiert." }));
  return sec;
}

/* ================================================================= Icon-Auswahl */
function iconPicker(value, onChange) {
  return el("div", { class: "icon-pick" },
    el("button", { type: "button", onclick: async () => { const r = await pickIcon(value); if (r !== undefined) { onChange(r || undefined); renderProps(); } } },
      el("span", { class: "ic", text: glyph(value) }),
      el("span", { text: value || "— kein —" }),
    ),
  );
}

function pickIcon(current) {
  const dlg = $("icon-dialog");
  const grid = $("icon-grid");
  const search = $("icon-search");
  return new Promise((resolve) => {
    let picked;
    const render = () => {
      const q = search.value.trim().toLowerCase();
      grid.replaceChildren(
        ...Object.keys(S.icons).filter((n) => !q || n.includes(q)).map((n) =>
          el("button", { type: "button", class: n === current ? "on" : null, title: n, onclick: () => { picked = n; dlg.close("pick"); } },
            el("span", { class: "ic", text: glyph(n) }), el("span", { class: "n", text: n })),
        ),
      );
    };
    search.value = "";
    search.oninput = render;
    render();
    dlg.onclose = () => resolve(dlg.returnValue === "none" ? "" : dlg.returnValue === "pick" ? picked : undefined);
    dlg.showModal();
    search.focus();
  });
}

/* ================================================================= Speichern / Live */
function changed(opts = {}) {
  S.dirty = true;
  renderPreview();
  renderItemList();
  renderPageCard();
  if (opts.tabs) { renderTabs(); renderDpsCard(); }
  if (opts.props !== false && opts.list !== false) renderPropsSoft();
  setSave("Änderungen …");
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(save, 350);
}

// Eigenschaften nur neu aufbauen, wenn der Fokus nicht in einem Textfeld liegt
function renderPropsSoft() {
  const a = document.activeElement;
  if (a && $("props").contains(a) && (a.tagName === "INPUT" || a.tagName === "SELECT")) return;
  renderProps();
}

async function save() {
  if (S.saving) { S.saveTimer = setTimeout(save, 200); return; }
  S.saving = true;
  const body = JSON.stringify(S.layout);
  try {
    const r = await fetch("/api/layout", { method: "PUT", headers: { "Content-Type": "application/json" }, body });
    const data = await r.json();
    if (!r.ok) {
      showError(data.error || `Fehler ${r.status}`);
      setSave("Nicht gespeichert", true);
    } else {
      S.lastSaved = body;
      S.dirty = false;
      showError(null);
      setSave("Gespeichert ✓ – live auf dem Display");
    }
  } catch (e) {
    setSave("Daemon nicht erreichbar", true);
  } finally {
    S.saving = false;
  }
}

function setSave(text, err) {
  const s = $("save-state");
  s.textContent = text;
  s.classList.toggle("err", !!err);
}

function toast(text, err) { setSave(text, err); }

function showError(text) {
  const e = $("error");
  e.hidden = !text;
  e.textContent = text ? `Layout ungültig – ${text}` : "";
}

function sendEvent(ev) {
  if (S.ws?.readyState === WebSocket.OPEN) S.ws.send(JSON.stringify({ v: 1, type: "event", ...ev }));
}

async function trigger(it, event) {
  const r = await fetch("/api/trigger", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event, item: it.id }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.error) toast(d.error || "Aktion fehlgeschlagen", true);
  else toast("Aktion ausgeführt");
}

/* Hintergrund der Vorschau = das, was der Daemon gerade an die Geräte schickt */
function setBgPreview(id) {
  $("preview").style.backgroundImage = `url("/api/background.png?v=${encodeURIComponent(id || "default")}")`;
}

function connectLive() {
  const ws = new WebSocket(`ws://${location.host}/api/live`);
  S.ws = ws;
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.type === "hello") {
      S.state = msg.state;
      S.devices = msg.devices;
      S.status = msg.status;
      S.dps = msg.dps;
      S.runs = msg.runs;
      setBgPreview(msg.status?.background?.id);
      if (!S.dirty) setLayout(msg.layout);
      showError(msg.error);
      renderChips();
      renderAll();
    } else if (msg.type === "state") {
      Object.assign(S.state, msg.values);
      renderPreview();
    } else if (msg.type === "devices") {
      S.devices = msg.devices;
      renderChips();
    } else if (msg.type === "layout") {
      // Handänderung an layout.yaml oder eigenes Speichern
      if (!S.dirty && JSON.stringify(msg.layout) !== JSON.stringify(S.layout)) {
        setLayout(msg.layout);
        renderAll();
      }
      showError(null);
    } else if (msg.type === "dps") {
      S.dps = msg.dps;
      renderDpsCard();
    } else if (msg.type === "runs") {
      S.runs = msg.runs;
      renderRunsCard();
    } else if (msg.type === "background") {
      setBgPreview(msg.id);
    } else if (msg.type === "layout_error") {
      showError(`layout.yaml: ${msg.error}`);
    } else if (msg.type === "error") {
      toast(msg.error, true);
    }
  };
  ws.onclose = () => {
    S.devices = [];
    renderChips(true);
    setTimeout(connectLive, 1500);
  };
}

function setLayout(layout) {
  S.layout = layout;
  S.page = Math.min(S.page, layout.pages.length - 1);
  if (S.sel != null && S.sel >= curPage().items.length) S.sel = null;
  S.lastSaved = JSON.stringify(layout);
}

function renderChips(offline) {
  const chips = $("chips");
  if (offline) {
    chips.replaceChildren(el("span", { class: "chip bad" }, el("span", { class: "dot" }), "Daemon nicht erreichbar"));
    return;
  }
  const devs = S.devices;
  const list = devs.length
    ? devs.map((d) => el("span", { class: "chip ok", title: `${d.model} ${d.fw} – ${d.remote}` }, el("span", { class: "dot" }), d.sim ? `Simulator (${d.remote})` : `${d.id} (${d.remote})`))
    : [el("span", { class: "chip" }, el("span", { class: "dot" }), "Kein Gerät verbunden")];
  chips.replaceChildren(...list);

  const missing = Object.entries(S.status.tools || {}).filter(([, ok]) => !ok).map(([t]) => t);
  const w = $("warnings");
  w.hidden = !missing.length;
  w.textContent = missing.length ? `Nicht installiert: ${missing.join(", ")} – die zugehörigen Aktionen/Statusanzeigen sind inaktiv.` : "";
  $("layout-path").textContent = S.status.layout_path ? `Datei: ${S.status.layout_path} (auch von Hand editierbar, wird live übernommen)` : "";
}

/* ================================================================= AION 2 DPS-Meter */
const DPS_DOT = { connected: "ok", bad_key: "bad", off: "" };

function renderDpsCard() {
  const d = S.dps;
  if (!d || !S.layout) return;
  const st = d.settings;
  const focused = document.activeElement;
  const setVal = (id, v) => { if (focused !== $(id)) $(id).value = v; };
  $("dps-enabled").checked = st.enabled;
  setVal("dps-source", st.source);
  setVal("dps-port", st.port);
  setVal("dps-key", st.key);
  setVal("dps-return", st.return_after);
  $("dps-manual").hidden = st.source !== "manual";
  const opts = { "": "— nicht wechseln —", ...Object.fromEntries(S.layout.pages.map((p) => [p.id, p.name || p.id])) };
  if (focused !== $("dps-page")) {
    $("dps-page").replaceChildren(...Object.entries(opts).map(([k, v]) => el("option", { value: k, selected: k === (st.auto_page || ""), text: v })));
  }
  $("dps-return").disabled = !st.auto_page;
  $("dps-chip").className = "chip " + (DPS_DOT[d.status] ?? "warn");
  $("dps-status").textContent = d.status_text + (d.status === "connected" && d.port ? ` (Port ${d.port})` : "");
  const hasTile = S.layout.pages.some((p) => p.items.some((i) => i.type === "dps"));
  const hint = {
    off: "",
    overlay_off: "Im A2Tools-Meter unter Einstellungen das Stream-Overlay einschalten. Port und Schlüssel liest die DeckBar dann selbst.",
    no_meter: st.source === "auto" && !d.a2tools.installed ? "Das A2Tools DPS Meter ist nicht installiert (oder hat noch keine Einstellungen gespeichert)." : "Das A2Tools DPS Meter starten. Die DeckBar verbindet sich dann von selbst.",
    connecting: "",
    bad_key: st.source === "manual" ? "Der Schlüssel passt nicht. Er steht in der Overlay-URL des Meters hinter key=." : "Der Schlüssel wurde abgelehnt. Wurde er im Meter gerade neu erzeugt? Die DeckBar versucht es gleich erneut.",
    connected: hasTile ? "" : "Für die Anzeige auf einer Seite eine Kachel „AION 2 DPS-Meter“ hinzufügen.",
  }[d.status] || "";
  $("dps-hint").textContent = (d.detail ? `(${d.detail}) ` : "") + hint;
  $("dps-hint").hidden = !$("dps-hint").textContent;
}

let dpsTimer = null;
function saveDps(patch) {
  Object.assign(S.dps.settings, patch);
  renderDpsCard();
  clearTimeout(dpsTimer);
  dpsTimer = setTimeout(async () => {
    try {
      const r = await fetch("/api/dps", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(S.dps.settings) });
      const data = await r.json();
      if (!r.ok) return toast(data.error || `Fehler ${r.status}`, true);
      S.dps = data;
      renderDpsCard();
      toast("DPS-Einstellungen gespeichert ✓");
    } catch {
      toast("Daemon nicht erreichbar", true);
    }
  }, 400);
}

function bindDpsCard() {
  $("dps-enabled").addEventListener("change", (e) => saveDps({ enabled: e.target.checked }));
  $("dps-source").addEventListener("change", (e) => saveDps({ source: e.target.value }));
  $("dps-port").addEventListener("change", (e) => saveDps({ port: clampInt(e.target.value, 1024, 65535, 18731) }));
  $("dps-key").addEventListener("change", (e) => saveDps({ key: e.target.value.trim() }));
  $("dps-page").addEventListener("change", (e) => saveDps({ auto_page: e.target.value || null }));
  $("dps-return").addEventListener("change", (e) => saveDps({ return_after: clampInt(e.target.value, 0, 600, 20) }));
}

/* ================================================================= Dungeon-Runs → Discord */
const CLASS_LABELS = { gladiator: "Gladiator", templar: "Templer", assassin: "Assassine", ranger: "Waldläufer", sorcerer: "Magier", spiritmaster: "Beschwörer", cleric: "Kleriker", chanter: "Kantor" };

// So maskiert das A2Tools-Meter (wie mask() in runs.py)
function maskName(n) {
  if (n.includes("*") || n.length < 2) return n;
  if (n.length === 2) return n[0] + "*";
  const head = n.length === 3 ? 1 : 2;
  return n.slice(0, head) + "*".repeat(Math.min(4, n.length - head - 1)) + n.slice(-1);
}

function renderRunsCard() {
  const r = S.runs;
  if (!r) return;
  const st = r.settings;
  const focused = document.activeElement;
  $("runs-enabled").checked = st.enabled;
  if (focused !== $("runs-webhook")) $("runs-webhook").value = st.webhook;
  if (focused !== $("runs-idle")) $("runs-idle").value = st.idle_minutes;
  const on = st.enabled && st.webhook;
  $("runs-chip").className = "chip " + (!r.history ? "warn" : on ? "ok" : "");
  $("runs-status").textContent = !r.history ? "keine History" : on ? (r.open_run ? "Run läuft" : "bereit") : "aus";
  const hint = [];
  if (!r.history) hint.push("Keine Kampf-History vom A2Tools-Meter gefunden.");
  else if (st.enabled && !st.webhook) hint.push("Webhook-URL fehlt: in Discord unter Kanal bearbeiten → Integrationen → Webhooks.");
  if (r.result) hint.push(r.result);
  $("runs-hint").textContent = hint.join(" ");
  $("runs-hint").hidden = !hint.length;
  // Namensliste nicht neu bauen, während jemand darin tippt
  if ($("runs-names").contains(focused)) return;
  $("runs-names").replaceChildren(...r.characters.flatMap((c) => {
    const inp = el("input", { type: "text", value: c.name, placeholder: c.seen || (c.you ? "dein Charakter" : "echter Name"), maxlength: 24, spellcheck: "false" });
    const check = () => inp.classList.toggle("bad", !!inp.value.trim() && maskName(inp.value.trim()) !== c.mask);
    inp.title = "Muss zur Maske passen: gleicher Anfang und gleiches Ende";
    check();
    inp.addEventListener("input", check);
    inp.addEventListener("change", () => {
      const names = { ...S.runs.settings.names };
      const v = inp.value.trim();
      if (v) names[c.key] = v; else delete names[c.key];
      saveRuns({ names });
    });
    return [el("span", { class: "m", text: c.mask }), el("span", { class: "c", text: `${CLASS_LABELS[c.cls] || "?"} · ${c.count}×` }), inp];
  }));
  if (!r.characters.length) $("runs-names").append(el("span", { class: "c", text: "Noch keine Dungeon-Kämpfe in der History." }));
}

let runsTimer = null;
function saveRuns(patch) {
  Object.assign(S.runs.settings, patch);
  clearTimeout(runsTimer);
  runsTimer = setTimeout(async () => {
    try {
      const r = await fetch("/api/runs", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(S.runs.settings) });
      const data = await r.json();
      if (!r.ok) return toast(data.error || `Fehler ${r.status}`, true);
      S.runs = data;
      renderRunsCard();
      toast("Discord-Einstellungen gespeichert ✓");
    } catch {
      toast("Daemon nicht erreichbar", true);
    }
  }, 300);
}

function bindRunsCard() {
  $("runs-enabled").addEventListener("change", (e) => saveRuns({ enabled: e.target.checked }));
  $("runs-webhook").addEventListener("change", (e) => saveRuns({ webhook: e.target.value.trim() }));
  $("runs-idle").addEventListener("change", (e) => saveRuns({ idle_minutes: clampInt(e.target.value, 2, 120, 15) }));
  $("runs-preview").addEventListener("click", () => window.open(`/api/runs/preview.png?t=${Date.now()}`, "_blank"));
  $("runs-test").addEventListener("click", async () => {
    $("runs-test").disabled = true;
    try {
      const r = await fetch("/api/runs/test", { method: "POST" });
      const data = await r.json();
      if (!r.ok) return toast(data.error || `Fehler ${r.status}`, true);
      S.runs = data;
      renderRunsCard();
      toast("An Discord geschickt ✓");
    } catch {
      toast("Daemon nicht erreichbar", true);
    } finally {
      $("runs-test").disabled = false;
    }
  });
}

function renderAll() {
  if (!S.layout) return;
  renderTabs();
  renderPageCard();
  renderDpsCard();
  renderRunsCard();
  renderPreview();
  renderItemList();
  renderProps();
}

/* ================================================================= Hilfen */
function clampInt(v, lo, hi, def) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : def;
}
function allItemIds() { return S.layout.pages.flatMap((p) => p.items.map((i) => i.id)); }
function uniqueId(base, taken) {
  base = base.slice(0, 28) || "item";
  if (!taken.includes(base)) return base;
  for (let n = 2; ; n++) if (!taken.includes(`${base}-${n}`)) return `${base}-${n}`;
}

/* ================================================================= Start */
async function init() {
  S.icons = await (await fetch("/static/icons.json")).json();
  await document.fonts.load('20px "mdi"').catch(() => {});
  bindPageCard();
  bindDpsCard();
  bindRunsCard();
  renderAddMenu();
  $("item-add").addEventListener("click", (e) => { e.stopPropagation(); $("add-menu").hidden = !$("add-menu").hidden; });
  document.addEventListener("click", (e) => { if (!$("add-menu").contains(e.target)) $("add-menu").hidden = true; });
  const setMode = (m) => {
    S.mode = m;
    $("mode-edit").classList.toggle("on", m === "edit");
    $("mode-test").classList.toggle("on", m === "test");
    $("mode-hint").textContent = m === "edit"
      ? "Klicke eine Kachel an, um sie zu bearbeiten. Im Modus „Testen“ lösen Klicks die echten Aktionen aus."
      : "Testmodus: Klicks und Ziehen lösen die echten Aktionen aus (wie auf dem Gerät).";
    renderPreview();
  };
  $("mode-edit").addEventListener("click", () => setMode("edit"));
  $("mode-test").addEventListener("click", () => setMode("test"));
  window.addEventListener("resize", fitPreview);
  // Erststand per REST (sofort sichtbar), danach live über den WebSocket
  try {
    const [lay, st, dps] = await Promise.all([fetch("/api/layout").then((r) => r.json()), fetch("/api/status").then((r) => r.json()), fetch("/api/dps").then((r) => r.json())]);
    S.dps = dps;
    S.state = st.state;
    S.devices = st.devices;
    S.status = st;
    setLayout(lay.layout);
    showError(lay.error);
    renderChips();
    renderAll();
  } catch {
    renderChips(true);
  }
  window.addEventListener("keydown", (e) => {
    if (e.key === "Delete" && S.sel != null && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
      curPage().items.splice(S.sel, 1);
      S.sel = null;
      changed();
    }
  });
  connectLive();
}

init();
