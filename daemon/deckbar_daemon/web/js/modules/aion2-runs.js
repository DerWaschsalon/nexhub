/* Modul AION 2 · Dungeon-Runs: Discord-Webhook, Vorschau, Namen der Mitspieler. */
import { fill, el, icon, api, S, on, field, input, button, chip, callout, card, settingsRow, sw, saver, toast, clampInt, fmtWhen, CLASS_LABELS } from "../core.js";

// So maskiert das A2Tools-Meter (wie mask() in runs.py)
function maskName(n) {
  if (n.includes("*") || n.length < 2) return n;
  if (n.length === 2) return n[0] + "*";
  const head = n.length === 3 ? 1 : 2;
  return n.slice(0, head) + "*".repeat(Math.min(4, n.length - head - 1)) + n.slice(-1);
}

function stateChip(r) {
  if (!r) return chip("…");
  const st = r.settings;
  if (!r.history) return chip("keine History", "warn");
  if (r.open_run) return chip("Run läuft", "info");
  return st.enabled && st.webhook ? chip("bereit", "ok") : chip("Posten aus");
}

function runsTab(ctx) {
  const box = el("div", { class: "stack" });
  const save = saver("PUT", "/api/runs", (res) => { S.runs = res; draw(); }, 300, "Discord-Einstellungen gespeichert");
  const patch = (p) => { Object.assign(S.runs.settings, p); save({ ...S.runs.settings }); };
  const draw = () => {
    const r = S.runs;
    if (!r) return;
    const st = r.settings;
    let img = null;
    fill(box,
      !r.history ? callout("warn", "alert", "Noch keine Kampf-History gefunden. Sie entsteht beim ersten Bosskampf mit laufendem Mitschnitt.") : null,
      el("div", { class: "cols" },
        card("Discord", "Nach jedem Run ein Bild mit dem Schaden pro Boss", stateChip(r),
          settingsRow("Bild posten", "Per Webhook in einen Kanal", sw(st.enabled, (v) => patch({ enabled: v }))),
          el("div", { class: "grid", style: "margin-top:6px" },
            field("Discord-Webhook", input(st.webhook, (v) => patch({ webhook: v.trim() }), { type: "password", autocomplete: "off", spellcheck: "false", lazy: true, placeholder: "https://discord.com/api/webhooks/…" }), "Kanal bearbeiten → Integrationen → Webhooks"),
            field("Run vorbei nach (min ohne Boss)", input(st.idle_minutes, (v) => patch({ idle_minutes: clampInt(v, 2, 120, 15) }), { type: "number", min: 2, max: 120 }))),
          r.result ? el("p", { class: "hint small", style: "margin-top:12px", text: r.result }) : null),
        card("Letzter Run", r.last_run ? `${r.last_run.name} · ${fmtWhen(r.last_run.end)} · ${r.last_run.kills} Boss(e)` : "noch keiner seit dem Start", null,
          el("div", { class: "row wrap" },
            button("Vorschau", () => { img.src = `/api/runs/preview.png?t=${Date.now()}`; img.hidden = false; }, "", "image"),
            button("Jetzt posten", async (e) => {
              const b = e.currentTarget; // nach dem await ist currentTarget null
              b.disabled = true;
              try { S.runs = await api("POST", "/api/runs/test"); toast("An Discord geschickt"); draw(); } catch (err) { toast(err.message, true); } finally { b.disabled = false; }
            }, "", "send")),
          (img = el("img", { class: "preview-img", hidden: true, alt: "Vorschau des letzten Runs", style: "margin-top:14px", onerror: () => { img.hidden = true; toast("Noch kein Dungeon-Run in der History", true); } })))),
      card("Namen der Mitspieler", "Das Meter speichert fremde Namen maskiert", null,
        el("p", { class: "hint small", style: "margin-bottom:14px", text: "Echte Namen lernt die NexBoard während des Kampfs aus der Live-Anzeige (grau vorausgefüllt). Eintragen musst du nur, was falsch oder leer ist." }),
        namesGrid(r, patch)),
      callout("info", "shield-check", "Die Bilder zeigen Charakternamen deiner Mitspieler. Poste sie nur in Kanäle, in denen das für alle in Ordnung ist."));
  };
  ctx.onUnmount(on("runs", draw));
  draw();
  return box;
}

function namesGrid(r, patch) {
  const grid = el("div", { class: "names" });
  for (const c of r.characters) {
    const inp = el("input", { type: "text", value: c.name, placeholder: c.seen || (c.you ? "dein Charakter" : "echter Name"), maxlength: 24, spellcheck: "false", title: "Muss zur Maske passen: gleicher Anfang und gleiches Ende" });
    const check = () => inp.classList.toggle("bad", !!inp.value.trim() && maskName(inp.value.trim()) !== c.mask);
    check();
    inp.addEventListener("input", check);
    inp.addEventListener("change", () => {
      const names = { ...S.runs.settings.names };
      const v = inp.value.trim();
      if (v) names[c.key] = v; else delete names[c.key];
      patch({ names });
    });
    grid.append(el("span", { class: "m", text: c.mask }), el("span", { class: "c", text: `${CLASS_LABELS[c.cls] || "?"} · ${c.count}×` }), inp);
  }
  if (!r.characters.length) return el("div", { class: "empty" }, icon("account-group"), "Noch keine Dungeon-Kämpfe in der History.");
  return grid;
}

export default {
  tabs: [{ id: "runs", label: "Runs", icon: "trophy" }],
  status: () => (S.runs?.settings?.enabled && S.runs.settings.webhook ? "" : "off"),
  card() {
    const r = S.runs;
    return el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "row wrap" }, stateChip(r)),
      r?.last_run ? el("span", {}, el("b", { text: r.last_run.name }), el("span", { class: "faint", text: ` · ${fmtWhen(r.last_run.end)}` })) : el("span", { class: "faint", text: "Noch kein Run seit dem Start." }));
  },
  render(tab, ctx) { return runsTab(ctx); },
};
