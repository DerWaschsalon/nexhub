/* Zeichenhilfen und Farben, die Cube-Radar und Karte teilen. */

export const COLOR = {
  ground: "rgb(10, 16, 28)", ring: "rgb(70, 90, 120)", me: "rgb(0, 230, 118)", cube: "rgb(255, 82, 82)",
  party: "rgb(80, 170, 255)", fieldBoss: "rgb(186, 85, 255)", opening: "rgb(255, 160, 40)",
  quiet: "rgb(120, 135, 160)", findSpot: "rgba(245, 185, 65, .5)", spawnSeen: "rgb(255, 196, 0)",
  spawnManual: "rgb(200, 210, 230)",
};

export function circle(c, x, y, r) {
  c.beginPath();
  c.arc(x, y, r, 0, 2 * Math.PI);
}

export function line(c, x1, y1, x2, y2) {
  c.beginPath();
  c.moveTo(x1, y1);
  c.lineTo(x2, y2);
  c.stroke();
}

export function label(c, text, x, y, color, size) {
  c.fillStyle = color;
  c.font = `${size}px Inter, "Noto Sans", sans-serif`;
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.fillText(text, x, y);
}

/** Leinwand in doppelter Auflösung, damit sie auch vergrößert scharf bleibt; gibt den geleerten Kontext zurück. */
export function canvas2x(canvas, width, height) {
  if (canvas.width !== width * 2 || canvas.height !== height * 2) {
    canvas.width = width * 2;
    canvas.height = height * 2;
  }
  const c = canvas.getContext("2d");
  c.setTransform(2, 0, 0, 2, 0, 0);
  c.clearRect(0, 0, width, height);
  return c;
}

/** Sekunden als 1:05. */
export const minSec = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
