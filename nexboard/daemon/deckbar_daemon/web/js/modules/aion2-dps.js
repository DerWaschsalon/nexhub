/* Modul AION 2 · DPS-Mitschnitt: Live-Ansicht und Einstellungen (Quelle, Sprache, Seitenwechsel). */
import { fill, el, icon, S, on, chip, callout, card, fmtAmount, fmtTime, classColor, modOn } from "../core.js";
import { moduleSettings } from "../form.js";

const DOT = { connected: "ok", capturing: "ok", bad_key: "bad", no_caps: "bad", no_capture: "bad", off: "" };

function statusChip(d) {
  if (!d) return chip("…");
  const cap = d.capture || {};
  const text = d.status_text + (d.status === "connected" && d.port ? ` (Port ${d.port})` : "") + (d.status === "capturing" && cap.ping ? ` · Ping ${cap.ping} ms` : "");
  return chip(text, DOT[d.status] ?? "warn");
}

function hintFor(d) {
  const st = d.settings;
  const cap = d.capture || {};
  const hasTile = S.layout?.pages?.some((p) => p.items.some((i) => i.type === "dps"));
  return {
    overlay_off: "Im A2Tools-Meter unter Einstellungen das Stream-Overlay einschalten. Port und Schlüssel liest die NexBoard dann selbst.",
    no_meter: st.source === "auto" && !d.a2tools.installed ? "Das A2Tools DPS Meter ist nicht installiert (oder hat noch keine Einstellungen gespeichert)." : "Das A2Tools DPS Meter starten. Die NexBoard verbindet sich dann von selbst.",
    bad_key: st.source === "manual" ? "Der Schlüssel passt nicht. Er steht in der Overlay-URL des Meters hinter key=." : "Der Schlüssel wurde abgelehnt. Wurde er im Meter gerade neu erzeugt? Die NexBoard versucht es gleich erneut.",
    no_game: "Startet von selbst, sobald AION 2 läuft, und endet mit dem Spiel.",
    no_capture: "Einmal bauen und installieren: capture/build.sh --install im Repo (braucht cargo, fragt nach sudo für die Mitschnitt-Rechte).",
    no_caps: `Mitschneiden braucht cap_net_raw: capture/build.sh --install (legt es nach ~/.local/bin) oder sudo setcap cap_net_raw=ep ${cap.binary || "deckbar-capture"}. Ein Neubau verliert die Rechte.`,
    capturing: hasTile === false && modOn("deck") ? "Für die Anzeige auf der Leiste eine Kachel „AION 2 DPS-Meter“ im Editor der Touch-Leiste hinzufügen." : "",
  }[d.status] || "";
}

function meter(d, n = 8) {
  const rows = (d?.rows || []).slice(0, n);
  const best = Math.max(1, ...rows.map((r) => r.dps));
  return el("div", { class: "minibars" }, rows.map((r, i) => el("div", { style: r.you ? "outline:1px solid var(--accent)" : "" },
    el("i", { style: `width:${Math.max(4, (100 * r.dps) / best)}%;background:${classColor(r.cls)}` }),
    el("span", { text: `${i + 1}  ${r.name}` }), el("span", { text: `${fmtAmount(r.dps)}/s · ${Math.round(r.pct || 0)} %` }))));
}

function liveTab(ctx) {
  const box = el("div", { class: "stack" });
  const draw = () => {
    const d = S.dps;
    const v = S.state.dps;
    const cap = d?.capture || {};
    const hint = d ? hintFor(d) : "";
    const facts = [
      ["Status", d?.status_text || "…"],
      ["Programm", cap.binary || "nicht gefunden"],
      ["Version", cap.version ? `${cap.version}${cap.parser ? ` · Parser ${cap.parser}` : ""}` : "–"],
      ["Rechte (cap_net_raw)", cap.cap_net_raw == null ? "–" : cap.cap_net_raw ? "ja" : "fehlen"],
      ["Spielserver-Port", cap.port || "–"],
      ["Ping", cap.ping ? `${cap.ping} ms` : "–"],
      ["Kampf-History", cap.history_dir || "–"],
    ];
    const table = el("table", { class: "list" }, el("tbody", {}, facts.map(([k, val]) =>
      el("tr", {}, el("td", { class: "faint", text: k }), el("td", { class: "mono", style: "word-break:break-all", text: String(val) })))));
    fill(box,
      d?.detail || hint ? callout(DOT[d.status] === "bad" ? "bad" : "info", "information-outline", el("span", { text: (d.detail ? `(${d.detail}) ` : "") + hint })) : null,
      el("div", { class: "cols" },
        card("Kampf", v?.target ? `${v.target}${v.hp != null ? ` · ${v.hp.toFixed(1).replace(".", ",")} % HP` : ""}` : "kein Ziel", statusChip(d),
          v?.rows?.length
            ? el("div", { class: "stack", style: "gap:12px" },
              el("div", { class: "row wrap" }, el("div", { class: "metric" }, el("b", { text: fmtTime(v.time) }), el("span", { text: "Kampfzeit" })),
                S.state.dps_active ? chip("im Kampf", "ok") : chip("Kampf vorbei")),
              meter(v))
            : el("div", { class: "empty" }, icon("sword-cross"), d?.status === "capturing" ? "Warte auf Kampfdaten …" : "Noch keine Daten.")),
        card("Mitschnitt", d?.settings?.source === "capture" ? "deckbar-capture" : "A2Tools-Meter (Stream-Overlay)", null, table)));
  };
  for (const t of ["dps", "state"]) ctx.onUnmount(on(t, draw));
  draw();
  return box;
}

function settingsTab(ctx) {
  return el("div", { class: "stack" },
    moduleSettings(ctx, "aion2.dps", "Kampfdaten", null),
    callout("info", "shield-check", el("span", {}, "Der Mitschnitt ist rein passiv: Er liest nur Netzwerkpakete mit (libpcap, Recht cap_net_raw), verändert nichts am Spiel und lädt nichts hoch.")));
}

export default {
  tabs: [
    { id: "live", label: "Live", icon: "chart-bar" },
    { id: "settings", label: "Einstellungen", icon: "tune-variant" },
  ],
  status: () => (S.dps ? ({ connected: "", capturing: "", no_game: "off", off: "off" }[S.dps.status] ?? "warn") : null),
  card() {
    const v = S.state.dps;
    return el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "row wrap" }, statusChip(S.dps), S.state.dps_active ? chip("im Kampf", "ok") : null),
      v?.rows?.length ? meter(v, 3) : el("span", { class: "faint", text: v?.target ? v.target : "Startet mit AION 2." }));
  },
  render(tab, ctx) {
    return tab === "settings" ? settingsTab(ctx) : liveTab(ctx);
  },
};
