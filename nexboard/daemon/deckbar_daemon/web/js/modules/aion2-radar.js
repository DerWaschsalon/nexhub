/* Modul AION 2 · Radar: Einstellungen und Knöpfe für das Radar (nexboard/radar).
   Das Radar selbst bleibt ein eigenes Programm mit eigenen Fenstern, diese Seite schreibt nur
   ~/.config/aion2-radar.json und schickt Befehle (Ton testen, Karte zeigen …). */
import { fill, el, api, S, field, input, select, button, chip, callout, card, settingsRow, sw, saver, toast } from "../core.js";

const REICHWEITEN = { 50: "50 m", 100: "100 m", 150: "150 m", 300: "300 m", 600: "600 m" };
const DREHUNG = { 0: "0°", 90: "90°", 180: "180°", 270: "270°" };
const TON = { aus: "Aus", piep: "Piepton", ansage: "Ansage" };

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
  return r.spiel ? chip("beendet") : chip("wartet auf AION 2");
}

// Regler in Prozent für Werte von 0 bis 1 (Deckkraft)
function prozent(wert, onChange) {
  const zahl = el("span", { text: `${Math.round(wert * 100)} %`, style: "min-width:44px" });
  return el("div", { class: "row" },
    el("input", { type: "range", min: 30, max: 100, value: Math.round(wert * 100), style: "max-width:200px",
      oninput: (e) => { zahl.textContent = `${e.target.value} %`; onChange(Number(e.target.value) / 100); } }),
    zahl);
}

function seite(ctx) {
  const box = el("div", { class: "stack" });
  const save = saver("PUT", "/api/radar", (res) => { S.radar = res; }, 300, "Radar gespeichert");
  const draw = () => {
    const r = S.radar;
    if (!r) return;
    const k = r.einstellungen;
    const setzen = (schluessel, wert) => { k[schluessel] = wert; save({ [schluessel]: wert }); };
    const knopf = (text, name, ic, erledigt) => button(text, () => befehl(name, erledigt), "sm", ic, { disabled: !r.laeuft });

    // Warnungen des gewählten Dungeons, wie im Fenster „Meldungen“ des Radars
    const dungeons = r.meldungen.dungeons || {};
    const eigene = dungeons[k.meldungen_dungeon] || {};
    const gruppen = { ...(Object.keys(eigene).length ? eigene : { casts: "Alle Boss-Casts zeigen (Lernhilfe)" }), ...r.meldungen.alle };
    const zeilen = Object.entries(gruppen).map(([gruppe, name]) => el("tr", {},
      el("td", { text: name }),
      el("td", {}, sw(!k.meldung_aus.includes(gruppe), (an) =>
        setzen("meldung_aus", an ? k.meldung_aus.filter((g) => g !== gruppe) : [...k.meldung_aus, gruppe]))),
      el("td", {}, select(TON, k.warnton[gruppe] || "ansage", (art) => setzen("warnton", { ...k.warnton, [gruppe]: art })))));

    fill(box,
      !r.laeuft && r.spiel ? callout("info", "information-outline", "AION 2 läuft, das Radar aber nicht (über Rechtsklick > Beenden geschlossen?). „Neu starten“ holt es zurück.") : null,
      el("div", { class: "cols" },
        card("Radar", "Startet mit AION 2 und endet 30 s nach dem Spiel", statusChip(r),
          el("div", { class: "row wrap" },
            button("Neu starten", () => befehl("neustart", "Radar startet neu"), "sm", "restart", { disabled: !r.spiel }),
            knopf("Ton testen", "ton_testen", "volume-high", "Ton gespielt")),
          settingsRow("Ton bei neuem Cube", null, sw(k.ton, (v) => setzen("ton", v))),
          settingsRow("Größe", `${k.groesse} px`, input(k.groesse, (v) => setzen("groesse", Math.max(120, Math.min(800, Number(v) || 260))), { type: "number", min: 120, max: 800, style: "width:90px" })),
          settingsRow("Reichweite", "Auch mit dem Mausrad auf dem Radar", select(REICHWEITEN, String(k.reichweite), (v) => setzen("reichweite", Number(v)))),
          settingsRow("Ausrichtung drehen", null, select(DREHUNG, String(k.drehung), (v) => setzen("drehung", Number(v)))),
          settingsRow("Spiegeln (Ost/West)", null, sw(k.spiegeln, (v) => setzen("spiegeln", v))),
          settingsRow("Deckkraft", null, prozent(k.deckkraft, (v) => setzen("deckkraft", v)))),
        card("Karte", "Eichen, Karte laden und Spawnpunkte bleiben im Kartenfenster (Rechtsklick)", null,
          el("div", { class: "row wrap" },
            knopf("Zeigen", "karte_zeigen", "eye", "Karte gezeigt"),
            knopf("Ausblenden", "karte_ausblenden", "eye-off", "Karte ausgeblendet")),
          settingsRow("Spieler folgen", null, sw(k.karte_folgen, (v) => setzen("karte_folgen", v))),
          settingsRow("Deckkraft", null, prozent(k.karte_deckkraft, (v) => setzen("karte_deckkraft", v))))),
      card("Boss-Warnungen", null, sw(k.warn_an, (v) => setzen("warn_an", v)),
        el("div", { class: "row wrap" },
          knopf("Testen", "warnung_testen", "bell-ring", "Testwarnung gezeigt"),
          knopf("Position ändern", "warnung_verschieben", "cursor-move", "Warnfenster verschieben, danach nochmal drücken"),
          r.aufnahme ? knopf("Aufnahme stoppen", "aufnahme_stopp", "stop", "Aufnahme gestoppt")
            : knopf("Aufnahme starten", "aufnahme_start", "record", "Aufnahme läuft")),
        el("div", { class: "grid" },
          field("Sprache", select({ de: "Deutsch", en: "Englisch" }, k.sprache, (v) => setzen("sprache", v))),
          field("Dungeon", select(Object.fromEntries(Object.keys(dungeons).map((d) => [d, d])), k.meldungen_dungeon, (v) => { setzen("meldungen_dungeon", v); draw(); }))),
        settingsRow("Dungeons automatisch aufnehmen", "Lernmodus: jeder Lauf wird eine eigene Aufnahme", sw(k.aufnahme_auto, (v) => setzen("aufnahme_auto", v))),
        el("div", { style: "overflow-x:auto" }, el("table", { class: "list" },
          el("thead", {}, el("tr", {}, ["Meldung", "Anzeigen", "Ton"].map((h) => el("th", { text: h })))),
          el("tbody", {}, zeilen)))),
      el("div", { class: "cols" },
        card("Feldbosse und Vertraute", "Respawn-Timer, Termine, Vertraute", null,
          el("div", { class: "row wrap" }, knopf("Fenster öffnen", "uebersicht_zeigen", "open-in-new", "Fenster geöffnet")),
          settingsRow("Feldboss-Ansage", "5 Minuten vorher und beim Respawn", sw(k.feldboss_ansage, (v) => setzen("feldboss_ansage", v)))),
        card("Charakter", "Macht die eigene Erkennung sicher („Todesmal – DU!“)", null,
          field("Charaktername", input(k.name, (v) => setzen("name", v.trim()), { lazy: true, maxlength: 30 }),
            "Wirkt nach „Neu starten“."))));
  };
  // Status (läuft, Aufnahme) alle 5 s auffrischen, aber nicht, während ein Feld in Benutzung ist
  const busy = () => box.contains(document.activeElement) && /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
  const timer = setInterval(() => refresh().then(() => { if (!busy()) draw(); }), 5000);
  ctx.onUnmount(() => clearInterval(timer));
  refresh().then(draw);
  draw();
  return box;
}

export default {
  tabs: [{ id: "radar", label: "Radar", icon: "radar" }],
  status: (m) => (m.status?.laeuft ? "" : "off"),
  card(m) {
    return el("div", { class: "row wrap" }, statusChip(m.status));
  },
  render(_tab, ctx) {
    return seite(ctx);
  },
};
