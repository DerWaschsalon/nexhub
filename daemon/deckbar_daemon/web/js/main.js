/* Web-UI: Gerüst (Seitenleiste, Kopfzeile), Router, Dashboard, Modulverwaltung, Einstellungen.
   Jedes Modul hat eine eigene Datei in js/modules/ (Tabs, Dashboard-Karte, Seiten). */
import {
  fill, $, el, icon, glyph, api, S, on, emit, connectLive, loadIcons, mod, modOn, setModule, modIcon, toast,
  setSaveState, sw, field, input, select, button, chip, callout, card, settingsRow, seg, fmtWhen,
} from "./core.js";
import deck from "./modules/deck.js";
import dps from "./modules/aion2-dps.js";
import overlay from "./modules/aion2-overlay.js";
import runs from "./modules/aion2-runs.js";
import bot from "./modules/discord-bot.js";
import updates from "./modules/updates.js";

export const BRAND = "DeckBar";
const UI = { deck, "aion2.dps": dps, "aion2.overlay": overlay, "aion2.runs": runs, "discord.bot": bot, updates };
const SYSTEM = [
  { id: "modules", name: "Module", icon: "puzzle" },
  { id: "settings", name: "Einstellungen", icon: "cog" },
];

let unmount = [];
let route = { page: "dashboard", tab: null };

/* ================================================================ Router */
function parseHash() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (!parts.length) return { page: "dashboard", tab: null };
  return { page: parts[0], tab: parts[1] || null };
}

export function go(page, tab) {
  location.hash = `#/${page === "dashboard" ? "" : encodeURIComponent(page) + (tab ? `/${encodeURIComponent(tab)}` : "")}`;
}

function render() {
  for (const fn of unmount) { try { fn(); } catch (e) { console.error(e); } }
  unmount = [];
  route = parseHash();
  document.body.classList.remove("nav-open");
  const ctx = { onUnmount: (fn) => unmount.push(fn), go };
  const view = $("view");
  let content, title, crumb, tabs = null;
  if (route.page === "dashboard") {
    title = "Übersicht";
    crumb = BRAND;
    content = dashboard(ctx);
  } else if (route.page === "modules") {
    title = "Module";
    crumb = "System";
    content = modulesPage(ctx);
  } else if (route.page === "settings") {
    title = "Einstellungen";
    crumb = "System";
    content = settingsPage(ctx);
  } else if (UI[route.page] && mod(route.page)) {
    const m = mod(route.page);
    const ui = UI[route.page];
    title = m.name;
    crumb = S.modules.categories[m.category] || "Module";
    const tab = ui.tabs.some((t) => t.id === route.tab) ? route.tab : ui.tabs[0].id;
    if (ui.tabs.length > 1) tabs = seg(ui.tabs, tab, (id) => go(m.id, id));
    content = m.enabled ? ui.render(tab, { ...ctx, m }) : disabledPage(m);
  } else {
    title = "Nicht gefunden";
    crumb = BRAND;
    content = el("div", { class: "empty glass card" }, icon("alert-circle"), "Diese Seite gibt es nicht.", el("p", {}, button("Zur Übersicht", () => go("dashboard"), "primary")));
  }
  $("crumb").textContent = crumb;
  $("title").textContent = title;
  document.title = `${title} · ${BRAND}`;
  $("tabs").replaceChildren(...(tabs ? [tabs] : []));
  fill(view, el("div", { class: "view" }, content));
  renderNav();
  window.scrollTo({ top: 0 });
}

function disabledPage(m) {
  return el("div", { class: "stack" }, card(null, null, null,
    el("div", { class: "row", style: "align-items:flex-start;gap:18px" }, modIcon(m, "off"),
      el("div", { class: "stack", style: "flex:1;gap:8px" },
        el("h2", { style: "margin:0;font-size:18px", text: `${m.name} ist ausgeschaltet` }),
        el("p", { class: "hint", text: m.summary }),
        m.requires.length ? el("p", { class: "hint small", text: `Schaltet mit ein: ${m.requires.map((r) => mod(r)?.name || r).join(", ")}` }) : null,
        el("div", {}, button("Modul einschalten", async () => { await setModule(m.id, true).catch((e) => toast(e.message, true)); render(); }, "primary", "power"))))));
}

/* ================================================================ Seitenleiste */
function badgeFor(m) {
  if (!m.enabled) return null;
  const st = UI[m.id]?.status?.(m);
  if (!st) return null;
  return el("span", { class: `badge ${st}`, title: st });
}

function renderNav() {
  const nav = $("nav");
  if (!S.modules) return;
  const link = (id, name, ic, extra) => el("a", { href: `#/${id === "dashboard" ? "" : id}`, class: route.page === id ? "on" : "" }, icon(ic), el("span", { class: "t", text: name }), extra);
  const items = [link("dashboard", "Übersicht", "view-dashboard")];
  for (const [cat, label] of Object.entries(S.modules.categories)) {
    if (cat === "system") continue;
    const mods = S.modules.modules.filter((m) => m.category === cat && m.enabled);
    if (!mods.length) continue;
    items.push(el("h6", { text: label }));
    for (const m of mods) items.push(link(m.id, m.name.replace(/^AION 2 · /, ""), m.icon, badgeFor(m)));
  }
  items.push(el("h6", { text: "System" }));
  for (const m of S.modules.modules.filter((x) => x.category === "system" && x.enabled)) items.push(link(m.id, m.name, m.icon, badgeFor(m)));
  for (const s of SYSTEM) items.push(link(s.id, s.name, s.icon));
  fill(nav, ...items);
}

/* ================================================================ Dashboard */
function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Gute Nacht" : h < 11 ? "Guten Morgen" : h < 17 ? "Hallo" : h < 22 ? "Guten Abend" : "Gute Nacht";
}

function dashboard(ctx) {
  const box = el("div");
  const draw = () => {
    if (!S.modules) { fill(box, el("div", { class: "empty" }, icon("connection"), "Verbinde mit dem Daemon …")); return; }
    const enabled = S.modules.modules.filter((m) => m.enabled);
    const off = S.modules.modules.filter((m) => !m.enabled);
    const parts = [];
    const devs = S.devices.length;
    parts.push(el("div", { class: "hero" },
      el("div", {}, el("h2", { text: greeting() }), el("p", { text: `${enabled.length} von ${S.modules.modules.length} Modulen aktiv · ${S.settings?.settings?.name || BRAND}` })),
      el("div", { class: "row wrap" },
        modOn("deck") ? chip(devs ? `${devs} Gerät${devs === 1 ? "" : "e"} verbunden` : "Kein Gerät verbunden", devs ? "ok" : "") : null,
        S.updates?.available ? el("a", { href: "#/updates", class: "chip info", style: "text-decoration:none" }, el("span", { class: "dot" }), "Update verfügbar") : null)));
    for (const [cat, label] of Object.entries(S.modules.categories)) {
      const mods = enabled.filter((m) => m.category === cat);
      if (!mods.length) continue;
      parts.push(el("div", { class: "section-title", text: label }));
      parts.push(el("div", { class: "cards" }, mods.map((m) => tile(m))));
    }
    if (off.length) {
      parts.push(el("div", { class: "section-title", text: "Weitere Module" }));
      parts.push(el("div", { class: "cards" }, off.map((m) => el("div", { class: "tile glass", onclick: (e) => { if (!e.target.closest(".switch")) go(m.id); } },
        el("div", { class: "tile-head" }, modIcon(m, "off"), el("div", { class: "t" }, el("b", { text: m.name }), el("small", { text: S.modules.categories[m.category] })),
          sw(false, (v) => setModule(m.id, v).catch((e) => toast(e.message, true)), { title: "Einschalten" })),
        el("div", { class: "body" }, el("span", { text: m.summary }))))));
    }
    fill(box, ...parts);
  };
  let frame = 0;
  const soon = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; draw(); }); };
  for (const t of ["hello", "modules", "devices", "state", "dps", "runs", "updates", "bot", "overlay", "settings", "online"]) ctx.onUnmount(on(t, soon));
  draw();
  return box;
}

function tile(m) {
  const ui = UI[m.id];
  return el("a", { class: "tile glass", href: `#/${m.id}` },
    el("div", { class: "tile-head" }, modIcon(m), el("div", { class: "t" }, el("b", { text: m.name }), el("small", { text: m.tags.join(" · ") })), icon("chevron-right", "faint")),
    el("div", { class: "body" }, ui?.card ? ui.card(m) : null));
}

/* ================================================================ Module verwalten */
function modulesPage(ctx) {
  const box = el("div", { class: "stack" });
  const draw = () => {
    if (!S.modules) return;
    const sections = Object.entries(S.modules.categories).map(([cat, label]) => {
      const mods = S.modules.modules.filter((m) => m.category === cat);
      if (!mods.length) return null;
      return card(label, null, null, el("div", {}, mods.map((m) => el("div", { class: "mod-row" },
        modIcon(m, m.enabled ? "" : "off"),
        el("div", { class: "txt" },
          el("div", { class: "row", style: "gap:8px" }, el("b", { text: m.name }), m.enabled ? chip("aktiv", "ok") : null),
          el("p", { text: m.summary }),
          el("div", { class: "tags" }, m.tags.map((t) => el("span", { class: "tag", text: t })),
            m.requires.length ? el("span", { class: "tag", text: `braucht ${m.requires.map((r) => mod(r)?.name || r).join(", ")}` }) : null)),
        m.enabled ? button(null, () => go(m.id), "ghost icon", "chevron-right", { title: "Öffnen" }) : null,
        sw(m.enabled, async (v, inp) => {
          if (!v && m.dependents.some(modOn)) {
            const deps = m.dependents.filter(modOn).map((d) => mod(d).name).join(", ");
            if (!confirm(`${m.name} ausschalten? Damit gehen auch aus: ${deps}`)) { inp.checked = true; return; }
          }
          try { await setModule(m.id, v); } catch (e) { inp.checked = !v; toast(e.message, true); }
        }, { "aria-label": `${m.name} ein/aus` })))));
    });
    fill(box,
      callout("info", "puzzle", el("span", {}, "Jedes Modul lässt sich einzeln ein- und ausschalten, ohne Neustart. Ausgeschaltete Module laufen nicht im Hintergrund und verschwinden aus der Seitenleiste. Abhängige Module werden mitgeschaltet.")),
      ...sections.filter(Boolean));
  };
  ctx.onUnmount(on("modules", draw));
  draw();
  return box;
}

/* ================================================================ Einstellungen */
function settingsPage(ctx) {
  const box = el("div", { class: "stack" });
  let restartNeeded = [];
  const save = async (patch) => {
    setSaveState("Speichere …");
    try {
      const res = await api("PUT", "/api/settings", patch);
      S.settings = { settings: res.settings, config_dir: res.config_dir, restart_fields: res.restart_fields };
      restartNeeded = [...new Set([...restartNeeded, ...res.restart])];
      setSaveState("Gespeichert ✓");
      draw();
    } catch (e) {
      setSaveState("Nicht gespeichert", true);
      toast(e.message, true);
    }
  };
  const draw = () => {
    const st = S.settings?.settings;
    if (!st) return;
    const theme = localStorage.getItem("theme") || "auto";
    fill(box,
      restartNeeded.length ? callout("warn", "restart", el("span", { text: `Wirkt erst nach einem Neustart des Daemons: ${restartNeeded.join(", ")}` }),
        button("Jetzt neu starten", restartDaemon, "primary sm", "restart")) : null,
      el("div", { class: "cols" },
        card("Allgemein", "Name und Darstellung", null,
          el("div", { class: "grid" },
            field("Name", input(st.name, (v) => save({ name: v }), { maxlength: 40, lazy: true }), "Erscheint auf den Geräten und im Netzwerk (mDNS)."),
            field("Darstellung", select({ auto: "Wie das System", dark: "Dunkel", light: "Hell" }, theme, (v) => { setTheme(v); }), "Gilt nur für diesen Browser."))),
        card("Medien", "Für Media-Kacheln und Aktionen", null,
          el("div", { class: "grid" },
            field("Player", input(st.player || "", (v) => save({ player: v.trim() || null }), { placeholder: "leer = aktivster Player (playerctl)", lazy: true }), "z. B. spotify oder firefox")))),
      card("Verbindung", "Wie Geräte den Daemon erreichen", null,
        el("div", { class: "grid g3" },
          field("Adresse", input(st.host, (v) => save({ host: v.trim() }), { lazy: true }), "0.0.0.0 = im ganzen LAN"),
          field("Port", input(st.port, (v) => save({ port: Number(v) }), { type: "number", min: 1024, max: 65535 }), `Overlay nutzt Port ${st.port + 1}`),
          field("Herzschlag (s)", input(st.heartbeat, (v) => save({ heartbeat: Number(v) }), { type: "number", min: 1, max: 60 })),
          field("USB-Rückfall", input(st.usb, (v) => save({ usb: v.trim() || "auto" }), { lazy: true }), "auto, off oder /dev/serial/by-id/…"),
          field("Geräte-Token", el("div", { class: "row" }, el("input", { value: st.token, readonly: true, class: "mono" }),
            button(null, showToken, "icon", "eye", { title: "Anzeigen" })), "Steht in der Firmware (secrets.h)")),
        settingsRow("mDNS", "Geräte finden den Daemon automatisch (_deckbar._tcp)", sw(st.mdns, (v) => save({ mdns: v }))),
        settingsRow("Browser beim Start öffnen", null, sw(st.open_browser, (v) => save({ open_browser: v })))),
      card("Daemon", S.settings.config_dir ? `Konfiguration: ${S.settings.config_dir}` : null, null,
        el("div", { class: "row wrap" },
          button("Daemon neu starten", restartDaemon, "", "restart"),
          el("span", { class: "hint small", text: `Version ${S.status?.version || "?"}` }))));
  };
  async function showToken() {
    try {
      const r = await api("POST", "/api/settings/token");
      prompt("Geräte-Token (für secrets.h der Firmware):", r.token);
    } catch (e) { toast(e.message, true); }
  }
  ctx.onUnmount(on("settings", draw));
  draw();
  if (!S.settings) api("GET", "/api/settings").then((s) => { S.settings = s; draw(); });
  return box;
}

async function restartDaemon() {
  try {
    await api("POST", "/api/restart");
    toast("Daemon startet neu …");
  } catch (e) { toast(e.message, true); }
}

/* ================================================================ Gerüst */
function setTheme(v) {
  try { if (v === "auto") localStorage.removeItem("theme"); else localStorage.setItem("theme", v); } catch { /* privat */ }
  if (v === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = v;
}

function renderConn() {
  const c = $("conn");
  c.classList.toggle("off", !S.online);
  c.querySelector(".t").textContent = S.online ? `Verbunden · v${S.status?.version || "?"}` : "Daemon nicht erreichbar";
}

function renderBanners() {
  const b = $("banners");
  const parts = [];
  if (!S.online && S.modules) parts.push(callout("bad", "lan", "Keine Verbindung zum Daemon. Läuft deckbar.service? Die Seite verbindet sich von selbst neu."));
  if (S.layoutError) parts.push(callout("bad", "alert", `Layout ungültig – ${S.layoutError}`));
  const missing = Object.entries(S.status?.tools || {}).filter(([, ok]) => !ok).map(([t]) => t);
  if (modOn("deck") && missing.length) parts.push(callout("warn", "information-outline", `Nicht installiert: ${missing.join(", ")} – die zugehörigen Aktionen und Anzeigen bleiben inaktiv.`));
  fill(b, ...parts);
}

async function init() {
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch { /* privat */ }
  await loadIcons();
  $("logo").textContent = glyph("gesture-tap-button");
  $("brand-name").textContent = BRAND;
  $("menu-btn").append(icon("menu"));
  $("menu-btn").addEventListener("click", () => document.body.classList.toggle("nav-open"));
  $("scrim").addEventListener("click", () => document.body.classList.remove("nav-open"));
  $("theme-btn").append(icon("theme-light-dark"));
  $("theme-btn").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(dark ? "light" : "dark");
  });
  addEventListener("hashchange", render);
  on("hello", () => { render(); renderConn(); renderBanners(); });
  on("modules", () => { renderNav(); if (route.page !== "dashboard" && route.page !== "modules" && UI[route.page]) render(); });
  on("online", () => { renderConn(); renderBanners(); });
  on("layout_error", renderBanners);
  on("layout", renderBanners);
  for (const t of ["dps", "runs", "updates", "bot", "overlay", "devices"]) on(t, renderNav);
  // Erststand per REST (sofort sichtbar), danach live über den WebSocket
  try {
    const [modules, st] = await Promise.all([api("GET", "/api/modules"), api("GET", "/api/status")]);
    Object.assign(S, { modules, status: st, state: st.state, devices: st.devices });
    render();
  } catch {
    render();
  }
  renderConn();
  connectLive();
}

init();
emit("boot");
