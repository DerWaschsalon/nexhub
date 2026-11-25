/* Ersteinrichtung (System → Einrichtung): in drei Schritten einschalten, was man braucht. Vorlagen und
   Voraussetzungen kommen vom Daemon (setup.py); hier wird nur gewählt und übernommen. */
import { fill, el, api, S, emit, mod, button, chip, callout, card, icon, settingsRow, sw, toast } from "./core.js";

// Wohin es nach dem Übernehmen weitergeht, je Vorlage
const NEXT = {
  bar: { page: "deck", label: "Leiste einrichten", icon: "tablet" },
  pve: { page: "aion2.overlay", label: "Widgets anordnen", icon: "cursor-move" },
  pvp: { page: "aion2.overlay", label: "Widgets anordnen", icon: "cursor-move" },
  radar: { page: "aion2.overlay", label: "Widgets anordnen", icon: "cursor-move" },
};

async function reloadModules() {
  S.modules = await api("GET", "/api/modules");
  emit("modules", S.modules);
}

function templateTile(t, chosen, toggle) {
  return el("div", { class: "tile glass" },
    el("div", { class: "tile-head" },
      el("div", { class: "mod-icon" }, icon(t.icon)),
      el("div", { class: "t" }, el("b", { text: t.name }), el("small", { text: t.active ? "schon eingerichtet" : `${t.modules.length} Module` })),
      sw(chosen.has(t.id), (on) => toggle(t.id, on), { title: t.name })),
    el("div", { class: "body" }, el("span", { text: t.summary })));
}

function requirementsCard(info, chosen) {
  const needed = info.requirements.filter((r) => r.templates.some((id) => chosen.has(id)));
  const missing = needed.filter((r) => !r.ok).length;
  const sub = !needed.length ? "Wähle oben mindestens eine Vorlage"
    : missing ? `${missing} fehl${missing === 1 ? "t" : "en"} noch; einschalten kannst du trotzdem` : "Alles da";
  return card("2 · Voraussetzungen", sub, null,
    needed.map((r) => settingsRow(r.name, r.ok ? null : r.hint, r.ok ? chip("vorhanden", "ok") : chip("fehlt", "warn"))));
}

function resultCallout(changed, chosen, go) {
  const names = changed.map((id) => mod(id)?.name || id);
  const pages = new Map([...chosen].map((id) => [NEXT[id].page, NEXT[id]]));
  return callout("ok", "check-circle", names.length ? `Eingeschaltet: ${names.join(", ")}` : "Alles war schon eingeschaltet.",
    ...[...pages.values()].map((next) => button(next.label, () => go(next.page), "sm", next.icon)));
}

/** go(Seite): Navigation der Web-UI (main.js). */
export function setupPage(ctx, go) {
  const box = el("div", { class: "stack" });
  const chosen = new Set();
  let info = null, changed = null;
  const draw = () => {
    if (!info) return;
    const toggle = (id, on) => { if (on) chosen.add(id); else chosen.delete(id); changed = null; draw(); };
    fill(box,
      card("1 · Was soll die NexBoard für dich tun?", "Mehrere sind möglich. Ausgeschaltet wird hier nichts.", null,
        el("div", { class: "cards" }, info.templates.map((t) => templateTile(t, chosen, toggle)))),
      requirementsCard(info, chosen),
      card("3 · Übernehmen", "Schaltet die Module der gewählten Vorlagen ein", null,
        el("div", { class: "row wrap" }, button("Module einschalten", apply, "primary", "power", { disabled: !chosen.size })),
        changed ? el("div", { style: "margin-top:14px" }, resultCallout(changed, chosen, go)) : null));
  };
  const apply = async () => {
    try {
      const res = await api("POST", "/api/setup", { templates: [...chosen] });
      info = res;
      changed = res.changed;
      await reloadModules();
      draw();
    } catch (e) { toast(e.message, true); }
  };
  api("GET", "/api/setup").then((res) => {
    info = res;
    for (const t of info.templates) if (t.active) chosen.add(t.id);
    draw();
  }).catch((e) => toast(e.message, true));
  return box;
}
