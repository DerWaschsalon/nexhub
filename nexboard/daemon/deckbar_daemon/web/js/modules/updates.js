/* Modul Updates: Stand von Repo und A2Tools-Kern, Prüfen, Installieren. */
import { fill, el, icon, api, S, on, button, chip, callout, card, toast, fmtWhen } from "../core.js";

function summary(u) {
  const parts = [];
  if (u?.deckbar?.behind) parts.push(`NexBoard: ${u.deckbar.behind} neue${u.deckbar.behind === 1 ? "r" : ""} Commit${u.deckbar.behind === 1 ? "" : "s"}`);
  if (u?.a2tools?.newer) parts.push(`A2Tools ${u.a2tools.latest} (bisher ${u.a2tools.current})`);
  return parts.join(" · ");
}

function updatesTab(ctx) {
  const box = el("div", { class: "stack" });
  const draw = () => {
    const u = S.updates;
    if (!u) return;
    const d = u.deckbar || {};
    const a = u.a2tools || {};
    fill(box,
      u.available ? callout("info", "update", el("span", { text: `Update verfügbar: ${summary(u)}` }),
        button(u.running ? "Läuft …" : "Jetzt aktualisieren", async () => {
          try { await api("POST", "/api/updates/run"); toast("Update läuft im Konsole-Fenster"); } catch (e) { toast(e.message, true); }
        }, "primary sm", "download", { disabled: !!u.running })) : null,
      u.error ? callout("warn", "alert", u.error) : null,
      el("div", { class: "cols" },
        card("NexBoard", d.upstream ? `Zweig ${d.upstream}` : d.branch ? `lokaler Zweig ${d.branch} (ohne Upstream)` : "Git-Repository", d.behind ? chip(`${d.behind} neu`, "info") : chip("aktuell", "ok"),
          el("table", { class: "list" }, el("tbody", {},
            el("tr", {}, el("td", { class: "faint", text: "Neueste Änderung" }), el("td", { text: d.latest || "–" })),
            el("tr", {}, el("td", { class: "faint", text: "Lokal voraus" }), el("td", { text: String(d.ahead ?? "–") }))))),
        card("A2Tools-Kern", "Mitschnitt und Meter-Oberfläche (Submodul)", a.newer ? chip(`${a.latest} verfügbar`, "info") : chip(a.current || "…", "ok"),
          el("table", { class: "list" }, el("tbody", {},
            el("tr", {}, el("td", { class: "faint", text: "Installiert" }), el("td", { text: a.current || "–" })),
            el("tr", {}, el("td", { class: "faint", text: "Neuestes Release" }), el("td", {}, a.url ? el("a", { href: a.url, target: "_blank", rel: "noopener", text: a.latest }) : a.latest || "–")))))),
      el("div", { class: "row wrap" },
        button("Jetzt prüfen", async (e) => {
          const b = e.currentTarget;
          b.disabled = true;
          try { S.updates = await api("POST", "/api/updates/check"); draw(); toast(S.updates.available ? "Update gefunden" : "Alles aktuell"); } catch (err) { toast(err.message, true); } finally { b.disabled = false; }
        }, "", "refresh"),
        el("span", { class: "hint small", text: u.checked_at ? `Zuletzt geprüft: ${fmtWhen(u.checked_at)} · danach täglich` : "Erste Prüfung kurz nach dem Start, danach täglich." })));
  };
  ctx.onUnmount(on("updates", draw));
  draw();
  if (!S.updates) api("GET", "/api/updates").then((r) => { S.updates = r; draw(); });
  return box;
}

export default {
  tabs: [{ id: "updates", label: "Updates", icon: "update" }],
  status: () => (S.updates?.available ? "warn" : ""),
  card() {
    const u = S.updates;
    return el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "row wrap" }, u?.available ? chip("Update verfügbar", "info") : chip("aktuell", "ok")),
      el("span", { class: "faint", text: u?.available ? summary(u) : u?.checked_at ? `Geprüft ${fmtWhen(u.checked_at)}` : "Noch nicht geprüft." }));
  },
  render(tab, ctx) { return updatesTab(ctx); },
};
