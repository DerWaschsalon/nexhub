/* Modul AION 2 · Termine: eine Liste aus den festen Terminen der Server und eigenen Ereignissen (dieselbe zeigt
   das Termine-Widget im Overlay), eigene Ereignisse bearbeiten, darunter die Feldbosse des Radars. */
import { fill, el, api, S, on, input, select, button, chip, card, settingsRow, sw, toast, clampInt, modOn } from "../core.js";

const SETTINGS = "/api/m/aion2.schedule/settings";
const REFRESH_MS = 5000;
const EVERY = { 60: "stündlich", 120: "alle 2 h", 180: "alle 3 h", 240: "alle 4 h", 360: "alle 6 h", 720: "alle 12 h", 1440: "täglich", 10080: "wöchentlich" };
const WEEK = 10080;
const DAY = 1440;
const DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

const clock = (s) => new Date(s * 1000).toLocaleString("de-DE", { weekday: "short", hour: "2-digit", minute: "2-digit" });

function countdown(s) {
  s = Math.max(0, Math.round(s));
  const days = s >= 86400 ? `${Math.floor(s / 86400)} d ` : "";
  const h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return `in ${days}${h}:${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function table(heads, rows) {
  return el("div", { style: "overflow-x:auto" }, el("table", { class: "list" },
    el("thead", {}, el("tr", {}, heads.map((h) => el("th", { text: h })))),
    el("tbody", {}, rows)));
}

const hhmm = (min) => `${String(Math.floor((min % DAY) / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

/** „HH:MM“ als Minuten ab Mitternacht (bzw. ab Montag beim wöchentlichen); null = ungültig. */
function parseStart(text, ev) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!m) return null;
  const day = ev.every === WEEK ? Math.floor(ev.at / DAY) * DAY : 0;
  return day + (Number(m[1]) * 60 + Number(m[2])) % Math.min(ev.every, DAY);
}

/** Ein eigenes Ereignis als Tabellenzeile; push() speichert die ganze Liste. */
function eventRow(evs, i, push) {
  const ev = evs[i];
  const setStart = (v) => {
    const at = parseStart(v, ev);
    if (at === null) { toast("Zeit als HH:MM", true); return; }
    ev.at = at;
    push();
  };
  const day = ev.every === WEEK
    ? select(Object.fromEntries(DAYS.map((d, k) => [k, d])), String(Math.floor(ev.at / DAY)), (v) => { ev.at = Number(v) * DAY + (ev.at % DAY); push(); })
    : null;
  return el("tr", {},
    el("td", {}, input(ev.name, (v) => { ev.name = v.trim() || ev.name; push(); }, { maxlength: 40, lazy: true })),
    el("td", {}, select(EVERY, String(ev.every), (v) => { ev.every = Number(v); ev.at %= ev.every; push(); })),
    el("td", {}, day, input(hhmm(ev.at), setStart, { lazy: true, style: "width:80px", title: "erster Start ab Mitternacht" })),
    el("td", {}, input(ev.open, (v) => { ev.open = clampInt(v, 0, DAY, 0); push(); }, { type: "number", min: 0, max: DAY, style: "width:80px" })),
    el("td", {}, select({ local: "Ortszeit", utc: "UTC" }, ev.tz, (v) => { ev.tz = v; push(); })),
    el("td", {}, button(null, () => { evs.splice(i, 1); push(); }, "sm icon ghost", "delete", { title: "Entfernen" })));
}

function ownEventsCard(settings, save) {
  const evs = settings.events;
  const push = () => save({ events: evs });
  const add = () => { evs.push({ name: "Neues Ereignis", every: 60, at: 0, open: 0, tz: "local", enabled: true }); push(); };
  return card("Eigene Ereignisse", "Erscheinen in der Liste oben und im Termine-Widget", null,
    evs.length ? table(["Name", "Wiederholung", "Start", "offen (min)", "Zeitzone", ""], evs.map((_, i) => eventRow(evs, i, push))) : null,
    el("div", { class: "row wrap", style: "margin-top:14px" }, button("Ereignis hinzufügen", add, "sm", "plus")));
}

/** Alle Termine mit Schalter: feste Termine ausblenden, eigene ein- und ausschalten. */
function listCard(entries, settings, save) {
  const now = Date.now() / 1000;
  let own = -1;
  const rows = entries.map((t) => {
    if (t.own) own += 1;
    const i = own;
    const toggle = t.own
      ? (v) => { settings.events[i].enabled = v; save({ events: settings.events }); }
      : (v) => save({ hidden: v ? settings.hidden.filter((n) => n !== t.name) : [...settings.hidden, t.name] });
    const status = t.open_until !== null
      ? el("td", { class: "ok", text: `offen bis ${clock(t.open_until).slice(-5)}` })
      : el("td", { class: "warn", text: countdown(t.start - now) });
    return el("tr", {}, el("td", {}, sw(t.shown, toggle)), el("td", {}, t.name, t.own ? chip("eigenes") : null),
      el("td", { text: clock(t.start) }), status);
  });
  return card("Termine", "Feste Zeiten der globalen Server und eigene Ereignisse, in deiner Ortszeit", null,
    table(["", "Termin", "Uhrzeit", "Status"], rows));
}

function fieldBossCard(bosses) {
  const announce = S.radar?.einstellungen.feldboss_ansage ?? true;
  const rows = bosses.map((b) => el("tr", {}, el("td", { text: b.name }), el("td", { text: String(b.karte) }), el("td", { class: b.farbe, text: b.status })));
  return card("Feldbosse", "Respawn-Timer aus dem Radar; die der aktuellen Karte zuerst", null,
    settingsRow("Ansage 5 Minuten vorher", "Feldbosse der aktuellen Karte und der Riss", sw(announce, async (v) => {
      try { S.radar = await api("PUT", "/api/radar", { feldboss_ansage: v }); } catch (e) { toast(e.message, true); }
    })),
    rows.length ? table(["Feldboss", "Karte", "Status"], rows) : el("p", { class: "hint", text: "Noch keine Feldbosse gesehen." }));
}

function schedulePage(ctx) {
  const box = el("div", { class: "stack" });
  let entries = null, settings = null, bosses = [];
  const load = async () => {
    try {
      entries = (await api("GET", "/api/schedule")).entries;
      if (!modOn("aion2.radar")) return;
      bosses = (await api("GET", "/api/radar/feldbosse")).feldbosse;
      S.radar ??= await api("GET", "/api/radar"); // für den Schalter der Feldboss-Ansage
    } catch { /* bleibt */ }
  };
  const save = async (patch) => {
    try {
      settings = (await api("PUT", SETTINGS, patch)).settings;
      await load();
      draw();
    } catch (e) { toast(e.message, true); }
  };
  const draw = () => {
    if (!entries || !settings) return;
    fill(box, listCard(entries, settings, save), ownEventsCard(settings, save),
      modOn("aion2.radar") ? fieldBossCard(bosses) : null);
  };
  // nicht neu zeichnen, während ein Feld in Benutzung ist
  const busy = () => box.contains(document.activeElement) && /INPUT|SELECT/.test(document.activeElement.tagName);
  const timer = setInterval(() => load().then(() => { if (!busy()) draw(); }), REFRESH_MS);
  ctx.onUnmount(() => clearInterval(timer));
  ctx.onUnmount(on("modules", draw));
  Promise.all([api("GET", SETTINGS), load()]).then(([res]) => { settings = res.settings; draw(); });
  return box;
}

export default {
  card() {
    return el("span", { class: "faint", text: "Riss, Shugo-Fest, Resets und eigene Ereignisse" });
  },
  pages: [{ id: "aion2.schedule", name: "Termine", render: (tab, ctx) => schedulePage(ctx) }],
};
