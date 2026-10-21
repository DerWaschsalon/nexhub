/* Modul NexHub: Hub-Adresse, Gerät koppeln (Code + Link), Stand, abkoppeln. */
import { fill, el, api, S, on, field, input, button, chip, callout, card, settingsRow, sw, saver, toast, fmtWhen, modOn, setModule } from "../core.js";

const PRIVACY = "Hochgeladene Runs enthalten die Charakternamen, Klassen und Ausrüstungswerte deiner Mitspieler und jeden einzelnen Treffer. Sie sind im Hub für alle freigeschalteten Mitglieder sichtbar. Sprich das mit deiner Gruppe ab.";

const STATUS = {
  unpaired: ["nicht gekoppelt", ""],
  pairing: ["wartet auf Bestätigung", "warn"],
  paired: ["gekoppelt", "ok"],
  offline: ["nicht erreichbar", "bad"],
};

function hubTab(ctx) {
  const box = el("div", { class: "stack" });
  const save = saver("PUT", "/api/hub", (res) => { S.hub = res; draw(); }, 500, "NexHub-Einstellungen gespeichert");
  const action = (name, okText) => async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    try { S.hub = await api("POST", `/api/hub/${name}`); if (okText) toast(okText); draw(); } catch (err) { toast(err.message, true); } finally { b.disabled = false; }
  };
  // Restzeit des Codes jede Sekunde neu zeichnen, solange gekoppelt wird
  const timer = setInterval(() => { if (S.hub?.pairing) draw(); }, 1000);
  ctx.onUnmount(() => clearInterval(timer));

  const draw = () => {
    const h = S.hub;
    if (!h) return;
    const st = h.settings;
    const [label, kind] = STATUS[h.status] || [h.status, ""];
    const p = h.pairing;
    const left = p ? Math.max(0, p.expires_at - Math.floor(Date.now() / 1000)) : 0;
    fill(box,
      el("div", { class: "cols" },
        card("Verbindung", "Wohin dieses NexBoard sich verbindet", chip(label, kind),
          el("div", { class: "grid", style: "margin-top:6px" },
            field("Adresse des Hubs", input(st.url, (v) => save({ url: v.trim() }), { spellcheck: "false", lazy: true, placeholder: "https://hub.example.com" }),
              "Ohne Domain per SSH-Tunnel: http://localhost:8080. Unverschlüsselt nur für localhost."),
            field("Name dieses Geräts", input(st.name, (v) => save({ name: v.trim() }), { lazy: true, maxlength: 64 }), "Vorschlag für den Hub, dort änderbar.")),
          h.detail ? el("p", { class: "hint small", style: `margin-top:10px;color:${h.status === "offline" ? "var(--bad)" : ""}`, text: h.detail }) : null),
        h.status === "paired" && h.account
          ? card("Gekoppelt", "Dieses NexBoard gehört zu einem Konto im Hub", chip("aktiv", "ok"),
              settingsRow("Gerät", h.account.device, null),
              settingsRow("Konto", h.account.owner, null),
              el("div", { class: "row wrap", style: "margin-top:14px" },
                button("Neu prüfen", action("check"), "sm", "refresh"),
                button("Abkoppeln", async (e) => { if (confirm("Dieses NexBoard vom Hub abkoppeln?")) await action("unpair", "Abgekoppelt")(e); }, "sm danger", "link-variant")))
          : p
            ? card("Code bestätigen", "Im Hub unter „Geräte“ eingeben", chip(`noch ${fmtLeft(left)}`, "warn"),
                el("div", { class: "pair-code", text: p.user_code, style: "font-size:34px;font-weight:600;letter-spacing:.12em;text-align:center;margin:10px 0 14px" }),
                el("div", { class: "row wrap", style: "justify-content:center" },
                  el("a", { class: "btn primary sm", href: p.uri, target: "_blank", rel: "noopener", text: "Im Hub öffnen" }),
                  button("Abbrechen", action("cancel"), "sm")),
                el("p", { class: "hint small", style: "margin-top:12px;text-align:center", text: "Der Link füllt den Code im Hub schon aus. NexBoard merkt die Bestätigung von selbst." }))
            : card("Koppeln", "Einmal mit deinem Discord-Konto im Hub verbinden", null,
                el("p", { class: "hint", text: "NexBoard holt einen Code. Du bestätigst ihn im Hub unter „Geräte“, danach ist dieses Gerät deinem Konto zugeordnet." }),
                el("div", { class: "row wrap", style: "margin-top:12px" },
                  button("Koppeln", action("pair"), "sm primary", "link-variant", { disabled: !st.url })))),
      uploadCard(h));
  };
  const uploadCard = (h) => {
    const st = h.settings;
    const last = h.last_upload;
    const toggle = (v) => {
      if (v && !confirm(`Runs hochladen?\n\n${PRIVACY}`)) { draw(); return; }
      save({ upload: v });
    };
    return card("Runs hochladen", "Nach jedem Dungeon-Run automatisch in den Hub", st.upload && h.status === "paired" ? chip("an", "ok") : chip("aus"),
      !modOn("aion2.runs") ? callout("info", "information-outline", el("span", {}, "Braucht das Modul „AION 2 · Dungeon-Runs“ (es erkennt, wann ein Run vorbei ist)."), button("Einschalten", () => setModule("aion2.runs", true).catch((e) => toast(e.message, true)), "sm primary")) : null,
      settingsRow("Hochladen", h.status === "paired" ? "Fertige Runs mit allen Treffern an den Hub schicken" : "Erst koppeln", sw(st.upload, toggle, { disabled: h.status !== "paired" && !st.upload })),
      settingsRow("Postausgang", h.outbox ? `${h.outbox} Run${h.outbox === 1 ? "" : "s"} warten auf den Hub` : "leer", null),
      el("p", { class: "hint small", style: "margin-top:10px" },
        last ? el("span", { style: `color:${last.ok ? "var(--ok)" : "var(--bad)"}` }, `${fmtWhen(last.at)} · ${last.text} `) : el("span", { class: "faint", text: "Noch nichts hochgeladen." }),
        last?.url ? el("a", { href: last.url, target: "_blank", rel: "noopener", text: "im Hub ansehen" }) : null),
      el("p", { class: "hint small", style: "margin-top:8px", text: PRIVACY }));
  };
  ctx.onUnmount(on("hub", draw));
  draw();
  if (!S.hub) api("GET", "/api/hub").then((r) => { S.hub = r; draw(); });
  return box;
}

function fmtLeft(s) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default {
  tabs: [{ id: "hub", label: "Verbindung", icon: "link-variant" }],
  status: () => ({ paired: "", pairing: "", offline: "bad" })[S.hub?.status] ?? "off",
  card() {
    const h = S.hub;
    if (!h) return el("span", { class: "faint", text: "…" });
    const [label, kind] = STATUS[h.status] || [h.status, ""];
    return el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "row wrap" }, chip(label, kind)),
      el("span", { class: "faint", text: h.account ? `${h.account.device} · ${h.account.owner}` : (h.settings.url || "Keine Hub-Adresse") }),
      h.settings.upload ? el("span", { class: "faint", text: h.outbox ? `${h.outbox} im Postausgang` : (h.last_upload?.ok ? `Zuletzt hochgeladen ${fmtWhen(h.last_upload.at)}` : "Hochladen an") }) : null);
  },
  render(tab, ctx) { return hubTab(ctx); },
};
