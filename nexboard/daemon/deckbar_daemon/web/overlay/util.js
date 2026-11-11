/* Kleine Helfer, die mehrere Teile der Overlay-Seite brauchen. */

export const $ = (id) => document.getElementById(id);

/** Element mit Klasse und Text, z. B. el("span", "name", "Boss"). */
export function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}

/** Rechteck eines Elements auf der Seite als [x, y, Breite, Höhe] in ganzen Pixeln. */
export function rectOf(node) {
  const r = node.getBoundingClientRect();
  return [Math.floor(r.left), Math.floor(r.top), Math.ceil(r.width), Math.ceil(r.height)];
}

/** Dauer in Sekunden als 1:05, 2:01:05 oder „3 T 4 h“. */
export function duration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const two = (n) => String(n).padStart(2, "0");
  if (h >= 24) return `${Math.floor(h / 24)} T ${h % 24} h`;
  return h ? `${h}:${two(m)}:${two(s % 60)}` : `${m}:${two(s % 60)}`;
}
