/* Modul Touch-Leiste: Editor mit Live-Vorschau (Seiten, Kacheln, Aktionen), Design, Geräte.
   Jede Änderung wird nach kurzer Pause gespeichert; der Daemon schickt sie sofort an alle Geräte. */
import {
  fill, $, el, icon, glyph, deckIcons, api, S, on, sendLive, toast, setSaveState, field, input as inputEl, select as selectEl,
  button, chip, callout, card, settingsRow, seg, sw, fmtAmount, fmtWhen, clampInt, CLASS_COLORS, modOn, throttle, dpsDiff,
} from "../core.js";

const W = 640, H = 172, PAD = 8, GAP = 8;
const STYLES = { default: "#ffffff", accent: null, danger: "#ff453a", success: "#30d158", warning: "#ff9f0a" };
const STYLE_NAMES = { default: "Standard", accent: "Akzent", danger: "Rot", success: "Grün", warning: "Orange" };
const TYPE_NAMES = { button: "Button", toggle: "Toggle", slider: "Slider", media: "Media", dps: "DPS-Meter", claude: "Claude-Nutzung" };
// Icon für Kacheln ohne eigenes Icon (Liste im Editor)
const TYPE_ICONS = { media: "music", dps: "flash", claude: "chart-bar" };
const BUILTIN_KEYS = ["mic_muted", "out_muted", "playing", "out_volume", "mic_volume", "art_url", "dps", "dps_active", "claude"];
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
  { name: "Befehl", icon: "console", item: { label: "Befehl", icon: "console", action: { do: "shell", cmd: "notify-send NexBoard Hallo" } } },
  { name: "Seite wechseln", icon: "chevron-right", item: { label: "Mehr", icon: "chevron-right", nav: "" } },
  { name: "AION 2 DPS-Meter", icon: "flash", item: { type: "dps" }, needs: "aion2.dps" },
  { name: "Claude-Nutzung", icon: "chart-bar", item: { type: "claude", w: 2 } },
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

/* Zustand des Editors (bleibt beim Wechsel zwischen Seiten der Web-UI erhalten) */
const D = { layout: null, page: 0, sel: null, mode: "edit", saveTimer: 0, saving: false, dirty: false, bgId: "default" };
let root = null; // Elemente des gerade sichtbaren Editors

on("layout", ({ layout }) => {
  if (!layout) return;
  // Handänderung an layout.yaml oder eigenes Speichern
  if (D.dirty || (D.layout && JSON.stringify(layout) === JSON.stringify(D.layout))) return;
  setLayout(layout);
  if (root) renderAll();
});
// Vorschau: DPS-Diffs (im Kampf 2×/s) höchstens 1×/s, alles andere (Lautstärke …) sofort
const previewSlow = throttle(() => { if (root) renderPreview(); }, 1000);
on("state", (v) => { if (!root) return; if (dpsDiff(v) && Object.keys(v).every((k) => k === "dps" || k === "dps_active")) previewSlow(); else renderPreview(); });
on("background", (id) => { D.bgId = id || "default"; if (root) setBgPreview(); });
on("hello", (msg) => { D.bgId = msg.status?.background?.id || "default"; });

const accent = () => D.layout?.theme?.accent || "#5AC8FA";
const styleColor = (s) => (s === "accent" ? accent() : STYLES[s] || "#ffffff");
const truthy = (v) => !!v && v !== 0;
const curPage = () => D.layout.pages[D.page];
const selItem = () => (D.sel == null ? null : curPage().items[D.sel]);
const g = (name) => glyph(name);

function setLayout(layout) {
  D.layout = structuredClone(layout);
  D.page = Math.min(D.page, layout.pages.length - 1);
  if (D.sel != null && D.sel >= curPage().items.length) D.sel = null;
}

/* ================================================================ Raster (wie shared-ui/src/ui.c) */
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

/* ================================================================ Vorschau */
function renderPreview() {
  if (!root || !D.layout) return;
  const pv = root.preview;
  fill(pv, );
  pv.classList.toggle("test", D.mode === "test");
  pv.style.setProperty("--daccent", accent());
  const page = curPage();
  const boxes = placeItems(page);
  page.items.forEach((it, i) => { if (boxes[i]) pv.append(renderTile(it, boxes[i], i)); });
  if (D.layout.pages.length > 1) pv.append(el("div", { class: "dots" }, D.layout.pages.map((_, i) => el("span", { class: i === D.page ? "on" : null }))));
  fitPreview();
}

function renderTile(it, b, idx) {
  const type = it.type || "button";
  const style = it.style || "default";
  const t = el("div", { class: "tile-d", style: `left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px` });
  t.style.setProperty("--c", styleColor(style));
  if (D.mode === "edit" && idx === D.sel) t.classList.add("sel");

  if (type === "button" || type === "toggle") {
    const isOn = type === "toggle" && truthy(S.state[it.bind]);
    if (type === "button" && style !== "default") t.classList.add("tint");
    if (isOn) t.classList.add("on");
    const big = b.h >= 100, row = !big && b.w >= 150;
    const ic = isOn && it.icon_on ? it.icon_on : it.icon;
    const inner = el("div", { class: "in" + (row ? " row" : "") });
    if (ic) inner.append(el("span", { class: "ic" + (big ? " big" : b.h < 60 ? " sm" : ""), text: g(ic) || g("dots-horizontal") }));
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
    const ic = muted && it.icon_on ? it.icon_on : it.icon;
    t.append(el("div", { class: "fill", style: `width:${pct}%` }));
    if (ic) t.append(el("span", { class: "ic" + (b.h < 60 ? " sm" : ""), style: `position:absolute;z-index:2;${compact ? "left:10px;top:8px" : "left:14px;top:50%;transform:translateY(-50%)"}`, text: g(ic) }));
    if (!compact && it.label && b.h >= 60) t.append(el("span", { class: "lb", style: `position:absolute;z-index:2;left:${ic ? 52 : 16}px;top:50%;transform:translateY(-50%)`, text: it.label }));
    t.append(el("span", { class: "val" + (compact ? " sm" : ""), text: `${Math.round(v)}%` }));
    attachSliderTest(t, it, min, max);
    t.addEventListener("click", () => D.mode === "edit" && select(idx));
  } else if (type === "media") {
    const tall = b.h >= 100;
    const tr = S.state.track;
    const m = el("div", { class: "media" });
    let tx = 16;
    if (tall ? b.w >= 180 : b.w >= 260) {
      m.append(el("span", { class: "ic", style: tall ? "" : `top:${(b.h - 28) / 2}px`, text: g("music-note") }));
      tx = 54;
    }
    const right = tall ? 16 : 62;
    const title = tr?.title || "Nichts läuft";
    const artist = tr?.artist || "";
    const tiY = tall ? 14 : artist ? b.h / 2 - 22 : (b.h - 23) / 2;
    m.append(el("div", { class: "ti", style: `left:${tx}px;top:${tiY}px;width:${b.w - tx - right}px;opacity:${tr?.title ? 1 : 0.59}`, text: title }));
    if (artist) m.append(el("div", { class: "ar", style: `left:${tx}px;top:${tall ? 38 : b.h / 2 + 2}px;width:${b.w - tx - right}px`, text: artist }));
    const playG = g(S.state.playing ? "pause" : "play");
    const mini = (gl, part, size) => el("span", { class: "mini", style: `width:${size}px;height:${size}px;font-size:${size >= 44 ? 28 : 20}px`, text: gl, onclick: (e) => { if (D.mode === "test") { e.stopPropagation(); sendEvent({ event: "button_press", item: it.id, part }); } } });
    if (tall) {
      m.append(el("div", { class: "bar" }, mini(g("skip-previous"), "prev", 48), mini(playG, "toggle", 58), mini(g("skip-next"), "next", 48)));
    } else {
      const p = mini(playG, "toggle", 44);
      p.style.cssText += ";position:absolute;right:12px;top:50%;transform:translateY(-50%)";
      m.append(p);
    }
    t.append(m);
    t.addEventListener("click", () => onTileClick(it, idx));
  } else if (type === "dps" || type === "claude") {
    t.append(type === "dps" ? renderDps(it, b) : renderClaude(b));
    t.addEventListener("click", () => D.mode === "edit" && select(idx));
  }
  return t;
}

function renderDps(it, b) {
  const box = el("div", { class: "dps" });
  let d = S.state.dps;
  const demo = (!d || !d.rows?.length) && D.mode === "edit";
  if (demo) d = DPS_DEMO;
  const extra = it.extra || "pct";
  let y = 7;
  if (b.h >= 90) {
    const rows = d?.rows?.length;
    const time = rows ? `${Math.floor(d.time / 60)}:${String(d.time % 60).padStart(2, "0")}` : "";
    box.append(el("div", { class: "hd" }, el("span", { text: d?.target || "AION 2" }), el("span", { text: rows && d.hp != null ? `${Math.round(d.hp)} % · ${time}` : time })));
    y += 18;
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
  if (!rows.length) box.append(el("div", { class: "msg", style: b.h >= 90 ? "top:16px" : "", text: d ? "Warte auf Kampf …" : modOn("aion2.dps") ? "DPS-Meter nicht verbunden" : "Modul DPS-Mitschnitt ist aus" }));
  if (demo) box.append(el("span", { class: "demo", text: "Beispieldaten" }));
  return box;
}

// wie build_claude in shared-ui/src/ui.c
function renderClaude(b) {
  const c = S.state.claude || {};
  const box = el("div", { class: "claude" });
  [["session", "5 h"], ["week", "Woche"]].forEach(([key, name], i) => {
    const r = c[key];
    const pct = r ? Math.max(0, Math.min(100, r.pct)) : 0;
    const color = styleColor(pct >= 90 ? "danger" : pct >= 75 ? "warning" : "accent");
    box.append(el("div", { class: "r", style: `top:${(b.h * (2 * i + 1)) / 4 - 8}px` },
      el("span", { class: "n", text: name }),
      el("span", { class: "t" }, el("i", { style: `width:${pct}%;background:${color}` })),
      el("span", { class: "p", text: r ? `${pct} %` : "–" }),
      b.w >= 260 ? el("span", { class: "x", text: r?.reset || "" }) : null));
  });
  return box;
}

function onTileClick(it, idx) {
  if (D.mode === "edit") return select(idx);
  if (it.nav) {
    const p = D.layout.pages.findIndex((pg) => pg.id === it.nav);
    if (p >= 0) setPage(p);
    return;
  }
  sendEvent({ event: "button_press", item: it.id, part: it.type === "media" ? "toggle" : undefined });
}

function attachSliderTest(t, it, min, max) {
  let startX = 0, startV = 0, moved = false, last = 0;
  t.addEventListener("pointerdown", (e) => {
    if (D.mode !== "test") return;
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
  const avail = root.wrap.clientWidth - 28;
  return Math.max(0.4, Math.min(2, avail / W));
}

function fitPreview() {
  if (!root?.wrap.isConnected) return;
  const s = previewScale();
  const avail = root.wrap.clientWidth - 28;
  root.preview.style.transform = `scale(${s})`;
  root.preview.style.marginLeft = `${Math.max(0, (avail - W * s) / 2)}px`;
  root.wrap.style.height = `${H * s + 28}px`;
}

function setBgPreview() {
  if (root) root.preview.style.backgroundImage = `url("/api/background.png?v=${encodeURIComponent(D.bgId)}")`;
}

/* ================================================================ Seiten */
function renderTabs() {
  fill(root.tabs, seg(D.layout.pages.map((p, i) => ({ id: String(i), label: p.name || p.id })), String(D.page), (i) => setPage(Number(i))));
}

function setPage(i) {
  D.page = Math.max(0, Math.min(D.layout.pages.length - 1, i));
  D.sel = null;
  if (D.mode === "test") sendEvent({ event: "page_change", page: curPage().id });
  renderAll();
}

function pageCard() {
  const p = curPage();
  const move = (d) => {
    const ps = D.layout.pages, i = D.page, j = i + d;
    if (j < 0 || j >= ps.length) return;
    [ps[i], ps[j]] = [ps[j], ps[i]];
    D.page = j;
    changed({ tabs: true });
  };
  return card("Seite", `${D.page + 1} von ${D.layout.pages.length}`, [
    button(null, () => move(-1), "sm icon", "chevron-left", { title: "Nach links", disabled: D.page === 0 }),
    button(null, () => move(1), "sm icon", "chevron-right", { title: "Nach rechts", disabled: D.page === D.layout.pages.length - 1 }),
    button(null, () => {
      if (!confirm(`Seite „${p.name || p.id}“ mit ${p.items.length} Kachel(n) löschen?`)) return;
      D.layout.pages.splice(D.page, 1);
      for (const q of D.layout.pages) for (const it of q.items) if (it.nav === p.id) delete it.nav;
      D.page = Math.max(0, D.page - 1);
      D.sel = null;
      changed({ tabs: true });
    }, "sm icon danger", "delete", { title: "Seite löschen", disabled: D.layout.pages.length === 1 }),
  ],
  el("div", { class: "grid g2" },
    field("Name", inputEl(p.name, (v) => { curPage().name = v || undefined; changed({ tabs: true, page: false }); }, { maxlength: 24 })),
    field("ID", inputEl(p.id, (v, i) => {
      v = v.trim();
      const pg = curPage();
      if (!ID_RE.test(v) || D.layout.pages.some((q) => q !== pg && q.id === v)) { i.value = pg.id; return toast("ID ungültig oder schon vergeben", true); }
      for (const q of D.layout.pages) for (const it of q.items) if (it.nav === pg.id) it.nav = v;
      pg.id = v;
      changed({ tabs: true });
    }, { maxlength: 32, lazy: true })),
    field("Spalten", inputEl(p.cols || 6, (v) => { curPage().cols = clampInt(v, 1, 8, 6); changed(); }, { type: "number", min: 1, max: 8 })),
    field("Zeilen", inputEl(p.rows || 2, (v) => { curPage().rows = clampInt(v, 1, 3, 2); changed(); }, { type: "number", min: 1, max: 3 }))),
  el("div", { style: "margin-top:14px" }, button("Neue Seite", () => {
    const id = uniqueId("seite", D.layout.pages.map((q) => q.id));
    D.layout.pages.push({ id, name: `Seite ${D.layout.pages.length + 1}`, cols: 6, rows: 2, items: [] });
    D.page = D.layout.pages.length - 1;
    D.sel = null;
    changed({ tabs: true });
  }, "", "plus")));
}

/* ================================================================ Kachel-Liste */
function itemsCard() {
  const menu = el("div", { class: "menu", hidden: true }, TEMPLATES.filter((t) => !t.needs || modOn(t.needs)).map((t) =>
    el("button", { type: "button", onclick: () => { addItem(t.item); menu.hidden = true; } }, el("span", { class: "ic", text: g(t.icon) }), t.name)));
  const add = button("Hinzufügen", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; }, "primary sm", "plus");
  const closer = (e) => { if (!menu.contains(e.target)) menu.hidden = true; };
  document.addEventListener("click", closer);
  root.cleanup.push(() => document.removeEventListener("click", closer));
  root.list = el("ol", { class: "items" });
  return card("Kacheln", "Reihenfolge per Ziehen", el("div", { class: "add-wrap" }, add, menu),
    root.list, el("p", { class: "hint small", style: "margin-top:12px", text: "Kacheln werden zeilenweise in die erste freie Lücke gesetzt. Entf löscht die ausgewählte." }));
}

function renderItemList() {
  const list = root.list;
  const page = curPage();
  const boxes = placeItems(page);
  fill(list, ...page.items.map((it, i) => {
    const li = el("li", { class: i === D.sel ? "sel" : null, draggable: "true", onclick: () => select(i) },
      el("span", { class: "ic", text: g(it.icon) || g(TYPE_ICONS[it.type]) || "" }),
      el("span", { class: "nm", text: it.label || (TYPE_ICONS[it.type] ? TYPE_NAMES[it.type] : it.id) }),
      boxes[i] ? el("span", { class: "meta", text: `${TYPE_NAMES[it.type || "button"]} · ${it.w || 1}×${it.h || 1}` }) : el("span", { class: "warn", text: "passt nicht" }));
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
      D.sel = to;
      changed();
    });
    return li;
  }));
  if (!page.items.length) list.append(el("li", { class: "faint", style: "cursor:default", text: "Noch keine Kacheln – oben auf „Hinzufügen“." }));
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
    const other = D.layout.pages.find((p) => p !== curPage());
    if (other) item.nav = other.id;
    else delete item.nav;
  }
  curPage().items.push(item);
  D.sel = curPage().items.length - 1;
  changed();
}

/* ================================================================ Eigenschaften */
function select(i) {
  D.sel = i;
  renderPreview();
  renderItemList();
  renderProps();
}

function renderProps() {
  const box = root.props;
  const it = selItem();
  if (!it) {
    fill(box, el("div", { class: "props-empty" }, el("span", { class: "ic", style: "font-size:40px;display:block;margin-bottom:10px", text: g("gesture-tap") }),
      "Keine Kachel ausgewählt. Klicke eine Kachel in der Vorschau oder in der Liste an."));
    return;
  }
  const type = it.type || "button";
  const set = (k, v, opts) => {
    if (v === "" || v == null) delete it[k];
    else it[k] = v;
    changed(opts);
  };

  const head = el("div", { class: "card-head" }, el("h2", { text: "Kachel" }),
    el("div", { class: "row" },
      button("Duplizieren", () => { const c = structuredClone(it); c.id = uniqueId(it.id, allItemIds()); curPage().items.splice(D.sel + 1, 0, c); D.sel++; changed(); }, "sm", "content-copy"),
      button("Löschen", () => { curPage().items.splice(D.sel, 1); D.sel = null; changed(); }, "sm danger", "delete")));

  const basics = el("div", { class: "grid g2" },
    field("Typ", selectEl(TYPE_NAMES, type, (v) => { changeType(it, v); changed({ props: true }); })),
    field("ID", inputEl(it.id, (v, i) => {
      if (!ID_RE.test(v) || allItemIds().some((x) => x !== it.id && x === v)) { i.setCustomValidity("ungültig oder doppelt"); return; }
      i.setCustomValidity("");
      it.id = v;
      changed({ props: false });
    }, { maxlength: 32 })),
    !TYPE_ICONS[type] ? field("Beschriftung", inputEl(it.label, (v) => set("label", v, { props: false }), { maxlength: 24 }), null, "span-all") : null,
    field("Breite (Zellen)", inputEl(it.w || 1, (v) => set("w", clampInt(v, 1, 8, 1) === 1 ? undefined : clampInt(v, 1, 8, 1)), { type: "number", min: 1, max: 8 })),
    field("Höhe (Zellen)", inputEl(it.h || 1, (v) => set("h", clampInt(v, 1, 3, 1) === 1 ? undefined : clampInt(v, 1, 3, 1)), { type: "number", min: 1, max: 3 })));

  const parts = [head, basics];
  if (type === "dps") {
    parts.push(el("div", { class: "section" }, el("h3", { text: "Anzeige" }),
      el("div", { class: "grid g2" },
        field("Spieler (Zeilen)", inputEl(it.players || 5, (v) => set("players", clampInt(v, 1, 8, 5) === 5 ? undefined : clampInt(v, 1, 8, 5)), { type: "number", min: 1, max: 8 })),
        field("Neben der DPS-Zahl", selectEl(EXTRA_NAMES, it.extra || "pct", (v) => set("extra", v === "pct" ? undefined : v)))),
      el("p", { class: "hint small", style: "margin-top:10px", text: "Passen nicht alle Spieler in die Kachel, zeigt sie so viele wie möglich. Die Daten kommen vom Modul „AION 2 · DPS-Mitschnitt“." })));
    fill(box, ...parts);
    return;
  }
  if (type === "claude") {
    parts.push(el("p", { class: "hint small", style: "margin-top:14px", text: "Zeigt die Auslastung deines Claude-Abos (5-Stunden-Sitzung und Woche) wie /usage in Claude Code. Der Daemon liest dafür die Anmeldung von Claude Code auf diesem Rechner und fragt alle 5 Minuten nach." }));
    fill(box, ...parts);
    return;
  }

  const look = el("div", { class: "section" }, el("h3", { text: "Aussehen" }));
  if (type !== "media") {
    look.append(el("div", { class: "grid g2" },
      field("Icon", iconPicker(it.icon, (v) => set("icon", v))),
      type === "toggle" || type === "slider" ? field(type === "toggle" ? "Icon aktiv" : "Icon stumm", iconPicker(it.icon_on, (v) => set("icon_on", v))) : null));
  }
  look.append(el("div", { style: "margin-top:14px" },
    el("div", { class: "faint small", style: "margin-bottom:8px;font-weight:600", text: type === "toggle" ? "Farbe im aktiven Zustand" : "Farbe" }),
    el("div", { class: "styles" }, Object.keys(STYLES).map((s) =>
      el("button", { type: "button", class: "sw" + ((it.style || "default") === s ? " on" : ""), title: STYLE_NAMES[s], style: `background:${s === "default" ? "rgba(128,128,128,.35)" : styleColor(s)}`, onclick: () => { set("style", s === "default" ? undefined : s); renderProps(); } })))));
  parts.push(look);

  if (type === "toggle" || type === "slider") {
    const keys = type === "toggle" ? ["mic_muted", "out_muted", "playing"] : ["out_volume", "mic_volume"];
    const gr = el("div", { class: "grid g2" },
      field(type === "toggle" ? "Aktiv, wenn State-Wert wahr ist" : "Wert aus State", keyInput(it.bind, keys, (v) => set("bind", v)), null, "span-all"));
    if (type === "slider") {
      gr.append(field("Stumm-Anzeige (State)", keyInput(it.mute_bind, ["out_muted", "mic_muted"], (v) => set("mute_bind", v)), null, "span-all"));
      gr.append(field("Minimum", inputEl(it.min ?? 0, (v) => set("min", v === "0" ? undefined : Number(v)), { type: "number" })));
      gr.append(field("Maximum", inputEl(it.max ?? 100, (v) => set("max", v === "100" ? undefined : Number(v)), { type: "number" })));
    }
    parts.push(el("div", { class: "section" }, el("h3", { text: "Status" }), gr));
  }

  if (type === "button") {
    const opts = { "": "— keiner —", ...Object.fromEntries(D.layout.pages.filter((p) => p !== curPage()).map((p) => [p.id, p.name || p.id])) };
    parts.push(el("div", { class: "section" }, el("h3", { text: "Seitenwechsel" }),
      field("Tippen wechselt zu Seite (auf dem Gerät, ohne Aktion)", selectEl(opts, it.nav || "", (v) => { set("nav", v); renderProps(); }))));
  }

  if (!(type === "button" && it.nav)) {
    parts.push(actionEditor(type === "media" ? "Aktion beim Tippen (leer = Play/Pause)" : "Aktion beim Tippen" + (type === "slider" ? " / Ziehen" : ""), it.action, (a) => set("action", a)));
    parts.push(actionEditor("Aktion bei langem Drücken", it.long_action, (a) => set("long_action", a)));
    parts.push(el("div", { class: "row wrap", style: "margin-top:16px" },
      button("Aktion testen", () => trigger(it, "button_press"), "", "play"),
      it.long_action ? button("Lang drücken testen", () => trigger(it, "long_press"), "", "play") : null));
  }
  fill(box, ...parts);
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
  if (v === "dps" || v === "claude") { delete it.icon; delete it.label; delete it.style; delete it.action; delete it.long_action; }
  if (v !== "dps") { delete it.players; delete it.extra; }
}

function keyInput(value, suggestions, onChange) {
  const id = "keys-" + Math.random().toString(36).slice(2);
  const custom = Object.keys(S.state).filter((k) => !BUILTIN_KEYS.includes(k) && k !== "track");
  return el("div", {}, inputEl(value, onChange, { list: id, placeholder: "State-Schlüssel" }),
    el("datalist", { id }, [...suggestions, ...custom].map((k) => el("option", { value: k }))));
}

function actionEditor(title, action, onChange) {
  const kinds = { "": "— keine —", media: "Medien (playerctl)", volume: "Lautstärke / Mute (wpctl)", open: "Link / Datei öffnen", hotkey: "Hotkey (ydotool)", shell: "Shell-Befehl" };
  const gr = el("div", { class: "grid g2" },
    field("Art", selectEl(kinds, action?.do || "", (v) => { onChange(v ? structuredClone(ACTION_DEFAULTS[v]) : undefined); renderProps(); }), null, "span-all"));
  if (action?.do) {
    for (const [key, kind, label, opts] of ACTION_FIELDS[action.do]) {
      if (action.do === "volume" && key === "step" && action.op !== "step") continue;
      const update = (v) => {
        const a = { ...action };
        if (v === "" || v == null) delete a[key];
        else a[key] = kind === "number" ? Number(v) : v;
        onChange(a);
      };
      const ctl = kind === "select"
        ? selectEl(opts, action[key] ?? Object.keys(opts)[0], (v) => { update(v); renderProps(); })
        : inputEl(action[key], update, kind === "number" ? { type: "number" } : {});
      gr.append(field(label, ctl, null, kind === "text" ? "span-all" : ""));
    }
  }
  const sec = el("div", { class: "section" }, el("h3", { text: title }), gr);
  if (action?.do === "hotkey" && !S.status.tools?.ydotool) sec.append(el("p", { class: "hint small", style: "margin-top:10px", text: "ydotool ist nicht installiert – Hotkeys funktionieren erst danach (und ydotoold muss laufen)." }));
  if (action?.do === "media" && !S.status.tools?.playerctl) sec.append(el("p", { class: "hint small", style: "margin-top:10px", text: "playerctl ist nicht installiert." }));
  return sec;
}

/* ================================================================ Icon-Auswahl */
function iconPicker(value, onChange) {
  return el("div", { class: "icon-pick" },
    el("button", { type: "button", class: "btn", onclick: async () => { const r = await pickIcon(value); if (r !== undefined) { onChange(r || undefined); renderProps(); } } },
      el("span", { class: "ic", text: g(value) }), el("span", { text: value || "— kein —" })));
}

function pickIcon(current) {
  const dlg = $("icon-dialog");
  const grid = $("icon-grid");
  const search = $("icon-search");
  return new Promise((resolve) => {
    let picked;
    const draw = () => {
      const q = search.value.trim().toLowerCase();
      fill(grid, ...Object.keys(deckIcons()).filter((n) => !q || n.includes(q)).map((n) =>
        el("button", { type: "button", class: n === current ? "on" : null, title: n, onclick: () => { picked = n; dlg.close("pick"); } },
          el("span", { class: "ic", text: g(n) }), el("span", { class: "n", text: n }))));
    };
    search.value = "";
    search.oninput = draw;
    draw();
    dlg.onclose = () => resolve(dlg.returnValue === "none" ? "" : dlg.returnValue === "pick" ? picked : undefined);
    dlg.showModal();
    search.focus();
  });
}

/* ================================================================ Speichern / Live */
function changed(opts = {}) {
  D.dirty = true;
  renderPreview();
  renderItemList();
  if (opts.tabs) renderTabs();
  if (opts.page !== false) renderPageSoft();
  if (opts.props !== false) renderPropsSoft();
  setSaveState("Änderungen …");
  clearTimeout(D.saveTimer);
  D.saveTimer = setTimeout(save, 350);
}

// Karten nur neu aufbauen, wenn der Fokus nicht in einem ihrer Eingabefelder liegt
function focusedIn(box) {
  const a = document.activeElement;
  return a && box.contains(a) && (a.tagName === "INPUT" || a.tagName === "SELECT" || a.tagName === "TEXTAREA");
}
function renderPropsSoft() { if (!focusedIn(root.props)) renderProps(); }
function renderPageSoft() { if (!focusedIn(root.page)) fill(root.page, pageCard()); }

async function save() {
  if (D.saving) { D.saveTimer = setTimeout(save, 200); return; }
  D.saving = true;
  const layout = structuredClone(D.layout);
  try {
    await api("PUT", "/api/layout", layout);
    D.dirty = false;
    S.layoutError = null;
    setSaveState("Gespeichert ✓ – live auf dem Display");
  } catch (e) {
    setSaveState("Nicht gespeichert", true);
    toast(e.message, true);
  } finally {
    D.saving = false;
  }
}

function sendEvent(ev) { sendLive({ v: 1, type: "event", ...ev }); }

async function trigger(it, event) {
  try {
    const d = await api("POST", "/api/trigger", { event, item: it.id });
    if (d.error) toast(d.error, true); else toast("Aktion ausgeführt");
  } catch (e) { toast(e.message, true); }
}

/* ================================================================ Hilfen */
function allItemIds() { return D.layout.pages.flatMap((p) => p.items.map((i) => i.id)); }
function uniqueId(base, taken) {
  base = base.slice(0, 28) || "item";
  if (!taken.includes(base)) return base;
  for (let n = 2; ; n++) if (!taken.includes(`${base}-${n}`)) return `${base}-${n}`;
}

function renderAll() {
  if (!root || !D.layout) return;
  renderTabs();
  fill(root.page, pageCard());
  renderPreview();
  renderItemList();
  renderProps();
}

/* ================================================================ Tabs */
function editorTab(ctx) {
  const wrap = el("div", { class: "preview-wrap" });
  const preview = el("div", { class: "preview" });
  wrap.append(preview);
  const modeSeg = el("div");
  const hint = el("p", { class: "hint small stage-hint" });
  const drawMode = () => {
    fill(modeSeg, seg([{ id: "edit", label: "Bearbeiten", icon: "pencil" }, { id: "test", label: "Testen", icon: "gesture-tap" }], D.mode, (m) => { D.mode = m; drawMode(); renderPreview(); }));
    hint.textContent = D.mode === "edit"
      ? "Klicke eine Kachel an, um sie zu bearbeiten. Im Modus „Testen“ lösen Klicks die echten Aktionen aus."
      : "Testmodus: Klicks und Ziehen lösen die echten Aktionen aus (wie auf dem Gerät).";
  };
  drawMode();
  root = { wrap, preview, tabs: el("div", { class: "page-tabs" }), page: el("div"), props: el("section", { class: "card glass" }), list: null, cleanup: [] };
  const items = itemsCard();
  const view = el("div", { class: "stack" },
    el("section", { class: "card glass deck-stage" }, el("div", { class: "stage-bar" }, root.tabs, modeSeg), wrap, hint),
    el("div", { class: "cols side" }, el("div", { class: "stack" }, root.page, items), root.props));
  const onResize = () => fitPreview();
  addEventListener("resize", onResize);
  const onKey = (e) => {
    if (e.key === "Delete" && D.sel != null && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
      curPage().items.splice(D.sel, 1);
      D.sel = null;
      changed();
    }
  };
  addEventListener("keydown", onKey);
  ctx.onUnmount(() => {
    removeEventListener("resize", onResize);
    removeEventListener("keydown", onKey);
    for (const fn of root?.cleanup || []) fn();
    root = null;
  });
  setBgPreview();
  if (D.layout) requestAnimationFrame(renderAll);
  else api("GET", "/api/layout").then((r) => { setLayout(r.layout); S.layoutError = r.error; renderAll(); });
  return view;
}

function designTab(ctx) {
  const box = el("div", { class: "cols" });
  const draw = () => {
    if (!D.layout) return;
    const theme = D.layout.theme || {};
    const bg = theme.background || "default";
    const kind = bg === "default" || bg === "wallpaper" ? bg : "file";
    const setTheme = (patch) => {
      D.layout.theme = { ...(D.layout.theme || {}), ...patch };
      D.dirty = true;
      setSaveState("Änderungen …");
      clearTimeout(D.saveTimer);
      D.saveTimer = setTimeout(save, 350);
    };
    const fileRow = el("div", { class: "stack", hidden: kind !== "file" },
      button("Bild hochladen …", () => upload.click(), "", "upload"),
      field("oder Pfad", inputEl(kind === "file" ? bg : "", (v) => v.trim() && setTheme({ background: v.trim() }), { placeholder: "/home/…/bild.jpg", spellcheck: "false", lazy: true })));
    const upload = el("input", { type: "file", accept: "image/*", hidden: true, onchange: async (e) => {
      const f = e.target.files[0];
      e.target.value = "";
      if (!f) return;
      if (f.size > 20 * 1024 * 1024) return toast("Bild zu groß (max. 20 MB)", true);
      setSaveState("Lade Bild hoch …");
      try {
        const r = await fetch("/api/background", { method: "POST", headers: { "Content-Type": f.type || "application/octet-stream" }, body: f });
        const j = await r.json();
        if (!r.ok) return toast(j.error || "Upload fehlgeschlagen", true);
        setTheme({ background: j.path });
        draw();
      } catch { toast("Upload fehlgeschlagen", true); }
    } });
    const accentIn = el("input", { type: "color" });
    accentIn.value = (theme.accent || "#5AC8FA").toLowerCase();
    accentIn.addEventListener("input", () => setTheme({ accent: accentIn.value.toUpperCase() }));
    const prev = el("img", { class: "preview-img", alt: "Hintergrund der Leiste", src: `/api/background.png?v=${encodeURIComponent(D.bgId)}` });
    const off = on("background", () => { prev.src = `/api/background.png?v=${encodeURIComponent(D.bgId)}`; });
    ctx.onUnmount(off);
    fill(box,
      card("Farben", "Akzent für Slider, Media und eigene Zeile", null,
        settingsRow("Akzentfarbe", theme.accent || "#5AC8FA", accentIn)),
      card("Hintergrund", "Wird auf 640 × 172 zugeschnitten, weichgezeichnet und abgedunkelt", null,
        el("div", { class: "stack" },
          prev,
          field("Quelle", selectEl({ default: "Standard", wallpaper: "Desktop-Hintergrund (folgt automatisch)", file: "Eigenes Bild" }, kind, (v) => {
            if (v === "file") { fileRow.hidden = false; return; }
            setTheme({ background: v });
            draw();
          })),
          fileRow, upload)));
  };
  draw();
  if (!D.layout) api("GET", "/api/layout").then((r) => { setLayout(r.layout); draw(); });
  return box;
}

function devicesTab(ctx) {
  const box = el("div", { class: "stack" });
  const draw = () => {
    const devs = S.devices || [];
    fill(box,
      card("Verbundene Geräte", devs.length ? `${devs.length} verbunden` : "Keins verbunden", null,
        devs.length ? el("table", { class: "list" },
          el("thead", {}, el("tr", {}, ["Gerät", "Modell", "Firmware", "Adresse", "Seite", "Seit"].map((h) => el("th", { text: h })))),
          el("tbody", {}, devs.map((d) => el("tr", {},
            el("td", {}, el("b", { text: d.sim ? "Simulator" : d.id })), el("td", { text: d.model || "–" }), el("td", { text: d.fw || "–" }),
            el("td", { class: "mono", text: d.remote }), el("td", { text: d.page || "–" }), el("td", { text: fmtWhen(d.connected_at) })))))
          : el("div", { class: "empty" }, icon("tablet"), "Kein Gerät verbunden.", el("p", { class: "hint small", text: "Die Leiste verbindet sich per WLAN (mDNS) oder USB-Kabel. Der Simulator: simulator/build/deckbar-sim." }))),
      card("Layout-Datei", null, null,
        el("p", { class: "hint", text: `${S.status.layout_path || "layout.yaml"} – auch von Hand editierbar, Änderungen werden live übernommen.` })));
  };
  ctx.onUnmount(on("devices", draw));
  draw();
  return box;
}

export default {
  tabs: [
    { id: "editor", label: "Editor", icon: "view-dashboard-outline" },
    { id: "design", label: "Design", icon: "palette" },
    { id: "devices", label: "Geräte", icon: "tablet" },
  ],
  status: () => (S.devices.length ? "" : "off"),
  card() {
    const devs = S.devices.length;
    const pages = D.layout?.pages.length ?? S.modules?.modules.find((m) => m.id === "deck")?.status?.pages ?? 0;
    return el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "metric" }, el("b", { text: String(devs) }), el("span", { text: devs === 1 ? "Gerät verbunden" : "Geräte verbunden" })),
      el("div", { class: "row wrap", style: "gap:6px" }, chip(`${pages} Seite${pages === 1 ? "" : "n"}`), S.state.track?.title ? chip(`♪ ${S.state.track.title}`, "info") : null));
  },
  render(tab, ctx) {
    if (tab === "design") return designTab(ctx);
    if (tab === "devices") return devicesTab(ctx);
    return editorTab(ctx);
  },
};
