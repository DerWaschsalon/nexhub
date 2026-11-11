/* Cube-Radar des Moduls AION 2 · Radar: ein kleiner Kreis mit dir in der Mitte, der nur erscheint,
 * solange ein Hidden Cube in Sicht ist. Zeigt Richtung, Abstand und Höhe zum nächsten Cube, dazu
 * Gruppenmitglieder und lebende Feldbosse. Die Daten kommen mit dem Ereignis „radar“. */
import { el } from "../util.js";
import { COLOR, canvas2x, circle, label, line, minSec } from "./radar-draw.js";

const SIZE = 190; // Kantenlänge der Leinwand in CSS-Pixeln
const EDGE = 10; // Abstand der Punkte zum Kreisrand
// Beispiel im Bearbeiten-Modus: ein Cube 42 m nordöstlich
const EXAMPLE = {
  aktiv: true, position: [0, 0, 0], kurs: null, gruppe: [], feldbosse: [], status: "",
  cubes: [{ x: 3000, y: -3000, z: 400, alter: 75, oeffner: "" }],
  einstellungen: { reichweite: 100, drehung: 0, spiegeln: false, kurs_oben: false },
};

/** Drehung des Radars: fest eingestellt, oder so, dass die Laufrichtung oben ist (radar.kurs). */
function rotation(radar) {
  const e = radar.einstellungen;
  if (!e.kurs_oben || !radar.kurs) return (e.drehung * Math.PI) / 180;
  const [kx, ky] = radar.kurs;
  return -Math.atan2(e.spiegeln ? -kx : kx, -ky);
}

/** Weltversatz → Bildschirmversatz. Norden ist Welt −y, Osten +x; dazu Drehen und Spiegeln. */
function toScreen(radar, dx, dy) {
  const sx = radar.einstellungen.spiegeln ? -dx : dx;
  const w = rotation(radar);
  return [sx * Math.cos(w) - dy * Math.sin(w), sx * Math.sin(w) + dy * Math.cos(w)];
}

function drawGround(c, m, r) {
  c.fillStyle = COLOR.ground;
  c.strokeStyle = COLOR.ring;
  c.lineWidth = 1.5;
  circle(c, m, m, r);
  c.fill();
  c.stroke();
  c.lineWidth = 1;
  c.setLineDash([4, 4]);
  circle(c, m, m, r / 2);
  c.stroke();
  line(c, m, m - r + 8, m, m + r - 8);
  line(c, m - r + 8, m, m + r - 8, m);
  c.setLineDash([]);
}

/** Cubes zeichnen (außerhalb der Reichweite am Rand festgehalten) und den nächsten zurückgeben. */
function drawCubes(c, radar, m, reach, unit) {
  const [px, py, pz] = radar.position;
  let nearest = null;
  for (const cube of radar.cubes) {
    const [dx, dy, dz] = [cube.x - px, cube.y - py, cube.z - pz];
    const dist = Math.hypot(dx, dy, dz);
    let [ox, oy] = toScreen(radar, dx * unit, dy * unit);
    const outside = Math.hypot(ox, oy) >= reach;
    if (outside) { // am Rand festhalten, Richtung bleibt
      const f = reach / Math.hypot(ox, oy);
      [ox, oy] = [ox * f, oy * f];
    }
    if (!nearest || dist < nearest.dist) nearest = { dist, dz, x: m + ox, y: m + oy, cube };
    const color = cube.oeffner ? COLOR.opening : COLOR.cube; // orange: jemand öffnet ihn gerade
    c.strokeStyle = color;
    c.fillStyle = color;
    c.lineWidth = 2;
    circle(c, m + ox, m + oy, 5);
    if (outside) c.stroke(); else c.fill();
  }
  return nearest;
}

function drawOthers(c, radar, m, reach, unit) {
  const [px, py] = radar.position;
  const inside = (ox, oy) => Math.hypot(ox, oy) < reach;
  for (const member of radar.gruppe) { // Gruppenmitglieder (kommen nur alle 2 s, also grob)
    const [ox, oy] = toScreen(radar, (member.x - px) * unit, (member.y - py) * unit);
    if (!inside(ox, oy)) continue;
    c.fillStyle = COLOR.party;
    circle(c, m + ox, m + oy, 4);
    c.fill();
    label(c, member.name.slice(0, 8), m + ox, m + oy + 10, COLOR.party, 9);
  }
  for (const [bx, by] of radar.feldbosse) { // lebende Feldbosse der Karte als Raute
    const [ox, oy] = toScreen(radar, (bx - px) * unit, (by - py) * unit);
    if (!inside(ox, oy)) continue;
    const [x, y] = [m + ox, m + oy];
    c.fillStyle = COLOR.fieldBoss;
    c.beginPath();
    c.moveTo(x, y - 6); c.lineTo(x + 6, y); c.lineTo(x, y + 6); c.lineTo(x - 6, y);
    c.fill();
  }
}

function cubeText(nearest, count) {
  const { dist, dz, cube } = nearest;
  const meters = (cm) => Math.round(cm / 100);
  let text = cube.oeffner ? `Cube wird geöffnet: ${cube.oeffner}`
    : `${meters(dist)} m (${dz >= 0 ? "+" : ""}${meters(dz)} m) · ${minSec(cube.alter)}`;
  if (count > 1) text += ` · ${count} Cubes`;
  return text;
}

export default {
  events: ["radar"],
  hud: true,
  defaultPos: () => [innerWidth - SIZE - 60, 300],

  mount(root, ctx) {
    const canvas = root.appendChild(el("canvas"));
    const text = root.appendChild(el("div", "cube-text"));
    let radar = { aktiv: false };

    function render() {
      const live = radar.aktiv && radar.cubes.length > 0;
      const shown = live ? radar : ctx.mode() === "edit" ? EXAMPLE : null;
      ctx.setIdle(!shown);
      if (!shown) return;
      const c = canvas2x(canvas, SIZE, SIZE);
      const m = SIZE / 2;
      const r = m - 4;
      const reach = r - EDGE;
      drawGround(c, m, r);
      const [nx, ny] = toScreen(shown, 0, -1);
      label(c, "N", m + nx * (r - 9), m + ny * (r - 9), COLOR.quiet, 10);
      label(c, `${shown.einstellungen.reichweite} m`, m, m + r - 16, COLOR.quiet, 10);
      if (!shown.position) {
        text.textContent = `${shown.cubes.length} Cube(s), eigene Position fehlt`;
        text.className = "cube-text";
        return;
      }
      const unit = reach / (shown.einstellungen.reichweite * 100); // Pixel je cm
      const nearest = drawCubes(c, shown, m, reach, unit);
      drawOthers(c, shown, m, reach, unit);
      c.strokeStyle = COLOR.cube;
      c.setLineDash([2, 3]);
      line(c, m, m, nearest.x, nearest.y);
      c.setLineDash([]);
      c.fillStyle = COLOR.me;
      circle(c, m, m, 5);
      c.fill();
      text.textContent = cubeText(nearest, shown.cubes.length);
      text.className = nearest.cube.oeffner ? "cube-text opening" : "cube-text";
    }

    return {
      onEvent(_, data) {
        radar = data;
        render();
      },
      onMode: render,
    };
  },
};
