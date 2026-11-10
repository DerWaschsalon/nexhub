/* Modul AION 2 · Overlay: Profile (Hauptbedienung), Widgets aller eingeschalteten Module, Steuerung, Darstellung.
   Jedes Widget wird nur hier ein- und ausgeschaltet; die Module stellen es auf ihrer eigenen Seite ein. */
import { fill, el, api, S, on, field, input, select, button, chip, callout, card, settingsRow, sw, saver, toast, modOn, collapsible } from "../core.js";

const FX = { "": "aus", glanz: "Glanz", brennen: "Brennen", gold: "Gold", frost: "Frost", holo: "Holo", leere: "Leere" };
// Ein Begriff je Sache: „Durchklicken an“ = Overlay nimmt keine Klicks an, „aus“ = Meter bedienbar
const START_MODE = { click: "Durchklicken aus (Meter bedienbar)", lock: "Durchklicken an (alles klickt durch)" };
const DONE = { edit: "Bearbeiten-Modus umgeschaltet", toggle: "Overlay umgeschaltet", lock: "Durchklicken an", click: "Durchklicken aus", settings: "Meter-Einstellungen geöffnet" };
const WIDGET_HELP = {
  meter: "Oberfläche des A2Tools-Meters",
  boss: "HP des Ziels mit Kill-Prognose",
  timers: "Countdown bis zum nächsten Termin; welche, steht unter Termine",
  radar: "Karte, Cubes, Vertraute und Würfel; zeigt sich, solange ein Cube in Sicht ist",
  warnung: "Boss-Warnungen, nur während einer Warnung; was gewarnt wird, steht unter Warnungen",
  pvp: "Kills, Tode und Rangpunkte seit Spielstart",
};
const SHORTCUT_HINT = "Tastenkürzel: Systemeinstellungen → Tastatur → Kurzbefehle → „NexBoard Overlay ein/aus“. "
  + "Dort steht je Profil und je Widget eine eigene Aktion, der du eine Taste gibst.";

/** Befehl an das laufende Overlay-Programm (auch von Übersicht und Kampfdaten). */
export async function cmd(c) {
  try {
    await api("POST", "/api/overlay/command", { cmd: c });
    toast(DONE[c] || "Erledigt");
  } catch (e) { toast(e.message, true); }
}

async function refresh() {
  try { S.overlay = await api("GET", "/api/overlay"); } catch { /* bleibt */ }
}

function unitChip(o) {
  const u = o?.unit || {};
  if (u.installed === false) return chip("nicht eingerichtet", "warn");
  if (u.active) return chip("läuft", "ok");
  if (u.state === "inactive" && !o.game) return chip("wartet auf AION 2");
  if (u.state) return chip(u.state === "inactive" ? "beendet" : u.state, u.state === "failed" ? "bad" : "");
  return chip("…");
}

/** Profile: welche Widgets sichtbar sind. Wechsel und Löschen speichern sofort, die Schalter darunter ändern sich mit. */
function profilesCard(o, put) {
  const L = o.layout;
  const remove = (name) => {
    const rest = { ...L.profile };
    delete rest[name];
    put({ profile: rest, profil: name === L.profil ? "" : L.profil }, `Profil ${name} gelöscht`);
  };
  const rows = Object.entries(L.profile).map(([name, ids]) => settingsRow(name,
    ids.map((id) => o.widget_titel[id]).join(", ") || "keine Widgets",
    el("div", { class: "row" },
      name === L.profil ? chip("aktiv", "ok") : button("Wählen", () => put({ profil: name }, `Profil ${name}`), "sm"),
      button(null, () => remove(name), "sm icon ghost", "delete", { title: "Löschen" }))));
  let neu = "";
  const visible = Object.keys(L.widgets).filter((id) => L.widgets[id].enabled);
  return card("Profile", "Das aktive Profil merkt sich jedes Ein- und Ausschalten eines Widgets", null,
    ...rows,
    el("div", { class: "row wrap", style: "margin-top:14px" },
      input("", (v) => { neu = v.trim(); }, { placeholder: "Name ohne Leerzeichen, z. B. Raid", maxlength: 24 }),
      button("Aus der aktuellen Ansicht anlegen", () => put({ profile: { ...L.profile, [neu]: visible }, profil: neu }, `Profil ${neu} angelegt`), "sm", "plus")));
}

/** Ein Widget: Schalter in der Zeile, Deckkraft, Position und Eigenes unter „Anpassen“. */
function widgetRow(o, id, set, view) {
  const w = o.layout.widgets[id];
  const extra = id === "boss" ? [
    settingsRow("Kill-Prognose", "Restzeit aus dem HP-Verlauf der letzten 40 s", sw(w.show_ttk, (v) => set(id, { show_ttk: v }))),
    settingsRow("Außerhalb von Kämpfen ausblenden", null, sw(w.hide_idle, (v) => set(id, { hide_idle: v }))),
  ] : [];
  const opacity = el("input", { type: "range", min: 20, max: 100, value: Math.round(w.opacity * 100), style: "max-width:200px" });
  const opacityRow = settingsRow("Deckkraft", `${opacity.value} %`, opacity);
  opacity.addEventListener("input", () => {
    set(id, { opacity: Number(opacity.value) / 100 });
    opacityRow.querySelector(".txt span").textContent = `${opacity.value} %`;
  });
  const reset = () => { set(id, { x: null, y: null, scale: 1 }); toast("Zurückgesetzt"); };
  return el("div", { class: "row-group" }, settingsRow(o.widget_titel[id], WIDGET_HELP[id], sw(w.enabled, (v) => set(id, { enabled: v }))),
    collapsible("Anpassen", view,
      opacityRow,
      settingsRow("Position zurücksetzen", "An den Standardplatz, Größe 100 %", button("Zurücksetzen", reset, "sm", "refresh")),
      ...extra));
}

function widgetsCard(o, set, views) {
  const ids = Object.keys(o.layout.widgets).filter((id) => modOn(o.widget_module[id]));
  return card("Widgets", "Nur von eingeschalteten Modulen", null, ids.map((id) => {
    views[id] ??= {};
    return widgetRow(o, id, set, views[id]);
  }));
}

function controlCard(o, redraw) {
  const restart = async () => {
    try { S.overlay = await api("POST", "/api/overlay/restart"); toast("Overlay startet neu"); redraw(); } catch (e) { toast(e.message, true); }
  };
  return card("Steuerung", "Startet mit AION 2 und läuft dann als eigenes Programm im Tray", unitChip(o),
    el("div", { class: "row wrap" },
      button("Bearbeiten", () => cmd("edit"), "primary", "cursor-move"),
      button("Zeigen/Verbergen", () => cmd("toggle"), "", "eye"),
      button("Durchklicken an", () => cmd("lock"), "", "lock"),
      button("Durchklicken aus", () => cmd("click"), "", "lock-open"),
      button("Overlay neu starten", restart, "ghost", "restart")),
    el("p", { class: "hint small", style: "margin-top:14px" },
      "Im Bearbeiten-Modus Widgets ziehen, Mausrad = Größe, Esc = fertig. Das Meter lässt sich jederzeit an Kopf- oder Fußzeile verschieben."),
    el("p", { class: "hint small", text: SHORTCUT_HINT }));
}

function lookCard(o, save, view) {
  const L = o.layout;
  const screens = { "": "Hauptmonitor (laut KDE)", ...Object.fromEntries((o.screens || []).map((s) => [s.name, `${s.name} · ${s.width}×${s.height}${s.primary ? " · Hauptmonitor" : ""}`])) };
  if (L.screen && !(L.screen in screens)) screens[L.screen] = L.screen;
  const set = (key, value) => { L[key] = value; save({ [key]: value }); };
  const advanced = collapsible("Erweitert", view,
    settingsRow("GPU-Beschleunigung", "Aus nur bei Darstellungsfehlern; wirkt nach „Overlay neu starten“", sw(L.gpu, (v) => set("gpu", v))));
  return card("Darstellung", null, null,
    el("div", { class: "grid" },
      field("Monitor", select(screens, L.screen, (v) => set("screen", v)), "Wirkt nach „Overlay neu starten“."),
      field("Beim Start", select(START_MODE, L.start_mode, (v) => set("start_mode", v))),
      field("Namenseffekt", select(FX, L.fx, (v) => set("fx", v)), "Auf deinem Namen in der eigenen Meter-Zeile.")),
    settingsRow("Nur bei aktivem Spiel zeigen", "Blendet das Overlay aus, sobald ein anderes Fenster als AION 2 den Fokus hat (KDE)", sw(L.hide_unfocused, (v) => set("hide_unfocused", v))),
    advanced);
}

function overlayPage(ctx) {
  const box = el("div", { class: "stack" });
  const save = saver("PUT", "/api/overlay", (res) => { S.overlay = res; }, 400, "Overlay gespeichert");
  const views = {}; // aufgeklappte Abschnitte bleiben beim Neuzeichnen offen
  const view = {};
  const draw = () => {
    const o = S.overlay;
    if (!o) return;
    const setWidget = (id, patch) => { Object.assign(o.layout.widgets[id], patch); save({ widgets: { [id]: patch } }); };
    const put = async (patch, text) => {
      try { S.overlay = await api("PUT", "/api/overlay", patch); toast(text); draw(); } catch (e) { toast(e.message, true); }
    };
    fill(box,
      o.unit?.installed === false ? callout("warn", "alert", el("span", {}, "Das Overlay-Programm ist noch nicht eingerichtet. Einmal im Repo ausführen: ", el("code", { text: "overlay/install.sh" }), " (braucht pyside6, qt6-webengine, layer-shell-qt).")) : null,
      el("div", { class: "cols" }, profilesCard(o, put), widgetsCard(o, setWidget, views)),
      el("div", { class: "cols" }, controlCard(o, draw), lookCard(o, save, view)),
      callout("info", "information-outline", "Unter KDE Plasma (Wayland) liegt das Overlay als eigene Ebene über dem Vollbildspiel und nimmt nur dort Klicks an, wo das Meter ist. Ohne layer-shell (GNOME, X11) läuft automatisch das einfache Meter-Fenster."));
  };
  // nicht neu aufbauen, solange ein Regler oder Feld in Benutzung ist (sonst bricht das Ziehen ab)
  const busy = () => box.contains(document.activeElement) && /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
  ctx.onUnmount(on("overlay", () => { if (!busy()) draw(); }));
  ctx.onUnmount(on("modules", draw));
  refresh().then(draw);
  draw();
  return box;
}

export default {
  status: () => (S.overlay?.unit?.active ? "" : "off"),
  card() {
    const o = S.overlay;
    const w = o?.layout?.widgets;
    const active = w ? Object.entries(w).filter(([, v]) => v.enabled).length : 0;
    return el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "row wrap" }, unitChip(o), o?.layout?.profil ? chip(`Profil ${o.layout.profil}`, "info") : null),
      el("div", { class: "metric" }, el("b", { text: String(active) }), el("span", { text: active === 1 ? "Widget aktiv" : "Widgets aktiv" })));
  },
  pages: [{ id: "aion2.overlay", render: (tab, ctx) => overlayPage(ctx) }],
};
