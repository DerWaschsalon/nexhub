/* PvP der laufenden Sitzung im Overlay. Die Daten kommen mit dem Overlay-Ereignis „radar“ (Feld pvp,
 * radar/radar/pvp.py), das Widget braucht also das Modul AION 2 · Radar. Läuft vor overlay.js und
 * nutzt dessen Layout und Modus erst beim Aufruf (W, mode, fmt).
 *
 * Kills und Tode zählen live mit. Rangpunkte, Rang und Assists kommen aus der Saisonwertung, die der
 * Server nur etwa stündlich neu rechnet; „Stand“ sagt, wann sie zuletzt kam. */
"use strict";

const PVP_BEISPIEL = { kills: 3, tode: 1, assists: 4, punkte: 1312, rang: 1090, rang_plus: 12, grad: "Soldat Rang 9",
  stand: Date.now() / 1000, beginn: Date.now() / 1000 - 1500, letzte: [["kill", "Spieler"], ["tod", "Spieler"]] };
const zahl = new Intl.NumberFormat("de-DE");

function zeichnePvp() {
  const d = radar.aktiv ? radar.pvp : mode === "edit" ? PVP_BEISPIEL : null;
  W.pvp.classList.toggle("idle", !d);
  if (!d) return;
  document.getElementById("pvp-zeit").textContent = fmt(Date.now() / 1000 - d.beginn);
  document.getElementById("pvp-kda").replaceChildren(
    pvpWert(d.kills, "Kills"), pvpWert(d.tode, "Tode"), pvpWert(d.assists ?? "–", "Assists"),
    pvpWert(((d.kills + (d.assists ?? 0)) / Math.max(1, d.tode)).toFixed(1).replace(".", ","), "KDA"));
  document.getElementById("pvp-punkte").replaceChildren(...pvpPunkte(d));
  document.getElementById("pvp-letzte").replaceChildren(...d.letzte.map(([art, name]) => {
    const zeile = document.createElement("div");
    zeile.className = art;
    zeile.textContent = `${art === "kill" ? "⚔" : "✝"} ${name}`;
    return zeile;
  }));
}

function pvpWert(wert, text) {
  const box = document.createElement("div");
  const b = document.createElement("b");
  b.textContent = wert;
  const span = document.createElement("span");
  span.textContent = text;
  box.append(b, span);
  return box;
}

/** Zuwachs an Rangpunkten und der Rang, solange die Saisonwertung bekannt ist. */
function pvpPunkte(d) {
  if (d.rang == null) return [pvpText("Rangpunkte kommen beim nächsten Zonenwechsel", "leise")];
  const plus = d.punkte >= 0 ? "+" : "";
  const pfeil = d.rang_plus > 0 ? ` ▲${d.rang_plus}` : d.rang_plus < 0 ? ` ▼${-d.rang_plus}` : "";
  const stand = new Date(d.stand * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  return [pvpText(`Rangpunkte ${plus}${zahl.format(d.punkte)}`, d.punkte > 0 ? "plus" : ""),
    pvpText(`Rang ${zahl.format(d.rang)}${pfeil} · ${d.grad}`, ""),
    pvpText(`Stand ${stand}`, "leise")];
}

function pvpText(text, klasse) {
  const el = document.createElement("div");
  el.className = klasse;
  el.textContent = text;
  return el;
}
