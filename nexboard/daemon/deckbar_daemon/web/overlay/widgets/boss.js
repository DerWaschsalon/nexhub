/* Boss-Leiste: HP des Ziels aus dem Mitschnitt, Kampfdauer und Kill-Prognose aus dem HP-Verlauf. */
import { duration, el } from "../util.js";

const TTK_WINDOW_S = 40; // so weit zurück schaut die Prognose
const TTK_MIN_S = 4; // vorher ist die Rate zu wackelig
const percent = (hp) => `${hp.toFixed(1).replace(".", ",")} %`;

function build(root) {
  const part = (tag, cls, parent) => parent.appendChild(el(tag, cls));
  const head = part("div", "boss-head", root);
  const bar = part("div", "boss-bar", root);
  const foot = part("div", "boss-foot", root);
  return {
    name: part("span", "boss-name", head), pct: part("span", "boss-pct", head),
    fill: part("div", "boss-fill", bar), glow: part("div", "boss-glow", bar),
    time: part("span", "", foot), ttk: part("span", "", foot),
  };
}

/** Zeile wie „Kampf 1:05“: Wort normal, Wert fett. */
function labelled(node, label, value) {
  node.replaceChildren(...(value ? [`${label} `, el("b", "", value)] : []));
}

export default {
  events: ["dps"],
  hud: true,
  defaultPos: () => [innerWidth / 2 - 210, 72],

  mount(root, ctx) {
    const ui = build(root);
    let dps = { dps: null, dps_active: false };
    let samples = []; // [Zeit, HP] des aktuellen Ziels
    let target = null;

    function remember(d) {
      if (target !== d.target) {
        target = d.target;
        samples = [];
      }
      const now = performance.now() / 1000;
      samples.push([now, d.hp]);
      while (samples.length > 2 && now - samples[0][0] > TTK_WINDOW_S) samples.shift();
    }

    function killIn(hp) {
      if (!ctx.cfg().options.show_ttk || samples.length < 2) return "";
      const [t0, h0] = samples[0];
      const [t1, h1] = samples[samples.length - 1];
      const rate = (h0 - h1) / Math.max(0.001, t1 - t0);
      return t1 - t0 >= TTK_MIN_S && rate > 0 && hp > 0 ? duration(hp / rate) : "";
    }

    function render() {
      const d = dps.dps;
      const has = !!(d && d.target && d.hp != null);
      const editing = ctx.mode() === "edit";
      ctx.setIdle(ctx.cfg().options.hide_idle && !(has && dps.dps_active) && !editing);
      const hp = has ? Math.max(0, Math.min(100, d.hp)) : 100;
      ui.name.textContent = has ? d.target : editing ? "Boss-Leiste" : "Kein Ziel";
      ui.pct.textContent = has ? percent(hp) : "";
      ui.fill.style.transform = `scaleX(${hp / 100})`;
      ui.glow.style.transform = `translateX(${hp - 100}%)`;
      labelled(ui.time, "Kampf", has && d.time ? duration(d.time) : "");
      labelled(ui.ttk, "Kill in", has ? killIn(hp) : "");
    }

    return {
      onEvent(_, data) {
        dps = data;
        const d = dps.dps;
        if (d && d.target && d.hp != null) remember(d);
        render();
      },
      onLayout: render,
      onMode: render,
    };
  },
};
