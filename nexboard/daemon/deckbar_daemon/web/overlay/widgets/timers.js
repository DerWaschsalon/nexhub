/* Termine: Countdown bis zu den sichtbaren Terminen des Moduls Termine (schedule.py). Gerechnet wird im
 * Daemon (Name, Beginn und „offen bis“ in Sekunden seit 1970); hier wird nur heruntergezählt. */
import { duration, el } from "../util.js";

const SOON_S = 600; // ab hier färbt sich die Zeit

function row(entry, now) {
  const open = entry.open_until !== null;
  const left = Math.max(0, (open ? entry.open_until : entry.start) - now);
  const line = el("div", open ? "open" : left < SOON_S ? "soon" : "");
  line.append(el("span", "", entry.name), el("span", "", open ? `offen · ${duration(left)}` : duration(left)));
  return line;
}

export default {
  events: ["schedule"],
  hud: true,
  defaultPos: () => [innerWidth - 300, 160],

  mount(root, ctx) {
    const list = root.appendChild(el("div", "timer-list"));
    let entries = [];

    function render() {
      if (!ctx.cfg()?.enabled) return;
      if (!entries.length) {
        list.replaceChildren(el("div", "empty", "Keine Termine – in der Web-UI unter Im Spiel → Termine."));
        return;
      }
      const now = Date.now() / 1000;
      list.replaceChildren(...entries.map((entry) => row(entry, now)));
    }

    const timer = setInterval(render, 1000);
    return {
      onEvent(_, data) {
        entries = data;
        render();
      },
      destroy: () => clearInterval(timer),
    };
  },
};
