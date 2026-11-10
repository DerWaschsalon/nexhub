/* Modul AION 2 · Plugins: installierte Plugins, Katalog von A2Tools, Updates. Installieren und Updates mit
   neuen Rechten nur nach Zustimmung. Die Texte zu den Rechten kommen aus dem Meter (/api/plugins/texts). */
import { fill, el, api, button, chip, callout, card, settingsRow, sw, toast, collapsible } from "../core.js";

// Recht → Text im Meter (pluginSettings.js); „decoder:<name>“ liest einzelne Spielfelder
const PERMISSION_TEXT = {
  storage: "permStorage", notify: "permNotify", widgets: "permWidgets", window: "permWindow",
  "events:character": "permCharacter", "feed:boss-timers": "permBossTimers", fps: "permFps",
  screenshot: "permScreenshot", "events:death-recap": "permDeathRecap", "events:loot-rolls": "permLootRolls",
  "events:black-market": "permBlackMarket", "events:kda": "permKda",
};

let texts = {};

const call = async (cmd, args = {}) => (await api("POST", "/api/plugins", { cmd, args })).result;

function describe(permission) {
  if (permission.startsWith("decoder:")) return (texts.permDecoder || "Spieldaten: {name}").replace("{name}", permission.slice(8));
  return texts[PERMISSION_TEXT[permission]] || permission;
}

/** Zustimmung wie im Meter: was das Plugin danach darf. */
function consent(action, name, permissions) {
  const lines = permissions.length ? permissions.map((p) => `• ${describe(p)}`) : [`• ${texts.permNone || "Nur sein Fenster anzeigen"}`];
  return confirm(`${name} ${action}?\n\n${texts.permsTitle || "Es darf:"}\n${lines.join("\n")}`);
}

function permissionList(permissions, view) {
  return collapsible(`Darf (${permissions.length})`, view, el("ul", { class: "hint small" }, permissions.map((p) => el("li", { text: describe(p) }))));
}

function pluginsPage(ctx) {
  const box = el("div", { class: "stack" });
  const state = { view: null, catalog: [], updates: {}, catalogError: null, busy: false };
  const views = {}; // aufgeklappte Rechte bleiben offen
  const viewOf = (id) => (views[id] ??= {});

  const run = async (work, done) => {
    state.busy = true;
    draw();
    try {
      await work();
      if (done) toast(done);
    } catch (e) {
      toast(e.message, true);
    }
    state.busy = false;
    await load();
  };
  const install = (entry, permissions, action) => {
    if (!consent(action, entry.name, permissions)) return;
    run(async () => { state.view = await call("plugin_install", { id: entry.id }); delete state.updates[entry.id]; }, `${entry.name} ${action === "aktualisieren" ? "aktualisiert" : "installiert"}`);
  };
  const remove = (p) => {
    if (!confirm(`${p.name} entfernen? Seine gespeicherten Daten bleiben für eine spätere Installation.`)) return;
    run(async () => { state.view = await call("plugin_uninstall", { id: p.id }); }, `${p.name} entfernt`);
  };
  const checkUpdates = () => run(async () => {
    const res = await call("plugin_check_updates");
    state.updates = Object.fromEntries(res.available.map((a) => [a.id, a]));
    state.catalogError = res.catalogError;
  }, "Nach Updates gesucht");

  const installedRow = (p, builtIn) => {
    const on = !(state.view.disabled || []).includes(p.id);
    const update = state.updates[p.id];
    const controls = el("div", { class: "row" },
      update ? button(`Update auf ${update.to}`, () => install({ id: p.id, name: p.name }, update.newPermissions, "aktualisieren"), "sm primary", "update") : null,
      button(null, () => run(() => call("plugin_open", { id: p.id })), "sm icon ghost", "open-in-new", { title: "Fenster öffnen (Overlay muss laufen)", disabled: !on }),
      builtIn ? chip("eingebaut") : button(null, () => remove(p), "sm icon ghost", "delete", { title: "Entfernen" }),
      builtIn ? null : sw(on, (v) => run(async () => { state.view = await call("plugin_set_enabled", { id: p.id, enabled: v }); })));
    return el("div", { class: "row-group" },
      settingsRow(`${p.name} ${p.version}`, p.error ? `Fehler: ${p.error}` : p.description, controls),
      permissionList(p.permissions, viewOf(p.id)));
  };

  const catalogRow = (entry) => el("div", { class: "row-group" },
    settingsRow(`${entry.name} ${entry.version}`, `${entry.description}${entry.author ? ` · von ${entry.author}` : ""}`,
      button("Installieren", () => install(entry, entry.permissions, "installieren"), "sm", "download", { disabled: state.busy })),
    permissionList(entry.permissions, viewOf(`katalog-${entry.id}`)));

  const draw = () => {
    if (!state.view) { fill(box, el("div", { class: "empty" }, "Lade Plugins …")); return; }
    const installed = [...state.view.builtIn.map((p) => installedRow(p, true)), ...state.view.plugins.map((p) => installedRow(p, false))];
    const available = state.catalog.filter((e) => !e.installed);
    fill(box,
      callout("info", "information-outline", "Plugins aus dem signierten Katalog von A2Tools, mit Zustimmung zu dem, was sie dürfen. Bitte nur hier installieren: Das eigenständige A2Tools-Programm hat einen eigenen Ordner, die NexBoard sieht dessen Plugins nicht."),
      state.catalogError ? callout("warn", "alert", `Katalog nicht erreichbar: ${state.catalogError}`) : null,
      card("Installiert", "Fenster und Widgets erscheinen im Overlay, sobald AION 2 läuft",
        button("Nach Updates suchen", checkUpdates, "sm", "refresh", { disabled: state.busy }), installed),
      card("Katalog", available.length ? "Noch nicht installiert" : "Alle Plugins aus dem Katalog sind installiert", null, available.map(catalogRow)));
  };

  const load = async () => {
    try {
      state.view = await call("plugin_list");
      state.catalog = await call("plugin_catalog");
    } catch (e) {
      state.catalogError = e.message;
    }
    draw();
  };
  if (!Object.keys(texts).length) api("GET", "/api/plugins/texts").then((t) => { texts = t; draw(); }).catch(() => {});
  load();
  draw();
  return box;
}

export default {
  status: (m) => (m.status?.installed ? "" : "off"),
  card(m) {
    const n = m.status?.installed ?? 0;
    return el("div", { class: "metric" }, el("b", { text: String(n) }), el("span", { text: n === 1 ? "Plugin installiert" : "Plugins installiert" }));
  },
  pages: [{ id: "aion2.plugins", name: "Plugins", render: (tab, ctx) => pluginsPage(ctx) }],
};
