/* Boss-Warnungen des Moduls AION 2 · Radar: nur sichtbar, solange eine läuft oder eine Vorhersage
 * ansteht. Die Daten kommen etwa fünfmal pro Sekunde mit dem Ereignis „radar“. */
import { el } from "../util.js";

const BLINK_PER_S = 6;
const EXAMPLE = { titel: "Boss-Warnungen", hinweis: "erscheinen hier im Kampf", rest: 3, vorlauf: 4,
  farbe: [106, 166, 255], lernhilfe: false };

function warningBox(w, nowText) {
  const box = el("div", "warn");
  box.style.setProperty("--farbe", `rgb(${w.farbe.join(", ")})`);
  if (w.rest <= 0 && Math.floor((Date.now() / 1000) * BLINK_PER_S) % 2) box.classList.add("blinkt");
  // Lernhilfe: der echte Vorlauf ist unbekannt, also keine Sekunden
  const time = w.lernhilfe ? "" : w.rest > 0 ? w.rest.toFixed(1) : nowText;
  const head = el("div", "warn-kopf");
  head.append(el("span", "warn-titel", w.titel), el("span", "warn-zeit", time));
  const bar = el("div", "warn-balken");
  bar.appendChild(el("div")).style.transform = `scaleX(${Math.max(0, w.rest / w.vorlauf)})`;
  box.append(head, el("div", "warn-hinweis", w.hinweis), bar);
  return box;
}

function previewText(preview) {
  return preview.map(([text, rest]) => (rest <= 0 ? text : `${text} in ${Math.round(rest)} s`)).join("  ·  ");
}

export default {
  events: ["radar"],
  defaultPos: () => [innerWidth / 2 - 230, 140],

  mount(root, ctx) {
    const head = root.appendChild(el("div", "warn-vorschau"));
    const list = root.appendChild(el("div"));
    let radar = { aktiv: false };

    function render() {
      const warnings = radar.aktiv ? radar.warnungen : [];
      const preview = radar.aktiv ? radar.vorschau : [];
      const editing = ctx.mode() === "edit";
      ctx.setIdle(!warnings.length && !preview.length && !editing);
      head.hidden = !preview.length;
      head.textContent = previewText(preview);
      head.classList.toggle("offen", preview.some(([, rest]) => rest <= 0)); // Regen jederzeit möglich
      const shown = warnings.length ? warnings : editing ? [EXAMPLE] : [];
      list.replaceChildren(...shown.map((w) => warningBox(w, radar.jetzt_text)));
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
