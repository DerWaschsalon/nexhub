/* Modul AION 2 · Radar im Overlay: Radar, Boss-Warnungen und Karte. Die Daten kommen als
 * Overlay-Ereignis „radar“ (RadarDienst im Daemon, etwa fünfmal pro Sekunde). Läuft vor overlay.js
 * und nutzt dessen Layout und Modus erst beim Aufruf (cfg, W, mode, regionsSoon).
 *
 * Radar:      zeigt sich nur, solange ein Cube in Sicht ist
 * Warnungen:  nur, solange eine läuft oder eine Vorhersage ansteht
 * Karte:      ziehen = verschieben, Mausrad = Zoom (um die eigene Position, wenn bekannt),
 *             Doppelklick = wieder der eigenen Position folgen */
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
const karte = { daten: null, bild: null, symbol: null, schluessel: "", laedt: false, zoom: 1, versatz: [0, 0],
  folgen: false, folgenEinstellung: null, ziehen: null };

/** Vom Daemon: neuer Stand (oder {aktiv: false}, wenn das Spiel weg ist). */
function onRadar(stand) {
  radar = stand;
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
/** Weltversatz (cm) → Bildschirmversatz. Norden ist Welt −y, Osten +x; dazu Drehen und Spiegeln. */
function aufSchirm(dx, dy) {
  const e = radar.einstellungen;
  const sx = e.spiegeln ? -dx : dx;
  const w = (e.drehung * Math.PI) / 180;
  return [sx * Math.cos(w) - dy * Math.sin(w), sx * Math.sin(w) + dy * Math.cos(w)];
}

function zeichneRadar() {
  const cubes = radar.aktiv ? radar.cubes : [];
  W.radar.classList.toggle("idle", !cubes.length && mode !== "edit");
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
const geeicht = () => !!karte.daten?.m;

function weltZuBild(x, y) {
  const [a, b, c, d, e, f] = karte.daten.m;
  return [a * x + b * y + c, d * x + e * y + f];
}

function kartenFlaeche() {
  const el = document.getElementById("karte-bild");
  return [el.clientWidth, el.clientHeight];
}

function bildZuSchirm(u, v) {
  const [w, h] = kartenFlaeche();
  return [w / 2 + (u - karte.versatz[0]) * karte.zoom, h / 2 + (v - karte.versatz[1]) * karte.zoom];
}

function schirmZuBild(x, y) {
  const [w, h] = kartenFlaeche();
  return [karte.versatz[0] + (x - w / 2) / karte.zoom, karte.versatz[1] + (y - h / 2) / karte.zoom];
}

function bildLaden(url) {
  return new Promise((ok) => {
    const img = new Image();
    img.onload = () => ok(img);
    img.onerror = () => ok(null);
    img.src = url;
  });
}

/** Kartendaten neu holen, wenn eine andere Karte gewählt ist oder neue Spawnpunkte dazukamen. */
async function karteLaden() {
  const schluessel = `${radar.karte}|${radar.punkte}`;
  if (schluessel === karte.schluessel || karte.laedt) return;
  karte.laedt = true;
  try {
    const daten = await (await fetch("/api/radar/karte")).json();
    const andere = daten.name !== karte.daten?.name;
    karte.daten = daten;
    karte.schluessel = schluessel;
    if (andere) {
      const name = encodeURIComponent(daten.name);
      karte.bild = daten.name ? await bildLaden(`/api/radar/karte/bild?karte=${name}`) : null;
      karte.symbol = daten.symbol ? await bildLaden(`/api/radar/karte/symbol?karte=${name}`) : null;
      einpassen();
    }
  } catch (e) {
    log(`Karte nicht geladen: ${e}`);
  } finally {
    karte.laedt = false;
  }
}

function einpassen() {
  if (!karte.bild) return;
  const [w, h] = kartenFlaeche();
  karte.versatz = [karte.bild.width / 2, karte.bild.height / 2];
  karte.zoom = Math.min(w / karte.bild.width, h / karte.bild.height) || 1;
}

function karteAktualisieren() {
  W.karte.classList.toggle("idle", !radar.aktiv && mode !== "edit");
  if (!radar.aktiv || !cfg("karte").enabled) return;
  karteLaden();
  const folgen = radar.einstellungen.karte_folgen;
  if (folgen !== karte.folgenEinstellung) { // auf der NexBoard-Seite umgestellt
    karte.folgenEinstellung = folgen;
    karte.folgen = folgen;
  }
  if (karte.folgen && geeicht() && radar.position) karte.versatz = weltZuBild(...radar.position);
  zeichneKarte();
}

function zeichneKarte() {
  const [w, h] = kartenFlaeche();
  const c = leinwand(document.getElementById("karte-bild"), w, h);
  const d = karte.daten;
  document.getElementById("karte-name").textContent = d?.name || "Karte";
  if (!karte.bild) {
    schrift(c, "Noch keine Karte", w / 2, h / 2 - 9, FARBE.leise, 12);
    schrift(c, "python3 -m werkzeuge.cubekarte (in nexboard/radar)", w / 2, h / 2 + 9, FARBE.leise, 11);
    document.getElementById("karte-status").textContent = "";
    return;
  }
  const [ox, oy] = bildZuSchirm(0, 0);
  c.drawImage(karte.bild, ox, oy, karte.bild.width * karte.zoom, karte.bild.height * karte.zoom);
  c.fillStyle = FARBE.fundort; // bekannte Cube-Fundorte (aion2hub)
  for (const [u, v] of d.fundorte) {
    kreis(c, ...bildZuSchirm(u, v), 3.5);
    c.fill();
  }
  if (karte.symbol) {
    for (const [, u, v] of d.teleporter) {
      const [x, y] = bildZuSchirm(u, v);
      c.drawImage(karte.symbol, x - SYMBOL_PX / 2, y - SYMBOL_PX / 2, SYMBOL_PX, SYMBOL_PX);
    }
  }
  document.getElementById("karte-status").textContent = geeicht()
    ? `${d.punkte.length} Spawnpunkte · ${radar.cubes.length} aktiv` : "nicht geeicht";
  if (geeicht()) zeichneKartenInhalt(c);
}

function zeichneKartenInhalt(c) {
  c.lineWidth = 1.6;
  for (const [x, y, quelle] of karte.daten.punkte) { // gesehene Spawnpunkte
    c.strokeStyle = quelle === "radar" ? FARBE.punktRadar : FARBE.punktHand;
    kreis(c, ...bildZuSchirm(...weltZuBild(x, y)), 4.5);
    c.stroke();
  }
  const puls = 0.5 + 0.5 * Math.sin(Date.now() / 200);
  for (const cube of radar.cubes) {
    const [x, y] = bildZuSchirm(...weltZuBild(cube.x, cube.y));
    c.fillStyle = `rgba(255, 82, 82, ${(60 + 80 * puls) / 255})`;
    kreis(c, x, y, 9 + 4 * puls);
    c.fill();
    c.fillStyle = FARBE.cube;
    kreis(c, x, y, 5);
    c.fill();
  }
  if (radar.position) {
    const [x, y] = bildZuSchirm(...weltZuBild(...radar.position));
    c.globalAlpha = radar.position_alter > 30 ? 0.45 : 1; // veraltet
    c.fillStyle = FARBE.ich;
    c.strokeStyle = "rgba(255, 255, 255, .8)";
    c.lineWidth = 1.5;
    kreis(c, x, y, 5.5);
    c.fill();
    c.stroke();
    c.globalAlpha = 1;
  }
}

function teleporterTipp(e) {
  const tipp = document.getElementById("karte-tipp");
  const el = document.getElementById("karte-bild");
  const r = el.getBoundingClientRect();
  const s = cfg("karte").scale || 1;
  const [mx, my] = [(e.clientX - r.left) / s, (e.clientY - r.top) / s];
  const treffer = karte.symbol && karte.daten.teleporter.find(([, u, v]) => {
    const [x, y] = bildZuSchirm(u, v);
    return Math.abs(x - mx) <= SYMBOL_PX / 2 && Math.abs(y - my) <= SYMBOL_PX / 2;
  });
  tipp.hidden = !treffer;
  if (!treffer) return;
  tipp.textContent = treffer[0];
  tipp.style.left = `${el.offsetLeft + mx + 12}px`;
  tipp.style.top = `${el.offsetTop + my + 12}px`;
}

/** Maus auf der Karte; im Bearbeiten-Modus verschiebt overlay.js das ganze Widget. */
function radarStart() {
  const el = document.getElementById("karte-bild");
  const s = () => cfg("karte").scale || 1;
  el.addEventListener("pointerdown", (e) => {
    if (mode === "edit" || e.button !== 0 || !karte.bild) return;
    el.setPointerCapture(e.pointerId);
    karte.ziehen = { x: e.clientX, y: e.clientY, versatz: [...karte.versatz] };
  });
  el.addEventListener("pointermove", (e) => {
    if (!karte.ziehen) return teleporterTipp(e);
    const z = karte.ziehen;
    // Zittern beim Klicken ist kein Ziehen und soll das Folgen nicht beenden
    z.bewegt ||= Math.hypot(e.clientX - z.x, e.clientY - z.y) > 4;
    if (!z.bewegt) return;
    karte.folgen = false;
    karte.versatz = [z.versatz[0] - (e.clientX - z.x) / s() / karte.zoom, z.versatz[1] - (e.clientY - z.y) / s() / karte.zoom];
    zeichneKarte();
  });
  el.addEventListener("pointerup", () => { karte.ziehen = null; });
  el.addEventListener("dblclick", () => {
    if (mode === "edit") return;
    karte.folgen = true;
    karteAktualisieren();
  });
  el.addEventListener("wheel", (e) => {
    if (mode === "edit" || !karte.bild) return;
    e.preventDefault();
    // Zoom um die eigene Position, solange sie bekannt ist, sonst um den Punkt unter der Maus
    const r = el.getBoundingClientRect();
    const anker = geeicht() && radar.position ? bildZuSchirm(...weltZuBild(...radar.position))
      : [(e.clientX - r.left) / s(), (e.clientY - r.top) / s()];
    const unter = schirmZuBild(...anker);
    karte.zoom = Math.max(0.05, Math.min(8, karte.zoom * (e.deltaY < 0 ? 1.2 : 1 / 1.2)));
    const neu = schirmZuBild(...anker);
    karte.versatz = [karte.versatz[0] + unter[0] - neu[0], karte.versatz[1] + unter[1] - neu[1]];
    zeichneKarte();
  }, { passive: false });
}
