/* Modul AION 2 · DPS-Mitschnitt: Live-Ansicht und Einstellungen (Quelle, Sprache, Seitenwechsel). */
import { fill, el, icon, api, S, on, field, input, select, chip, callout, card, settingsRow, saver, fmtAmount, fmtTime, CLASS_COLORS, CLASS_LABELS, clampInt, modOn } from "../core.js";

const DOT = { connected: "ok", capturing: "ok", bad_key: "bad", no_caps: "bad", no_capture: "bad", off: "" };
const LANGS = { de: "Deutsch", en: "English", fr: "Français", es: "Español", pt: "Português", ru: "Русский", ja: "日本語", ko: "한국어", "zh-Hans": "简体中文", "zh-Hant": "繁體中文" };

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
    overlay_off: "Im A2Tools-Meter unter Einstellungen das Stream-Overlay einschalten. Port und Schlüssel liest die DeckBar dann selbst.",
    no_meter: st.source === "auto" && !d.a2tools.installed ? "Das A2Tools DPS Meter ist nicht installiert (oder hat noch keine Einstellungen gespeichert)." : "Das A2Tools DPS Meter starten. Die DeckBar verbindet sich dann von selbst.",
    bad_key: st.source === "manual" ? "Der Schlüssel passt nicht. Er steht in der Overlay-URL des Meters hinter key=." : "Der Schlüssel wurde abgelehnt. Wurde er im Meter gerade neu erzeugt? Die DeckBar versucht es gleich erneut.",
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
    el("i", { style: `width:${Math.max(4, (100 * r.dps) / best)}%;background:${CLASS_COLORS[r.cls] || "#8E8E93"}` }),
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
  const box = el("div", { class: "stack" });
  const save = saver("PUT", "/api/dps", (res) => { S.dps = res; draw(); }, 400, "DPS-Einstellungen gespeichert");
  const patch = (p) => { Object.assign(S.dps.settings, p); save({ ...S.dps.settings }); };
  const draw = () => {
    const d = S.dps;
    if (!d) return;
    const st = d.settings;
    const pages = { "": "— nicht wechseln —", ...Object.fromEntries((S.layout?.pages || []).map((p) => [p.id, p.name || p.id])) };
    fill(box,
      el("div", { class: "cols" },
        card("Quelle", "Woher die Kampfdaten kommen", statusChip(d),
          el("div", { class: "grid" },
            field("Quelle", select({ capture: "Eigener Mitschnitt (deckbar-capture)", auto: "A2Tools-Meter, Stream-Overlay (automatisch)", manual: "A2Tools-Meter, Port und Schlüssel von Hand" }, st.source, (v) => { patch({ source: v }); draw(); })),
            st.source === "capture" ? field("Sprache für Boss- und Skillnamen", select(LANGS, st.lang, (v) => patch({ lang: v }))) : null,
            st.source === "capture" ? field("Programmpfad", input(st.capture_bin, (v) => patch({ capture_bin: v.trim() }), { placeholder: "leer = ~/.local/bin bzw. Build im Repo", lazy: true, spellcheck: "false" })) : null,
            st.source === "manual" ? el("div", { class: "grid g2" },
              field("Port", input(st.port, (v) => patch({ port: clampInt(v, 1024, 65535, 18731) }), { type: "number", min: 1024, max: 65535 })),
              field("Schlüssel", input(st.key, (v) => patch({ key: v.trim() }), { type: "password", autocomplete: "off", lazy: true, placeholder: "key=… aus der Overlay-URL" }))) : null)),
        card("Touch-Leiste", "Automatischer Seitenwechsel im Kampf", null,
          modOn("deck") ? el("div", { class: "grid g2" },
            field("Bei Kampfbeginn zeigen", select(pages, st.auto_page || "", (v) => { patch({ auto_page: v || null }); draw(); })),
            field("Zurück nach (s, 0 = nie)", input(st.return_after, (v) => patch({ return_after: clampInt(v, 0, 600, 20) }), { type: "number", min: 0, max: 600, disabled: !st.auto_page })))
            : el("p", { class: "hint", text: "Das Modul Touch-Leiste ist aus." }))),
      callout("info", "shield-check", el("span", {}, "Der Mitschnitt ist rein passiv: Er liest nur Netzwerkpakete mit (libpcap, Recht cap_net_raw), verändert nichts am Spiel und lädt nichts hoch.")));
  };
  ctx.onUnmount(on("dps", draw));
  draw();
  if (!S.layout) api("GET", "/api/layout").then((r) => { S.layout = r.layout; draw(); });
  return box;
}

on("layout", ({ layout }) => { if (layout) S.layout = layout; });

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
