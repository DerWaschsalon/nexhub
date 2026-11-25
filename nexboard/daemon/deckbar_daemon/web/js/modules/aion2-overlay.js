/* Modul AION 2 · Overlay: Profile (Hauptbedienung), Widgets aller eingeschalteten Module, Steuerung, Darstellung.
   Jedes Widget wird nur hier ein- und ausgeschaltet; die Module stellen es auf ihrer eigenen Seite ein. */
import { fill, el, api, S, on, field, input, select, button, chip, callout, card, settingsRow, sw, saver, seg, toast, modOn, collapsible } from "../core.js";

const FX = { "": "aus", glanz: "Glanz", brennen: "Brennen", gold: "Gold", frost: "Frost", holo: "Holo", leere: "Leere" };
// Ein Begriff je Sache: „Durchklicken an“ = Overlay nimmt keine Klicks an, „aus“ = Meter bedienbar
const START_MODE = { click: "Durchklicken aus (Meter bedienbar)", lock: "Durchklicken an (alles klickt durch)" };
const DONE = { edit: "Bearbeiten-Modus umgeschaltet", toggle: "Overlay umgeschaltet", lock: "Durchklicken an", click: "Durchklicken aus", settings: "Meter-Einstellungen geöffnet" };
const SHORTCUT_HINT = "Tastenkürzel: In den Kurzbefehlen nach „NexBoard Overlay ein/aus“ suchen. "
  + "Dort steht je Profil und je Widget eine eigene Aktion, der du eine Taste gibst.";

async function openShortcuts() {
  try {
    await api("POST", "/api/overlay/shortcuts");
    toast("Kurzbefehle geöffnet");
  } catch (e) { toast(e.message, true); }
}

// Die Overlay-Seite läuft nur auf diesem PC; von einem anderen Gerät aus gibt es keine Vorschau
const LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]"];
const FALLBACK_SCREEN = { width: 1920, height: 1080 };
const PREVIEW_MODES = [
  { id: "edit", label: "Anordnen", icon: "cursor-move" },
  { id: "click", label: "Wie im Spiel", icon: "eye" },
];
const PREVIEW_HELP = {
  edit: "Zeigt alle Widgets mit Beispieldaten. Hier ziehen und mit dem Mausrad vergrößern; das laufende Overlay übernimmt es sofort.",
  click: "Zeigt, was das Overlay gerade zeigt. Ohne laufendes Spiel bleiben die meisten Widgets leer.",
};

/** Der Monitor, auf dem das Overlay liegt (eingestellt, sonst der Hauptmonitor). */
function overlayScreen(o) {
  const screens = (o.screens || []).filter((s) => s.width && s.height);
  return screens.find((s) => s.name === o.layout.screen) || screens.find((s) => s.primary) || screens[0] || FALLBACK_SCREEN;
}

/** Vorschau: die Overlay-Seite selbst in der Größe des Monitors, verkleinert auf die Breite der Karte.
    Sie bleibt beim Neuzeichnen der Seite stehen (ein neu eingehängtes iframe lädt neu); update(o) passt nur
    Größe und Adresse an. */
function overlayPreview() {
  const frame = el("iframe", { title: "Vorschau des Overlays", tabindex: "-1" });
  const stage = el("div", { class: "overlay-preview" }, frame);
  const head = el("div", { class: "row wrap" });
  const help = el("p", { class: "hint small" });
  const root = card("Vorschau", "So liegen die Widgets auf deinem Monitor", head, stage, help);
  let mode = "edit", size = FALLBACK_SCREEN, port = null;
  const fit = () => {
    const k = stage.clientWidth / size.width;
    frame.style.transform = `scale(${k})`;
    stage.style.height = `${Math.round(size.height * k)}px`;
  };
  const load = () => {
    const src = `http://${location.hostname}:${port}/__deckbar__/overlay/?mode=${mode}`;
    if (frame.src !== src) frame.src = src;
    fill(head, seg(PREVIEW_MODES, mode, (next) => { mode = next; load(); }));
    help.textContent = PREVIEW_HELP[mode];
  };
  new ResizeObserver(fit).observe(stage);
  const update = (o) => {
    root.hidden = !o.page_port || !LOCAL_HOSTS.includes(location.hostname);
    if (root.hidden) return;
    size = overlayScreen(o);
    port = o.page_port;
    frame.style.width = `${size.width}px`;
    frame.style.height = `${size.height}px`;
    fit();
    load();
  };
  return { root, update };
}

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
    const rest = { ...L.profiles };
    delete rest[name];
    put({ profiles: rest, profile: name === L.profile ? "" : L.profile }, `Profil ${name} gelöscht`);
  };
  const title = Object.fromEntries(o.widgets.map((w) => [w.id, w.title]));
  const rows = Object.entries(L.profiles).map(([name, ids]) => settingsRow(name,
    ids.map((id) => title[id]).join(", ") || "keine Widgets",
    el("div", { class: "row" },
      name === L.profile ? chip("aktiv", "ok") : button("Wählen", () => put({ profile: name }, `Profil ${name}`), "sm"),
      button(null, () => remove(name), "sm icon ghost", "delete", { title: "Löschen" }))));
  let neu = "";
  const visible = Object.keys(L.widgets).filter((id) => L.widgets[id].enabled);
  return card("Profile", "Das aktive Profil merkt sich jedes Ein- und Ausschalten eines Widgets", null,
    ...rows,
    el("div", { class: "row wrap", style: "margin-top:14px" },
      input("", (v) => { neu = v.trim(); }, { placeholder: "Name ohne Leerzeichen, z. B. Raid", maxlength: 24 }),
      button("Aus der aktuellen Ansicht anlegen", () => put({ profiles: { ...L.profiles, [neu]: visible }, profile: neu }, `Profil ${neu} angelegt`), "sm", "plus")));
}

/** Ein Widget: Schalter in der Zeile, Deckkraft, Position und seine eigenen Schalter unter „Anpassen“. */
function widgetRow(o, spec, set, view) {
  const id = spec.id;
  const w = o.layout.widgets[id];
  const extra = spec.options.map((option) => settingsRow(option.title, option.help || null,
    sw(w.options[option.key], (v) => set(id, { options: { [option.key]: v } }))));
  const opacity = el("input", { type: "range", min: 20, max: 100, value: Math.round(w.opacity * 100), style: "max-width:200px" });
  const opacityRow = settingsRow("Deckkraft", `${opacity.value} %`, opacity);
  opacity.addEventListener("input", () => {
    set(id, { opacity: Number(opacity.value) / 100 });
    opacityRow.querySelector(".txt span").textContent = `${opacity.value} %`;
  });
  const reset = () => { set(id, { x: null, y: null, scale: 1 }); toast("Zurückgesetzt"); };
  return el("div", { class: "row-group" }, settingsRow(spec.title, spec.help, sw(w.enabled, (v) => set(id, { enabled: v }))),
    collapsible("Anpassen", view,
      opacityRow,
      settingsRow("Position zurücksetzen", "An den Standardplatz, Größe 100 %", button("Zurücksetzen", reset, "sm", "refresh")),
      ...extra));
}

function widgetsCard(o, set, views) {
  const specs = o.widgets.filter((spec) => modOn(spec.module));
  return card("Widgets", "Nur von eingeschalteten Modulen", null, specs.map((spec) => {
    views[spec.id] ??= {};
    return widgetRow(o, spec, set, views[spec.id]);
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
    el("div", { class: "row wrap", style: "margin-top:14px" },
      button("Tastenkürzel einrichten", openShortcuts, "sm", "open-in-new"),
      el("span", { class: "hint small", text: SHORTCUT_HINT })));
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
  const preview = overlayPreview();
  const page = el("div", { class: "stack" }, preview.root, box);
  const save = saver("PUT", "/api/overlay", (res) => { S.overlay = res; }, 400, "Overlay gespeichert");
  const views = {}; // aufgeklappte Abschnitte bleiben beim Neuzeichnen offen
  const view = {};
  const draw = () => {
    const o = S.overlay;
    if (!o) return;
    preview.update(o);
    const setWidget = (id, patch) => {
      const { options, ...rest } = patch;
      Object.assign(o.layout.widgets[id], rest);
      Object.assign(o.layout.widgets[id].options, options);
      save({ widgets: { [id]: patch } });
    };
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
  return page;
}

export default {
  status: () => (S.overlay?.unit?.active ? "" : "off"),
  card() {
    const o = S.overlay;
    const w = o?.layout?.widgets;
    const active = w ? Object.entries(w).filter(([, v]) => v.enabled).length : 0;
    return el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "row wrap" }, unitChip(o), o?.layout?.profile ? chip(`Profil ${o.layout.profile}`, "info") : null),
      el("div", { class: "metric" }, el("b", { text: String(active) }), el("span", { text: active === 1 ? "Widget aktiv" : "Widgets aktiv" })));
  },
  pages: [{ id: "aion2.overlay", render: (tab, ctx) => overlayPage(ctx) }],
};
