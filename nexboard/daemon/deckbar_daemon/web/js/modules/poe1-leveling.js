/* Modul PoE 1 · Leveling-Guide: der aktuelle Schritt wie auf der Leiste, hier mit Symbolen und Layout-Bildern,
   dazu Bedienung, PoB-Import, Suchtexte für Händler und Einstellungen. */
import { fill, el, api, S, on, button, chip, callout, card, select, toast, collapsible } from "../core.js";
import { moduleSettings } from "../form.js";

const BASE = "/api/poe1/leveling";
const ICONS = "/static/poe1/icons/";
const LAYOUTS = "/static/poe1/layouts/";
const ACT_CHOICES = { 0: "zuerst möglich", ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [i + 1, `Akt ${i + 1}`])) };

/** Befehl oder Import schicken; die Antwort ist der neue Stand. */
async function post(path, body) {
  try {
    const res = await api("POST", `${BASE}${path}`, body);
    S.leveling = res;
    return res;
  } catch (e) {
    toast(e.message, true);
    return null;
  }
}

function copyButton(text) {
  return button(null, async () => {
    try { await navigator.clipboard.writeText(text); toast("Kopiert – im Spiel Strg+F, einfügen"); } catch { toast("Kopieren ging nicht", true); }
  }, "sm icon ghost", "content-copy", { title: "Kopieren" });
}

function segment(s, showLayout) {
  if (s.image) return el("img", { class: "gi", src: `${ICONS}${s.image}.png`, alt: s.image, onerror: (e) => e.target.remove() });
  const span = el("span", { style: `color:#${s.color}`, text: s.text });
  if (s.layout) {
    span.classList.add("layout-term");
    span.title = "Layout zeigen";
    span.onclick = () => showLayout(s.layout);
  }
  return span;
}

function stepCard(v, view, draw) {
  const showLayout = (name) => { view.layout = view.layout === name ? null : name; draw(); };
  const chips = [
    S.leveling.running ? chip("PoE läuft", "ok") : chip("PoE nicht gestartet"),
    v.zone ? chip(`${v.act} · ${v.zone}`) : null,
    v.level ? chip(`Stufe ${v.level}${v.character ? ` · ${v.character}` : ""}`) : null,
    v.xp ? chip(`XP ${v.xp.text} · ohne Abzug ${v.xp.low}–${v.xp.high}`, v.xp.text === "100 %" ? "ok" : "warn") : null,
  ];
  const lines = el("ul", { class: "guide-lines" }, v.lines.map((line) =>
    el("li", { class: line.bullet || "plain" }, line.segments.map((s) => segment(s, showLayout)))));
  const layout = view.layout
    ? el("figure", { class: "guide-layout" }, el("img", { src: `${LAYOUTS}${encodeURIComponent(view.layout.replaceAll(" ", "_"))}.jpg`, alt: view.layout }),
      el("figcaption", { class: "hint small", text: view.layout }))
    : null;
  const search = v.search.length
    ? el("div", { class: "stack", style: "gap:6px" }, el("b", { class: "small", style: "margin-top:12px", text: "Suchtext für den Händler" }),
      v.search.map((text) => el("div", { class: "row" }, el("code", { class: "grow", text }), copyButton(text))))
    : null;
  return card(`Schritt ${v.step} von ${v.steps}`, "Wie auf der Leiste; türkise Begriffe zeigen ein Layout-Bild", null,
    el("div", { class: "row wrap", style: "gap:6px" }, chips),
    v.message ? callout("warn", "information-outline", v.message) : null,
    lines, layout, search,
    el("div", { class: "row wrap", style: "margin-top:14px" },
      button("Zurück", () => post("/command", { cmd: "back" }), "", "chevron-left"),
      button("Weiter", () => post("/command", { cmd: "next" }), "primary", "chevron-right"),
      button("Zur aktuellen Zone", () => post("/command", { cmd: "skip" }), "", "arrow-right", { title: "Springt zu dem Schritt, der in die Zone führt, in der du stehst (auf der Leiste: Weiter lange halten)" }),
      button("Von vorn", () => confirm("Guide auf Schritt 1 zurücksetzen?") && post("/command", { cmd: "reset" }), "ghost", "restart")));
}

function gemSources(v) {
  const gems = [...new Set((v.build?.skill_sets || []).flatMap((s) => s.groups.flatMap((g) => g.gems.map(gemKey))))];
  const save = async (gem, act) => {
    const sources = { ...v.gem_sources, [gem]: Number(act) };
    try { S.leveling = await api("PUT", `${BASE}/gem-sources`, { sources }); } catch (e) { toast(e.message, true); }
  };
  return el("table", { class: "list" }, el("tbody", {}, gems.map((gem) => el("tr", {},
    el("td", { text: gem }), el("td", {}, select(ACT_CHOICES, String(v.gem_sources[gem] || 0), (act) => save(gem, act)))))));
}

const gemKey = (g) => (g.support && !g.name.includes("support") ? `${g.name} support` : g.name);

function buildCard(v, view) {
  const area = el("textarea", { rows: 3, placeholder: "PoB-Code, pobb.in-Link oder Guide (JSON aus Exile-UI)", spellcheck: "false" });
  const b = v.build;
  const info = b
    ? el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "row wrap" }, chip(b.char_class), ...b.ascendancies.filter((a) => a !== "none").map((a) => chip(a, "info")),
        v.custom_guide ? chip("eigener Guide", "warn") : null),
      collapsible(`Gem-Gruppen (${b.skill_sets.length} ${b.skill_sets.length === 1 ? "Set" : "Sets"})`, view.sets, b.skill_sets.map((set) =>
        el("div", { style: "margin-top:8px" }, el("b", { class: "small", text: set.title }),
          el("div", { class: "gem-groups" }, set.groups.map((g) => el("div", { class: "gem-group" },
            g.label ? el("span", { class: "faint small", text: g.label }) : null,
            g.gems.map((gem) => el("span", { class: gem.support ? "gem support" : "gem", text: gem.name })))))))),
      v.gems_left.length ? callout("info", "information-outline", `Nicht im Guide untergekommen: ${v.gems_left.join(", ")}`) : null,
      v.build_search.length ? el("div", { class: "stack", style: "gap:6px" }, el("b", { class: "small", text: "Alle Gems des Builds (Lilly, ab Akt 6)" }),
        v.build_search.map((text) => el("div", { class: "row" }, el("code", { class: "grow", text }), copyButton(text)))) : null,
      collapsible("Kaufort je Gem", view.sources, el("p", { class: "hint small", text: "Ohne Wahl kauft der Guide jedes Gem beim ersten Händler, der es hat." }), gemSources(v)))
    : el("p", { class: "hint", text: "Noch kein Build: ohne ihn zeigt der Guide keine Gem-Belohnungen und Käufe." });
  return card("Build", "Aus Path of Building; Klasse, Banditen und Gems bestimmen die Belohnungen im Guide", null, info,
    el("div", { class: "stack", style: "gap:8px;margin-top:14px" }, area,
      el("div", { class: "row wrap" },
        button("Übernehmen", async () => {
          const res = await post("/import", { code: area.value });
          if (res) toast(res.kind === "guide" ? "Eigener Guide übernommen" : "Build übernommen");
        }, "primary sm", "download"),
        v.custom_guide ? button("Mitgelieferten Guide nutzen", () => post("/default-guide"), "sm ghost", "restart") : null)));
}

function levelingPage(ctx) {
  const box = el("div", { class: "stack" });
  const view = { layout: null, sets: {}, sources: {} };  // bleibt über Neuzeichnen: offenes Layout-Bild, aufgeklappte Teile
  const settings = moduleSettings(ctx, "poe1.leveling", "Einstellungen", "Gelten sofort, auch für die Leiste");
  const draw = () => {
    const v = S.leveling;
    if (!v) return;
    fill(box, el("div", { class: "cols" }, stepCard(v, view, draw), buildCard(v, view)), settings);
  };
  ctx.onUnmount(on("leveling", draw));
  if (S.leveling) draw();
  else api("GET", BASE).then((v) => { S.leveling = v; draw(); });
  return box;
}

export default {
  card() {
    const v = S.leveling;
    return el("span", { class: "faint", text: v ? `Schritt ${v.step}/${v.steps}${v.zone ? ` · ${v.zone}` : ""}` : "Act Tracker nach Exile-UI" });
  },
  pages: [{ id: "poe1.leveling", name: "Leveling-Guide", render: (tab, ctx) => levelingPage(ctx) }],
};
