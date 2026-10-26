/* Modul AION 2 · Radar: Einstellungen, Knöpfe und die Tabellen Feldbosse/Vertraute.
   Das Radar selbst läuft im Daemon und zeigt sich als Widgets im Overlay (Radar, Boss-Warnungen,
   Karte); ein- und ausschalten, Deckkraft und Position dort unter Overlay → Widgets. */
import { fill, el, api, S, field, input, select, button, chip, callout, card, settingsRow, sw, saver, toast } from "../core.js";

const REICHWEITEN = { 50: "50 m", 100: "100 m", 150: "150 m", 300: "300 m", 600: "600 m" };
const DREHUNG = { 0: "0°", 90: "90°", 180: "180°", 270: "270°" };
const TON = { aus: "Aus", piep: "Piepton", ansage: "Ansage" };
const FILTER = { alle: "Alle", offen: "Noch nicht MAX", neu: "Nicht angefangen" };
const ARTEN = { alle: "Alle Arten", Cogni: "Cogni", Fera: "Fera", Natura: "Natura", Varian: "Varian", Spezial: "Spezial" };

async function refresh() {
  try { S.radar = await api("GET", "/api/radar"); } catch { /* bleibt */ }
}

async function befehl(name, text) {
  try {
    S.radar = await api("POST", "/api/radar/befehl", { befehl: name });
    toast(text);
  } catch (e) { toast(e.message, true); }
}

function statusChip(r) {
  if (!r) return chip("…");
  if (r.laeuft) return r.aufnahme ? chip("läuft · ● REC", "bad") : chip("läuft", "ok");
  return chip("wartet auf AION 2");
}

/** Alle 5 s auffrischen, aber nicht neu zeichnen, während ein Feld in Benutzung ist. */
function auffrischen(ctx, box, holen, draw) {
  const busy = () => box.contains(document.activeElement) && /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
  const timer = setInterval(() => holen().then(() => { if (!busy()) draw(); }), 5000);
  ctx.onUnmount(() => clearInterval(timer));
  holen().then(draw);
}

function einstellungen(ctx) {
  const box = el("div", { class: "stack" });
  const save = saver("PUT", "/api/radar", (res) => { S.radar = res; }, 300, "Radar gespeichert");
  const draw = () => {
    const r = S.radar;
    if (!r) return;
    const k = r.einstellungen;
    const setzen = (schluessel, wert) => { k[schluessel] = wert; save({ [schluessel]: wert }); };
    const knopf = (text, name, ic, erledigt) => button(text, () => befehl(name, erledigt), "sm", ic, { disabled: !r.laeuft });

    // Warnungen des gewählten Dungeons
    const dungeons = r.meldungen.dungeons || {};
    const eigene = dungeons[k.meldungen_dungeon] || {};
    const gruppen = { ...(Object.keys(eigene).length ? eigene : { casts: "Alle Boss-Casts zeigen (Lernhilfe)" }), ...r.meldungen.alle };
    const zeilen = Object.entries(gruppen).map(([gruppe, name]) => el("tr", {},
      el("td", { text: name }),
      el("td", {}, sw(!k.meldung_aus.includes(gruppe), (an) =>
        setzen("meldung_aus", an ? k.meldung_aus.filter((g) => g !== gruppe) : [...k.meldung_aus, gruppe]))),
      el("td", {}, select(TON, k.warnton[gruppe] || "ansage", (art) => setzen("warnton", { ...k.warnton, [gruppe]: art })))));
    const karten = Object.fromEntries([["", "automatisch"], ...r.karten.map((n) => [n, n])]);

    fill(box,
      callout("info", "information-outline", "Radar, Boss-Warnungen, Karte und PvP erscheinen im Overlay. Das Radar zeigt sich nur, solange ein Cube in Sicht ist. Ein- und ausschalten, Deckkraft und Position unter Overlay → Widgets."),
      el("div", { class: "cols" },
        card("Radar", "Läuft mit AION 2 und endet 30 s nach dem Spiel", statusChip(r),
          el("div", { class: "row wrap" },
            button("Neu starten", () => befehl("neustart", "Radar startet neu"), "sm", "restart", { disabled: !r.spiel }),
            knopf("Ton testen", "ton_testen", "volume-high", "Ton gespielt"),
            knopf("PvP neu beginnen", "pvp_neu", "sword-cross", "PvP-Sitzung beginnt neu")),
          settingsRow("Ton bei neuem Cube", null, sw(k.ton, (v) => setzen("ton", v))),
          settingsRow("Reichweite", null, select(REICHWEITEN, String(k.reichweite), (v) => setzen("reichweite", Number(v)))),
          settingsRow("Ausrichtung drehen", null, select(DREHUNG, String(k.drehung), (v) => setzen("drehung", Number(v)))),
          settingsRow("Spiegeln (Ost/West)", null, sw(k.spiegeln, (v) => setzen("spiegeln", v)))),
        card("Karte", "Cube-Fundorte, Teleporter, gesehene Spawnpunkte und deine Position", null,
          settingsRow("Karte", null, select(karten, k.karte_name || "", (v) => setzen("karte_name", v))),
          settingsRow("Spieler folgen", "Ziehen pausiert es, Doppelklick auf die Karte folgt wieder", sw(k.karte_folgen, (v) => setzen("karte_folgen", v))))),
      card("Boss-Warnungen", null, sw(k.warn_an, (v) => setzen("warn_an", v)),
        el("div", { class: "row wrap" },
          knopf("Testen", "warnung_testen", "bell-ring", "Testwarnung gezeigt"),
          r.aufnahme ? knopf("Aufnahme stoppen", "aufnahme_stopp", "stop", "Aufnahme gestoppt")
            : knopf("Aufnahme starten", "aufnahme_start", "record", "Aufnahme läuft")),
        el("div", { class: "grid" },
          field("Sprache", select({ de: "Deutsch", en: "Englisch" }, k.sprache, (v) => setzen("sprache", v))),
          field("Dungeon", select(Object.fromEntries(Object.keys(dungeons).map((d) => [d, d])), k.meldungen_dungeon, (v) => { setzen("meldungen_dungeon", v); draw(); }))),
        settingsRow("Dungeons automatisch aufnehmen", "Lernmodus: jeder Lauf wird eine eigene Aufnahme", sw(k.aufnahme_auto, (v) => setzen("aufnahme_auto", v))),
        el("div", { style: "overflow-x:auto" }, el("table", { class: "list" },
          el("thead", {}, el("tr", {}, ["Meldung", "Anzeigen", "Ton"].map((h) => el("th", { text: h })))),
          el("tbody", {}, zeilen)))),
      card("Charakter", "Macht die eigene Erkennung sicher („Todesmal – DU!“)", null,
        field("Charaktername", input(k.name, (v) => setzen("name", v.trim()), { lazy: true, maxlength: 30 }),
          "Wirkt nach „Neu starten“.")));
  };
  auffrischen(ctx, box, refresh, draw);
  draw();
  return box;
}

/* ---------------------------------------------------------------- Feldbosse und Vertraute */
const uhrzeit = (s) => new Date(s * 1000).toLocaleString("de-DE", { weekday: "short", hour: "2-digit", minute: "2-digit" });

function countdown(s) {
  s = Math.max(0, Math.round(s));
  const tage = s >= 86400 ? `${Math.floor(s / 86400)} d ` : "";
  const h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return `in ${tage}${h}:${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function tabelle(koepfe, zeilen) {
  return el("div", { style: "overflow-x:auto" }, el("table", { class: "list" },
    el("thead", {}, el("tr", {}, koepfe.map((h) => el("th", { text: h })))),
    el("tbody", {}, zeilen)));
}

function uebersicht(ctx) {
  const box = el("div", { class: "stack" });
  const wahl = { filter: "alle", art: "alle" };
  let u = null;
  const holen = async () => { try { u = await api("GET", "/api/radar/uebersicht"); } catch { /* bleibt */ } };
  const draw = () => {
    if (!u) return;
    const jetzt = Date.now() / 1000;
    const termine = u.termine.map((t) => el("tr", {},
      el("td", { text: t.name }), el("td", { text: uhrzeit(t.beginn) }),
      t.offen_bis ? el("td", { class: "ok", text: `offen bis ${uhrzeit(t.offen_bis).slice(-5)}` })
        : el("td", { class: "warn", text: countdown(t.beginn - jetzt) })));
    const bosse = u.feldbosse.map((b) => el("tr", {},
      el("td", { text: b.name }), el("td", { text: String(b.karte) }), el("td", { class: b.farbe, text: b.status })));
    const v = u.vertraute
      .filter((x) => wahl.filter === "alle" || (wahl.filter === "offen" ? x.stufe < 3 : !x.angefangen))
      .filter((x) => wahl.art === "alle" || x.art === ARTEN[wahl.art])
      .sort((a, b) => a.fehlen - b.fehlen); // zuerst, was der nächsten Stufe am nächsten ist
    const angefangen = u.vertraute.filter((x) => x.angefangen);
    const summe = angefangen.length
      ? `MAX: ${u.vertraute.filter((x) => x.stufe >= 3).length} · angefangen: ${angefangen.length} · gesamt: ${u.vertraute.length} · Seelen bis alles MAX: ${u.vertraute.reduce((s, x) => s + x.bis_max, 0)}`
      : "Noch keine Daten. Sie kommen beim Einloggen oder Zonenwechsel.";
    fill(box,
      el("div", { class: "cols" },
        card("Termine", "Feste Zeiten der globalen Server, in deiner Ortszeit", null, tabelle(["Termin", "Uhrzeit", "Status"], termine)),
        card("Feldbosse", "Respawn-Timer; die der aktuellen Karte zuerst", null,
          settingsRow("Ansage 5 Minuten vorher", "Feldbosse der aktuellen Karte und der Riss", sw(S.radar?.einstellungen.feldboss_ansage ?? true, async (an) => {
            try { S.radar = await api("PUT", "/api/radar", { feldboss_ansage: an }); } catch (e) { toast(e.message, true); }
          })),
          bosse.length ? tabelle(["Feldboss", "Karte", "Status"], bosse) : el("p", { class: "hint", text: "Noch keine Feldbosse gesehen." }))),
      card("Vertraute", summe, null,
        el("div", { class: "row wrap" },
          select(FILTER, wahl.filter, (f) => { wahl.filter = f; draw(); }),
          select(ARTEN, wahl.art, (a) => { wahl.art = a; draw(); })),
        tabelle(["Vertrauter", "Art", "Stufe (3 = MAX)", "Seelen", "Fehlen", "Wo farmen"], v.map((x) => el("tr", {},
          el("td", { text: x.name }), el("td", { text: x.art }),
          el("td", { class: x.stufe >= 3 ? "ok" : "", text: String(x.stufe) }), el("td", { text: String(x.seelen) }),
          el("td", { text: String(x.fehlen) }), el("td", { text: x.wo.slice(0, 3).join(", ") || "–", title: x.wo.join("\n") }))))));
  };
  if (!S.radar) refresh();
  auffrischen(ctx, box, holen, draw);
  return box;
}

export default {
  tabs: [{ id: "radar", label: "Radar", icon: "radar" }, { id: "uebersicht", label: "Feldbosse und Vertraute", icon: "sword-cross" }],
  status: (m) => (m.status?.laeuft ? "" : "off"),
  card(m) {
    return el("div", { class: "row wrap" }, statusChip(m.status));
  },
  render(tab, ctx) {
    return tab === "uebersicht" ? uebersicht(ctx) : einstellungen(ctx);
  },
};
