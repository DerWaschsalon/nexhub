/* Modul PoE 1 · Spiel: läuft das Spiel, und welches Client.txt wird gelesen. */
import { el, api, S, mod, on, fill, chip, card } from "../core.js";
import { moduleSettings } from "../form.js";

const REFRESH_MS = 5000;

function statusCard() {
  const box = el("div");
  const draw = () => {
    const st = mod("poe1.client")?.status || {};
    fill(box, card("Path of Exile", "Zonen und Aufstiege kommen aus Client.txt", st.running ? chip("läuft", "ok") : chip("nicht gestartet"),
      el("table", { class: "list" }, el("tbody", {},
        el("tr", {}, el("td", { class: "faint", text: "Client.txt" }),
          el("td", {}, st.client_txt ? el("code", { text: st.client_txt }) : "nicht gefunden", st.client_txt && !st.found ? chip("fehlt", "bad") : null)),
        el("tr", {}, el("td", { class: "faint", text: "Letzte Zone" }), el("td", { text: st.zone || "–" }))))));
  };
  draw();
  return { box, draw };
}

function clientPage(ctx) {
  const status = statusCard();
  ctx.onUnmount(on("modules", status.draw));
  // der Kurzstand kommt nur mit der Modulliste; solange die Seite offen ist, regelmäßig nachfragen
  const timer = setInterval(() => api("GET", "/api/modules").then((res) => { S.modules = res; status.draw(); }).catch(() => {}), REFRESH_MS);
  ctx.onUnmount(() => clearInterval(timer));
  return el("div", { class: "stack" }, status.box,
    moduleSettings(ctx, "poe1.client", "Einstellungen", "Meist leer lassen: der Ordner des laufenden Spiels wird erkannt"));
}

export default {
  status: () => (mod("poe1.client")?.status?.running ? "ok" : ""),
  card() {
    return el("span", { class: "faint", text: mod("poe1.client")?.status?.text || "" });
  },
  pages: [{ id: "poe1.client", name: "Path of Exile", render: (tab, ctx) => clientPage(ctx) }],
};
