/* Bearbeiten-Modus: Widgets ziehen (rastet ein), mit dem Mausrad skalieren, am Griff die Größe ändern,
 * in der Leiste ein- und ausschalten und das Profil wählen. */
import * as host from "./host.js";
import * as layout from "./layout.js";
import * as stage from "./stage.js";
import { $, el, rectOf } from "./util.js";

const GRID = 8;
const SNAP = 8;
const MIN_SIZE = [220, 160];

/* ================================================================ Einrasten */
function hideGuides() {
  document.querySelectorAll("#guides div").forEach((g) => (g.style.display = "none"));
}

function guide(cls, p) {
  const g = document.querySelector(`#guides .${cls}`);
  g.style.display = "block";
  if (cls === "gv") g.style.left = `${p}px`; else g.style.top = `${p}px`;
}

/** Einrasten an Bildschirmkanten, Bildschirmmitte, Kanten und Mitten der anderen Widgets. */
function snap(w, x, y, width, height) {
  const xs = [0, innerWidth / 2, innerWidth];
  const ys = [0, innerHeight / 2, innerHeight];
  for (const other of stage.all()) {
    if (other === w || other.el.hidden) continue;
    const r = other.el.getBoundingClientRect();
    xs.push(r.left, r.left + r.width / 2, r.right);
    ys.push(r.top, r.top + r.height / 2, r.bottom);
  }
  const fit = (p, size, lines) => {
    for (const edge of [0, size / 2, size]) {
      for (const l of lines) if (Math.abs(p + edge - l) <= SNAP) return [l - edge, l];
    }
    return null;
  };
  const fx = fit(x, width, xs);
  const fy = fit(y, height, ys);
  hideGuides();
  if (fx) guide("gv", fx[1]);
  if (fy) guide("gh", fy[1]);
  return [fx ? fx[0] : Math.round(x / GRID) * GRID, fy ? fy[0] : Math.round(y / GRID) * GRID];
}

/* ================================================================ Ziehen, Skalieren, Größe */
/** Solange die Maustaste gehalten wird: move(ev) je Bewegung, danach speichern. */
function track(target, e, move) {
  target.setPointerCapture(e.pointerId);
  layout.hold();
  const done = () => {
    target.removeEventListener("pointermove", move);
    hideGuides();
    layout.release();
    stage.regionsSoon();
    layout.saveSoon();
  };
  target.addEventListener("pointermove", move);
  target.addEventListener("pointerup", done, { once: true });
  target.addEventListener("pointercancel", done, { once: true });
}

function startDrag(w, e) {
  if (stage.getMode() !== "edit" || e.button !== 0) return;
  e.preventDefault();
  const c = stage.pin(w);
  const r = w.el.getBoundingClientRect();
  const offset = [e.clientX - c.x, e.clientY - c.y];
  w.el.classList.add("dragging");
  w.el.addEventListener("pointerup", () => w.el.classList.remove("dragging"), { once: true });
  w.el.addEventListener("pointercancel", () => w.el.classList.remove("dragging"), { once: true });
  track(w.el, e, (ev) => {
    let x = ev.clientX - offset[0];
    let y = ev.clientY - offset[1];
    if (ev.shiftKey) hideGuides(); else [x, y] = snap(w, x, y, r.width, r.height);
    c.x = Math.round(x);
    c.y = Math.round(y);
    stage.place(w);
  });
}

function scaleByWheel(w, e) {
  if (stage.getMode() !== "edit") return;
  e.preventDefault();
  const c = layout.cfg(w.id);
  const next = (c.scale || 1) - Math.sign(e.deltaY) * 0.05;
  c.scale = Math.min(3, Math.max(0.5, Math.round(next * 100) / 100));
  stage.place(w);
  stage.regionsSoon();
  layout.saveSoon();
}

/** Griff unten rechts: Breite und Höhe frei ziehen (das Mausrad skaliert dagegen alles darin). */
function addGrip(w) {
  const grip = el("div", "grip");
  grip.title = "Größe ändern";
  grip.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation(); // sonst zieht startDrag das ganze Widget
    const c = layout.cfg(w.id);
    const s = c.scale || 1;
    const start = { x: e.clientX, y: e.clientY, width: c.width, height: c.height };
    track(grip, e, (ev) => {
      c.width = Math.round(Math.max(MIN_SIZE[0], Math.min(innerWidth / s, start.width + (ev.clientX - start.x) / s)));
      c.height = Math.round(Math.max(MIN_SIZE[1], Math.min(innerHeight / s, start.height + (ev.clientY - start.y) / s)));
      stage.place(w);
      w.instance.onLayout?.();
    });
  });
  w.el.append(grip);
}

function makeEditable(w) {
  w.el.addEventListener("pointerdown", (e) => startDrag(w, e));
  w.el.addEventListener("wheel", (e) => scaleByWheel(w, e), { passive: false });
  if (w.spec.resizable) addGrip(w);
}

/* ================================================================ Leiste */
function buildToggles() {
  const boxes = stage.all().map((w) => {
    const label = el("label");
    const box = el("input");
    box.type = "checkbox";
    box.dataset.id = w.id;
    box.addEventListener("change", () => {
      layout.cfg(w.id).enabled = box.checked;
      stage.place(w);
      stage.regionsSoon();
      layout.saveSoon();
    });
    label.append(box, w.spec.title);
    return label;
  });
  $("toggles").replaceChildren(...boxes);
  syncToolbar();
}

function syncToolbar() {
  const current = layout.current();
  if (!current) return;
  for (const box of $("toggles").querySelectorAll("input")) box.checked = !!layout.cfg(box.dataset.id)?.enabled;
  const names = ["", ...Object.keys(current.profiles)];
  $("profile").replaceChildren(...names.map((name) => new Option(name || "–", name)));
  $("profile").value = current.profile;
}

function resetPositions() {
  for (const w of stage.all()) Object.assign(layout.cfg(w.id), { x: null, y: null, scale: 1 });
  stage.placeAll();
  layout.saveSoon();
}

export function start() {
  stage.onMount(makeEditable);
  stage.onSync(buildToggles);
  layout.onChange(syncToolbar);
  $("profile").addEventListener("change", () => layout.chooseProfile($("profile").value));
  $("done").addEventListener("click", host.finishEdit);
  $("reset").addEventListener("click", resetPositions);
  $("edit-button").addEventListener("click", () => host.requestMode("edit"));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && stage.getMode() === "edit") host.finishEdit();
  });
  // Bearbeiten-Knopf unten rechts: in jedem Modus anklickbar
  stage.addRegions((mode) => {
    const rect = mode === "edit" ? [] : [rectOf($("edit-button"))];
    return { click: rect, lock: rect };
  });
}
