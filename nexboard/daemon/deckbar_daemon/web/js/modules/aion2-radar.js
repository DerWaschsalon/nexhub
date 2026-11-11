/* Modul AION 2 · Radar: die Seiten „Warnungen“ und „Radar & Karte“. Die Feldbosse stehen unter Termine.
   Das Radar selbst läuft im Daemon und zeigt sich als Widgets im Overlay (Cube-Radar, Karte, Boss-Warnungen);
   ein- und ausschalten, Deckkraft und Position dort unter Overlay. Charaktername und Sprache stehen
   unter System → Einstellungen. */
import { fill, el, api, S, field, input, select, button, chip, card, settingsRow, sw, saver, toast, seg, collapsible } from "../core.js";

const REICHWEITEN = { 50: "50 m", 100: "100 m", 150: "150 m", 300: "300 m", 600: "600 m" };
const DREHUNG = { 0: "0°", 90: "90°", 180: "180°", 270: "270°" };
const TON = { aus: "Aus", piep: "Piepton", ansage: "Ansage" };
// Wörter wie im A2Tools-Plugin „Boss Callouts“, von dem die Boss-Ansagen stammen
const STIL = { beides: "Kurze Ansage und der Satz des Bosses", anweisung: "Kurze Ansage", zeile: "Der Satz des Bosses" };
const EIGENE_HINWEIS = "Wird statt dieses Rufs gesagt und gezeigt, egal welcher Rufstil. Leer: die Vorgabe.";
const AUS_HINWEIS = "Ein abgehakter Ruf ist ganz aus, auch sein Countdown. Um ihn zu behalten, aber weniger zu hören: Rufstil auf Kurze Ansage stellen oder ihm eigene Worte geben.";
const PRESETS = [
  { id: "aus", label: "Aus", icon: "bell-off" },
  { id: "wichtig", label: "Nur Wichtiges", icon: "bell" },
  { id: "alles", label: "Alles", icon: "bell-ring" },
];
const PRESET_HELP = {
  aus: "Keine Boss-Warnungen und Ansagen.",
  wichtig: "Nur was dich betrifft: Flächen, Angriffe auf alle und Effekte auf dir. Schweigt bei Angriffen auf andere Spieler.",
  alles: "Auch Angriffe und Effekte auf andere Spieler, z. B. „Todesmal auf …“ oder Mitspieler mit wenig LP.",
};

async function refresh() {
  try { S.radar = await api("GET", "/api/radar"); } catch { /* bleibt */ }
}

async function befehl(name, text) {
  try {
    S.radar = await api("POST", "/api/radar/befehl", { befehl: name });
    toast(text);
  } catch (e) { toast(e.message, true); }
}

async function rufTesten(schluessel) {
  try { S.radar = await api("POST", "/api/radar/befehl", { befehl: "ansage_testen", ruf: schluessel }); } catch (e) { toast(e.message, true); }
}

// Aufgeklappte Ruf-Listen; die Seite zeichnet alle 5 s neu, dabei sollen sie offen bleiben
const offen = new Set();

/** Die Rufe eines Bosses: Haken, Art, Vorgabe, eigene Worte, zurück zur Vorgabe, abspielen. */
function rufListe(r, gruppe, setzen) {
  const rufe = r.ansagen[gruppe];
  const k = r.einstellungen;
  const zeilen = rufe.map((ruf) => {
    const eigene = k.eigene_worte[ruf.schluessel] || "";
    const worte = (text) => {
      const neu = { ...k.eigene_worte };
      if (text.trim()) neu[ruf.schluessel] = text.trim(); else delete neu[ruf.schluessel];
      setzen("eigene_worte", neu);
    };
    return el("tr", {},
      el("td", {}, sw(!k.ruf_aus.includes(ruf.schluessel), (an) =>
        setzen("ruf_aus", an ? k.ruf_aus.filter((x) => x !== ruf.schluessel) : [...k.ruf_aus, ruf.schluessel]))),
      el("td", { class: "small muted", text: ruf.art }),
      el("td", {}, el("div", { text: ruf.vorgabe }), ruf.zeile ? el("div", { class: "small muted", text: ruf.zeile }) : null),
      el("td", {}, input(eigene, worte, { lazy: true, placeholder: "Eigene Worte", maxlength: 120, title: EIGENE_HINWEIS })),
      el("td", {}, el("div", { class: "row" },
        eigene ? button("", () => worte(""), "sm", "close", { title: "Zurück zur Vorgabe" }) : null,
        button("", () => rufTesten(ruf.schluessel), "sm", "play", { title: "Diesen Ruf abspielen", disabled: !r.laeuft }))));
  });
  const liste = el("details", { open: offen.has(gruppe) }, el("summary", { class: "small", text: `${rufe.length} Rufe` }),
    el("div", { class: "small muted", text: AUS_HINWEIS }),
    el("table", { class: "list" }, el("tbody", {}, zeilen)));
  liste.addEventListener("toggle", () => (liste.open ? offen.add(gruppe) : offen.delete(gruppe)));
  return liste;
}

function statusChip(r) {
  if (!r) return chip("…");
  if (r.fehler) return chip(`Fehler: ${r.fehler}`, "bad");
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

/** setzen(Schlüssel, Wert) für eine Seite: sofort im Stand, gespeichert gesammelt nach kurzer Pause. */
function radarSaver() {
  const save = saver("PUT", "/api/radar", (res) => { S.radar = res; }, 300, "Radar gespeichert");
  return (key, value) => { S.radar.einstellungen[key] = value; save({ [key]: value }); };
}

/** Knopf für einen Befehl ans laufende Radar. */
function knopf(r, text, name, ic, erledigt) {
  return button(text, () => befehl(name, erledigt), "sm", ic, { disabled: !r.laeuft });
}

/** Warnungen des gewählten Dungeons: je Gruppe anzeigen und Ton, je Boss die Rufe. */
function dungeonTable(r, setzen, draw) {
  const k = r.einstellungen;
  const neuZeichnen = (schluessel, wert) => { setzen(schluessel, wert); draw(); };  // „Zurück“-Knopf erscheint
  const dungeons = r.meldungen.dungeons || {};
  const eigene = dungeons[k.meldungen_dungeon] || {};
  const gruppen = { ...(Object.keys(eigene).length ? eigene : { casts: "Alle Boss-Casts zeigen (Lernhilfe)" }), ...r.meldungen.alle };
  const zeilen = Object.entries(gruppen).map(([gruppe, name]) => el("tr", {},
    el("td", {}, el("div", { text: name }), r.ansagen?.[gruppe] ? rufListe(r, gruppe, neuZeichnen) : null),
    el("td", {}, sw(!k.meldung_aus.includes(gruppe), (an) =>
      setzen("meldung_aus", an ? k.meldung_aus.filter((g) => g !== gruppe) : [...k.meldung_aus, gruppe]))),
    el("td", {}, select(TON, k.warnton[gruppe] || "ansage", (art) => setzen("warnton", { ...k.warnton, [gruppe]: art })))));
  return [
    field("Dungeon", select(Object.fromEntries(Object.keys(dungeons).map((d) => [d, d])), k.meldungen_dungeon, (v) => neuZeichnen("meldungen_dungeon", v))),
    el("div", { style: "overflow-x:auto" }, el("table", { class: "list" },
      el("thead", {}, el("tr", {}, ["Meldung", "Anzeigen", "Ton"].map((h) => el("th", { text: h })))),
      el("tbody", {}, zeilen))),
  ];
}

function warnungen(ctx) {
  const box = el("div", { class: "stack" });
  const view = {};
  const setzen = radarSaver();
  const draw = () => {
    const r = S.radar;
    if (!r) return;
    const k = r.einstellungen;
    const preset = async (id) => {
      try { S.radar = await api("PUT", "/api/radar", r.presets[id]); draw(); } catch (e) { toast(e.message, true); }
    };
    fill(box,
      card("Boss-Warnungen", PRESET_HELP[r.preset] || "Eigene Einstellungen", knopf(r, "Testen", "warnung_testen", "bell-ring", "Testwarnung gezeigt"),
        seg(PRESETS, r.preset, preset),
        collapsible("Erweitert", view,
          settingsRow("Art der Ansage", "Kurze Ansage: die Farbe oder was zu tun ist, mit Countdown, ohne den Satz des Bosses.", select(STIL, k.ansage_stil, (v) => setzen("ansage_stil", v))),
          settingsRow("Piepton bei jeder Welle", "Vakrons Sprung", sw(k.wellen_ton, (v) => setzen("wellen_ton", v))),
          ...dungeonTable(r, setzen, draw),
          settingsRow("Lernmodus: Dungeons aufnehmen", "Jeder Lauf wird eine eigene Aufnahme, zum Lernen neuer Mechaniken. Braucht viel Platz.", sw(k.aufnahme_auto, (v) => setzen("aufnahme_auto", v))),
          el("div", { class: "row wrap" }, r.aufnahme ? knopf(r, "Aufnahme stoppen", "aufnahme_stopp", "stop", "Aufnahme gestoppt")
            : knopf(r, "Aufnahme starten", "aufnahme_start", "record", "Aufnahme läuft")))));
  };
  auffrischen(ctx, box, refresh, draw);
  draw();
  return box;
}

function radarUndKarte(ctx) {
  const box = el("div", { class: "stack" });
  const view = {};
  const setzen = radarSaver();
  const draw = () => {
    const r = S.radar;
    if (!r) return;
    const k = r.einstellungen;
    const karten = Object.fromEntries([["", "automatisch"], ...r.karten.map((n) => [n, n])]);
    fill(box,
      el("div", { class: "cols" },
        card("Radar", "Läuft mit AION 2 und endet 30 s nach dem Spiel", statusChip(r),
          el("div", { class: "row wrap" },
            button("Radar neu starten", () => befehl("neustart", "Radar startet neu"), "sm", "restart", { disabled: !r.spiel }),
            knopf(r, "Ton testen", "ton_testen", "volume-high", "Ton gespielt")),
          settingsRow("Ton bei neuem Cube", null, sw(k.ton, (v) => setzen("ton", v))),
          settingsRow("Reichweite", null, select(REICHWEITEN, String(k.reichweite), (v) => setzen("reichweite", Number(v)))),
          settingsRow("Ausrichtung drehen", null, select(DREHUNG, String(k.drehung), (v) => setzen("drehung", Number(v)))),
          settingsRow("Spiegeln (Ost/West)", null, sw(k.spiegeln, (v) => setzen("spiegeln", v))),
          collapsible("Erweitert", view,
            settingsRow("Laufrichtung oben", "Dreht das Radar mit, statt Norden oben. Ungeprüft.", sw(k.kurs_oben, (v) => setzen("kurs_oben", v))))),
        card("Karte", "Cube-Fundorte, Teleporter, gesehene Spawnpunkte und deine Position", null,
          settingsRow("Karte", null, select(karten, k.karte_name || "", (v) => setzen("karte_name", v))),
          settingsRow("Spieler folgen", "Ziehen pausiert es, Doppelklick auf die Karte folgt wieder", sw(k.karte_folgen, (v) => setzen("karte_folgen", v))),
          settingsRow("Overlay bei offener Ingame-Karte ausblenden", "Erkennt die Karte an der Feldboss-Abfrage, etwa 1 s Verzögerung", sw(k.bei_karte_ausblenden, (v) => setzen("bei_karte_ausblenden", v))))));
  };
  auffrischen(ctx, box, refresh, draw);
  draw();
  return box;
}

export default {
  status: (m) => (m.status?.fehler ? "bad" : m.status?.laeuft ? "" : "off"),
  card(m) {
    return el("div", { class: "row wrap" }, statusChip(m.status));
  },
  pages: [
    { id: "aion2.warnings", name: "Warnungen", icon: "bell-alert", render: (tab, ctx) => warnungen(ctx) },
    { id: "aion2.radar", name: "Radar & Karte", icon: "radar", render: (tab, ctx) => radarUndKarte(ctx) },
  ],
};
