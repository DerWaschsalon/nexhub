/* Modul AION 2 · Radar im Overlay: das Radar-Widget und die Boss-Warnungen. Die Daten kommen als
 * Overlay-Ereignis „radar“ (RadarDienst im Daemon, etwa fünfmal pro Sekunde). Läuft vor overlay.js
 * und nutzt dessen Layout und Modus erst beim Aufruf (cfg, W, mode, regionsSoon).
 *
 * Radar:      ein Widget für alles, drei Reiter:
 *   Karte      Karte und Monster des Pet Soul Trackers (seine MiniMap aus dem installierten Plugin,
 *              seine Szene kommt als Widget-Nachricht), darüber Cubes, Spawnpunkte, Fundorte und
 *              Teleporter. Ziehen = verschieben, Mausrad = Zoom, Doppelklick = wieder dir folgen.
 *              Der Radarkreis erscheint, solange ein Cube in Sicht ist.
 *   Vertraute  die Seite des Pet Soul Trackers (tippen nur im Bearbeiten-Modus: sonst keine Tastatur)
 *   Würfel     die Seite von Dice Rolls; eine laufende Würfelkarte steht über jedem Reiter
 * Warnungen:  nur, solange eine läuft oder eine Vorhersage ansteht */
"use strict";

const FARBE = {
  grund: "rgb(10, 16, 28)", ring: "rgb(70, 90, 120)", ich: "rgb(0, 230, 118)", cube: "rgb(255, 82, 82)",
  gruppe: "rgb(80, 170, 255)", feldboss: "rgb(186, 85, 255)", oeffnen: "rgb(255, 160, 40)",
  leise: "rgb(120, 135, 160)", fundort: "rgba(245, 185, 65, .5)", punktRadar: "rgb(255, 196, 0)",
  punktHand: "rgb(200, 210, 230)",
};
const RADAR_PX = 260;
const SYMBOL_PX = 20; // Teleporter-Symbol, bleibt beim Zoomen gleich groß

let radar = { aktiv: false };
const karte = { daten: null, symbol: null, schluessel: "", laedt: false, gemalt: null, map: null, szene: null,
  folgenEinstellung: null };

/** Vom Daemon: neuer Stand (oder {aktiv: false}, wenn das Spiel weg ist). */
function onRadar(stand) {
  radar = stand;
  // Ingame-Karte offen: ganzes Overlay ausblenden (nicht beim Anordnen)
  document.body.classList.toggle("karte-offen", !!stand.karte_offen && mode !== "edit");
  radarNeuZeichnen();
}

function radarNeuZeichnen() {
  if (!layout) return;
  zeichneRadar();
  zeichneWarnungen();
  karteAktualisieren();
  zeichnePvp();
  regionsSoon();
}

/* ================================================================ Zeichenhilfen */
function kreis(c, x, y, r) {
  c.beginPath();
  c.arc(x, y, r, 0, 2 * Math.PI);
}

function linie(c, x1, y1, x2, y2) {
  c.beginPath();
  c.moveTo(x1, y1);
  c.lineTo(x2, y2);
  c.stroke();
}

function schrift(c, text, x, y, farbe, groesse) {
  c.fillStyle = farbe;
  c.font = `${groesse}px Inter, "Noto Sans", sans-serif`;
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.fillText(text, x, y);
}

/** Leinwand in doppelter Auflösung, damit sie auch vergrößert scharf bleibt. */
function leinwand(el, breite, hoehe) {
  if (el.width !== breite * 2 || el.height !== hoehe * 2) {
    el.width = breite * 2;
    el.height = hoehe * 2;
  }
  const c = el.getContext("2d");
  c.setTransform(2, 0, 0, 2, 0, 0);
  c.clearRect(0, 0, breite, hoehe);
  return c;
}

const minSek = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/* ================================================================ Radar */
/** Drehung des Radars: fest eingestellt, oder so, dass die Laufrichtung oben ist (radar.kurs). */
function drehwinkel(e) {
  if (!e.kurs_oben || !radar.kurs) return (e.drehung * Math.PI) / 180;
  const [kx, ky] = radar.kurs;
  return -Math.atan2(e.spiegeln ? -kx : kx, -ky);
}

/** Weltversatz (cm) → Bildschirmversatz. Norden ist Welt −y, Osten +x; dazu Drehen und Spiegeln. */
function aufSchirm(dx, dy) {
  const e = radar.einstellungen;
  const sx = e.spiegeln ? -dx : dx;
  const w = drehwinkel(e);
  return [sx * Math.cos(w) - dy * Math.sin(w), sx * Math.sin(w) + dy * Math.cos(w)];
}

function zeichneRadar() {
  const cubes = radar.aktiv ? radar.cubes : [];
  document.getElementById("radar-bild").hidden = !cubes.length;
  const c = leinwand(document.getElementById("radar-bild"), RADAR_PX, RADAR_PX);
  const m = RADAR_PX / 2;
  const r = m - 4;
  c.fillStyle = FARBE.grund;
  c.strokeStyle = FARBE.ring;
  c.lineWidth = 1.5;
  kreis(c, m, m, r);
  c.fill();
  c.stroke();
  c.lineWidth = 1;
  c.setLineDash([4, 4]);
  kreis(c, m, m, r / 2);
  c.stroke();
  linie(c, m, m - r + 8, m, m + r - 8);
  linie(c, m - r + 8, m, m + r - 8, m);
  c.setLineDash([]);
  if (!radar.aktiv) {
    zeile("kein Cube in Sicht", "", "Radar läuft, sobald AION 2 läuft");
    return;
  }
  const e = radar.einstellungen;
  const [nx, ny] = aufSchirm(0, -1);
  const n = Math.hypot(nx, ny);
  schrift(c, "N", m + (nx / n) * (r - 9), m + (ny / n) * (r - 9), FARBE.leise, 10);
  schrift(c, `${e.reichweite} m`, m, m + r - 16, FARBE.leise, 10);
  const pos = radar.position;
  if (!pos) {
    zeile(cubes.length ? `${cubes.length} Cube(s), eigene Position fehlt` : "kein Cube in Sicht", "", radar.status);
    return;
  }
  const mass = (r - 10) / (e.reichweite * 100);
  const innen = (ox, oy) => Math.hypot(ox, oy) < r - 10;
  let naechster = null;
  for (const cube of cubes) {
    const [dx, dy, dz] = [cube.x - pos[0], cube.y - pos[1], cube.z - pos[2]];
    const dist = Math.hypot(dx, dy, dz);
    let [ox, oy] = aufSchirm(dx * mass, dy * mass);
    const aussen = !innen(ox, oy);
    if (aussen) { // am Rand festhalten, Richtung bleibt
      const f = (r - 10) / Math.hypot(ox, oy);
      [ox, oy] = [ox * f, oy * f];
    }
    if (!naechster || dist < naechster.dist) naechster = { dist, dz, x: m + ox, y: m + oy, cube };
    const farbe = cube.oeffner ? FARBE.oeffnen : FARBE.cube; // orange: jemand öffnet ihn gerade
    c.strokeStyle = farbe;
    c.fillStyle = farbe;
    c.lineWidth = 2;
    kreis(c, m + ox, m + oy, 5);
    if (aussen) c.stroke(); else c.fill();
  }
  for (const g of radar.gruppe) { // Gruppenmitglieder (kommen nur alle 2 s, also grob)
    const [ox, oy] = aufSchirm((g.x - pos[0]) * mass, (g.y - pos[1]) * mass);
    if (!innen(ox, oy)) continue;
    c.fillStyle = FARBE.gruppe;
    kreis(c, m + ox, m + oy, 4);
    c.fill();
    schrift(c, g.name.slice(0, 8), m + ox, m + oy + 10, FARBE.gruppe, 9);
  }
  for (const [bx, by] of radar.feldbosse) { // lebende Feldbosse der Karte als Raute
    const [ox, oy] = aufSchirm((bx - pos[0]) * mass, (by - pos[1]) * mass);
    if (!innen(ox, oy)) continue;
    const [x, y] = [m + ox, m + oy];
    c.fillStyle = FARBE.feldboss;
    c.beginPath();
    c.moveTo(x, y - 6); c.lineTo(x + 6, y); c.lineTo(x, y + 6); c.lineTo(x - 6, y);
    c.fill();
  }
  if (naechster) {
    c.strokeStyle = FARBE.cube;
    c.setLineDash([2, 3]);
    linie(c, m, m, naechster.x, naechster.y);
    c.setLineDash([]);
  }
  c.fillStyle = FARBE.ich;
  kreis(c, m, m, 5);
  c.fill();
  zeile(cubeText(naechster, cubes.length), naechster?.cube.oeffner ? "oeffnet" : "", radar.status);
}

function cubeText(naechster, anzahl) {
  if (!naechster) return "kein Cube in Sicht";
  const { dist, dz, cube } = naechster;
  let text = cube.oeffner ? `Cube wird geöffnet: ${cube.oeffner}`
    : `Cube: ${Math.round(dist / 100)} m (${dz >= 0 ? "+" : ""}${Math.round(dz / 100)} m) · ${minSek(cube.alter)}`;
  if (anzahl > 1) text += `  · ${anzahl} Cubes`;
  return text;
}

function zeile(cube, klasse, status) {
  const el = document.getElementById("radar-cube");
  el.textContent = cube;
  el.className = klasse;
  document.getElementById("radar-status").textContent = status;
}

/* ================================================================ Boss-Warnungen */
function zeichneWarnungen() {
  const liste = radar.aktiv ? radar.warnungen : [];
  const vorschau = radar.aktiv ? radar.vorschau : [];
  W.warnung.classList.toggle("idle", !liste.length && !vorschau.length && mode !== "edit");
  const kopf = document.getElementById("warn-vorschau");
  kopf.hidden = !vorschau.length;
  kopf.textContent = vorschau.map(([t, rest]) => (rest <= 0 ? t : `${t} in ${Math.round(rest)} s`)).join("  ·  ");
  kopf.classList.toggle("offen", vorschau.some(([, rest]) => rest <= 0)); // Regen jederzeit möglich
  const kasten = liste.length ? liste.map(warnKasten)
    : mode === "edit" ? [warnKasten({ titel: "Boss-Warnungen", hinweis: "erscheinen hier im Kampf", rest: 3,
      vorlauf: 4, farbe: [106, 166, 255], lernhilfe: false })] : [];
  document.getElementById("warn-liste").replaceChildren(...kasten);
}

function warnKasten(w) {
  const box = document.createElement("div");
  box.className = "warn";
  box.style.setProperty("--farbe", `rgb(${w.farbe.join(", ")})`);
  if (w.rest <= 0 && Math.floor(Date.now() / 1000 * 6) % 2) box.classList.add("blinkt");
  const titel = document.createElement("span");
  titel.className = "warn-titel";
  titel.textContent = w.titel;
  const zeit = document.createElement("span");
  zeit.className = "warn-zeit";
  // Lernhilfe: der echte Vorlauf ist unbekannt, also keine Sekunden
  if (!w.lernhilfe) zeit.textContent = w.rest > 0 ? w.rest.toFixed(1) : radar.jetzt_text;
  const kopf = document.createElement("div");
  kopf.className = "warn-kopf";
  kopf.append(titel, zeit);
  const hinweis = document.createElement("div");
  hinweis.className = "warn-hinweis";
  hinweis.textContent = w.hinweis;
  const balken = document.createElement("div");
  balken.className = "warn-balken";
  balken.append(document.createElement("div"));
  balken.firstChild.style.transform = `scaleX(${Math.max(0, w.rest / w.vorlauf)})`;
  box.append(kopf, hinweis, balken);
  return box;
}

/* ================================================================ Karte */
const PLUGIN_DATEIEN = "/__a2plugin__/pet-souls/";
const geeicht = () => !!karte.daten?.m;

/** Teleporter und Fundorte sind in Bild-Koordinaten der eigenen Karte: zurück in die Welt. */
function bildZuWelt(u, v) {
  const [a, b, c, d, e, f] = karte.daten.m;
  const det = a * e - b * d;
  return [(e * (u - c) - b * (v - f)) / det, (a * (v - f) - d * (u - c)) / det];
}

/** Kartendaten neu holen, wenn eine andere Karte gewählt ist oder neue Spawnpunkte dazukamen. */
async function karteLaden() {
  const schluessel = `${radar.karte}|${radar.punkte}`;
  if (schluessel === karte.schluessel || karte.laedt) return;
  karte.laedt = true;
  try {
    const daten = await (await fetch("/api/radar/karte")).json();
    karte.daten = daten;
    karte.schluessel = schluessel;
    if (daten.symbol && daten.name) {
      const img = new Image();
      img.onload = () => { karte.symbol = img; };
      img.src = `/api/radar/karte/symbol?karte=${encodeURIComponent(daten.name)}`;
    }
  } catch (e) {
    log(`Karte nicht geladen: ${e}`);
  } finally {
    karte.laedt = false;
  }
}

function skriptLaden(url) {
  return new Promise((ok, fehler) => {
    const s = document.createElement("script");
    s.src = url;
    s.onload = ok;
    s.onerror = fehler;
    document.head.append(s);
  });
}

/** MiniMap und Karten kommen aus dem installierten Pet Soul Tracker, nichts davon liegt hier doppelt. */
function miniKarteStarten() {
  karte.start ||= miniKarteLaden();
  return karte.start;
}

async function miniKarteLaden() {
  try {
    await skriptLaden(`${PLUGIN_DATEIEN}maps.js`);
    await skriptLaden(`${PLUGIN_DATEIEN}minimap.js`);
  } catch {
    return false;
  }
  const bilder = document.getElementById("karte-bilder");
  for (const id of Object.keys(PET_MAPS)) {
    const img = document.createElement("img");
    img.className = "mapPic";
    img.dataset.map = id;
    img.loading = "lazy";
    img.src = `${PLUGIN_DATEIEN}maps/${id}.webp`;
    bilder.append(img);
  }
  const $ = (id) => document.getElementById(id);
  karte.map = new PetMiniMap.MiniMap(
    { canvas: $("karte-bild"), zoomIn: $("karte-rein"), zoomOut: $("karte-raus"), follow: $("karte-folgen"), note: $("karte-notiz") },
    { onZoom: (zoom) => szeneAntwort({ zoom }) },
  );
  const malen = karte.map.draw.bind(karte.map);
  karte.map.draw = () => {
    malen();
    radarEbene();
  };
  karte.map.set({});
  return true;
}

function szeneAntwort(data) {
  return fetch("/api/a2/invoke", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd: "plugin_widget_post", args: { data }, window: "widget:pet-souls:map" }),
  }).catch(() => {});
}

/** Vom Pet Soul Tracker: was er auf seine Karte zeichnen würde (plugins.js fängt es ab). */
function karteSzene(szene) {
  if (!szene || typeof szene !== "object") return;
  if (!karte.szene && szene.zoom != null) karte.map?.setZoom(szene.zoom);
  karte.szene = szene;
  karteAktualisieren();
}

/** Die Karte, auf der wir sind: die des Plugins, sonst die eingestellte des Radars. */
function aktuelleKarte() {
  if (karte.szene?.mapId) return karte.szene.mapId;
  if (typeof PET_MAPS === "undefined" || !radar.karte) return null;
  return Object.keys(PET_MAPS).find((id) => PET_MAPS[id].name === radar.karte) || null;
}

function karteAktualisieren() {
  if (!radar.aktiv && !karte.szene) return;
  if (radar.aktiv) karteLaden();
  const m = karte.map;
  if (!m) {
    miniKarteStarten().then((ok) => {
      if (ok) karteAktualisieren();
      else document.getElementById("karte-name").textContent = "Pet Soul Tracker fehlt";
    });
    return;
  }
  const folgen = radar.einstellungen?.karte_folgen;
  if (folgen !== karte.folgenEinstellung) { // auf der NexBoard-Seite umgestellt
    karte.folgenEinstellung = folgen;
    m.follow = !!folgen;
  }
  const s = karte.szene || {};
  // Das Radar kennt die Position meist früher und genauer als die Szene
  const you = radar.position
    ? { pos: radar.position, at: Date.now() - (radar.position_alter || 0) * 1000, estimated: false }
    : s.you || null;
  m.set({ mapId: aktuelleKarte(), you, wanted: s.wanted || [], others: s.others || [],
    spawnColours: s.spawnColours || {}, labels: s.labels || {} });
  document.getElementById("karte-name").textContent = s.title || radar.karte || "";
  const teile = [];
  if (s.count) teile.push(s.count);
  if (karte.daten?.punkte?.length) teile.push(`${karte.daten.punkte.length} Spawnpunkte`);
  document.getElementById("karte-status").textContent = teile.join(" · ");
}

/** Über dem Bild der MiniMap: was nur das Radar kennt. Gleiche Rechnung wie MiniMap.draw. */
function radarEbene() {
  const m = karte.map;
  const el = document.getElementById("karte-bild");
  if (!m?.center || !el.isConnected) return;
  const w = el.clientWidth || 300;
  const h = el.clientHeight || 220;
  const proPixel = m.zoom * 100;
  const schirm = (x, y) => [w / 2 + (x - m.center[0]) / proPixel, h / 2 + (y - m.center[1]) / proPixel];
  const c = el.getContext("2d");
  const eigeneKarte = karte.daten && PET_MAPS[m.scene.mapId]?.name === karte.daten.name && geeicht();
  karte.gemalt = [];
  if (eigeneKarte) {
    c.fillStyle = FARBE.fundort;
    for (const [u, v] of karte.daten.fundorte || []) {
      kreis(c, ...schirm(...bildZuWelt(u, v)), 3.5);
      c.fill();
    }
    c.lineWidth = 1.6;
    for (const [x, y, quelle] of karte.daten.punkte || []) {
      c.strokeStyle = quelle === "radar" ? FARBE.punktRadar : FARBE.punktHand;
      kreis(c, ...schirm(x, y), 4.5);
      c.stroke();
    }
    if (karte.symbol) {
      for (const [name, u, v] of karte.daten.teleporter || []) {
        const [x, y] = schirm(...bildZuWelt(u, v));
        c.drawImage(karte.symbol, x - SYMBOL_PX / 2, y - SYMBOL_PX / 2, SYMBOL_PX, SYMBOL_PX);
        karte.gemalt.push([name, x, y]);
      }
    }
  }
  const puls = 0.5 + 0.5 * Math.sin(Date.now() / 200);
  for (const cube of radar.aktiv ? radar.cubes || [] : []) {
    const [x, y] = schirm(cube.x, cube.y);
    c.fillStyle = `rgba(255, 82, 82, ${(60 + 80 * puls) / 255})`;
    kreis(c, x, y, 9 + 4 * puls);
    c.fill();
    c.fillStyle = FARBE.cube;
    kreis(c, x, y, 5);
    c.fill();
  }
}

function teleporterTipp(e) {
  const tipp = document.getElementById("karte-tipp");
  const r = document.getElementById("karte-bild").getBoundingClientRect();
  const s = cfg("radar").scale || 1;
  const [mx, my] = [(e.clientX - r.left) / s, (e.clientY - r.top) / s];
  const treffer = (karte.gemalt || []).find(([, x, y]) => Math.abs(x - mx) <= SYMBOL_PX / 2 && Math.abs(y - my) <= SYMBOL_PX / 2);
  tipp.hidden = !treffer;
  if (!treffer) return;
  tipp.textContent = treffer[0];
  tipp.style.left = `${mx + 12}px`;
  tipp.style.top = `${my + 12}px`;
}

/* ================================================================ Reiter */
const EINGEBETTET = { "pet-souls": "vertraute", "dice-rolls": "wuerfel" };

function reiterZeigen(name) {
  W.radar.classList.remove("gefaltet");
  for (const b of W.radar.querySelectorAll("[data-reiter]")) b.classList.toggle("an", b.dataset.reiter === name);
  for (const s of W.radar.querySelectorAll("[data-seite]")) s.classList.toggle("an", s.dataset.seite === name);
  try { localStorage.setItem("radar-reiter", name); } catch {}
  karte.map?.draw();
  regionsSoon();
}

/** Die Seiten der beiden Plugins laufen hier, auch im verdeckten Reiter (Seelen zählen weiter). */
function eingebetteteLaden(ids) {
  for (const [plugin, seite] of Object.entries(EINGEBETTET)) {
    const ort = W.radar.querySelector(`[data-seite="${seite}"]`);
    const da = ort.querySelector("iframe");
    if (ids.includes(plugin) && !da) {
      const f = document.createElement("iframe");
      f.src = `/plugin-host.html?plugin=${plugin}`;
      ort.replaceChildren(f);
    } else if (!ids.includes(plugin)) {
      da?.remove();
      if (!ort.firstChild) ort.textContent = "";
    }
  }
}

/** Griff unten rechts: Breite und Höhe frei ziehen (das Mausrad im Bearbeiten-Modus skaliert dagegen alles). */
function griffStarten() {
  const griff = document.getElementById("radar-griff");
  griff.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation(); // sonst zieht der Bearbeiten-Modus das ganze Widget
    const c = cfg("radar");
    const s = c.scale || 1;
    const start = { x: e.clientX, y: e.clientY, w: c.width, h: c.height };
    griff.setPointerCapture(e.pointerId);
    dragging = true;
    const ziehen = (ev) => {
      c.width = Math.round(Math.max(300, Math.min(2000, innerWidth / s, start.w + (ev.clientX - start.x) / s)));
      c.height = Math.round(Math.max(220, Math.min(1600, innerHeight / s, start.h + (ev.clientY - start.y) / s)));
      place(W.radar);
    };
    const los = () => {
      griff.removeEventListener("pointermove", ziehen);
      dragging = false;
      regionsSoon();
      saveSoon();
    };
    griff.addEventListener("pointermove", ziehen);
    griff.addEventListener("pointerup", los, { once: true });
    griff.addEventListener("pointercancel", los, { once: true });
  });
  new ResizeObserver(() => karte.map?.draw()).observe(document.getElementById("karte-bild"));
}

function radarStart() {
  griffStarten();
  for (const b of W.radar.querySelectorAll("[data-reiter]")) b.addEventListener("click", () => reiterZeigen(b.dataset.reiter));
  document.getElementById("radar-falten").addEventListener("click", () => {
    W.radar.classList.toggle("gefaltet");
    try { localStorage.setItem("radar-falten", W.radar.classList.contains("gefaltet") ? "1" : ""); } catch {}
    regionsSoon();
  });
  try {
    reiterZeigen(localStorage.getItem("radar-reiter") || "karte");
    if (localStorage.getItem("radar-falten")) W.radar.classList.add("gefaltet");
  } catch {}
  document.getElementById("karte-bild").addEventListener("pointermove", teleporterTipp);
  miniKarteStarten().then((ok) => {
    if (ok) szeneAntwort({ hello: true });
    else document.getElementById("karte-name").textContent = "Pet Soul Tracker fehlt";
  });
  // Cubes pulsieren: auch ohne neue Daten neu zeichnen, solange einer da ist
  setInterval(() => { if (radar.aktiv && radar.cubes?.length) karte.map?.draw(); }, 100);
}
