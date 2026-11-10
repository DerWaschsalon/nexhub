/* Formulare aus dem Einstellungs-Schema eines Moduls (pydantic): eine Stelle für alle Einstellungsseiten.
   Hinweise im Schema (json_schema_extra): hidden, advanced (unter „Erweitert“), secret, labels {Wert: Text},
   show_if {Feld: [Werte]} und choices "pages" (Seiten der Leiste). */
import { el, fill, api, on, S, field, input, select, sw, settingsRow, card, saver, collapsible } from "./core.js";

const NO_PAGE = "— nicht wechseln —";

/** Optional[X] steht im Schema als anyOf [X, null]: Typ und Grenzen kommen aus X. */
function shape(prop) {
  const inner = (prop.anyOf || []).find((v) => v.type !== "null") || {};
  return { ...inner, ...prop, nullable: !!prop.anyOf };
}

function visible(prop, values) {
  if (prop.hidden) return false;
  return Object.entries(prop.show_if || {}).every(([key, allowed]) => allowed.includes(values[key]));
}

function options(prop) {
  if (prop.choices === "pages") {
    return { "": NO_PAGE, ...Object.fromEntries((S.layout?.pages || []).map((p) => [p.id, p.name || p.id])) };
  }
  return Object.fromEntries(prop.enum.map((v) => [v, prop.labels?.[v] ?? v]));
}

/** Ein Eingabeelement; set(value) bekommt schon den passenden Typ. */
function control(prop, value, set) {
  if (prop.enum || prop.choices) return select(options(prop), value ?? "", (v) => set(v === "" && prop.nullable ? null : v));
  if (prop.type === "integer" || prop.type === "number") {
    return input(value, (v) => set(Number(v)), { type: "number", min: prop.minimum, max: prop.maximum });
  }
  const attrs = { lazy: true, spellcheck: "false", maxlength: prop.maxLength };
  if (prop.secret) Object.assign(attrs, { type: "password", autocomplete: "off" });
  return input(value ?? "", (v) => set(v.trim() === "" && prop.nullable ? null : v.trim()), attrs);
}

/** Felder in der Reihenfolge des Schemas: Schalter als Zeile, Eingaben im Raster, Erweitertes zugeklappt.
    view merkt sich über Neuzeichnen hinweg, ob „Erweitert“ offen ist. */
export function schemaForm(schema, values, patch, view = {}) {
  const groups = { basic: [], advanced: [] };
  for (const [name, raw] of Object.entries(schema.properties)) {
    const prop = shape(raw);
    if (!visible(prop, values)) continue;
    const set = (v) => patch({ [name]: v });
    const items = groups[prop.advanced ? "advanced" : "basic"];
    if (prop.type === "boolean") {
      items.push(settingsRow(prop.title || name, prop.description, sw(values[name], set)));
      continue;
    }
    const entry = field(prop.title || name, control(prop, values[name], set), prop.description);
    const last = items[items.length - 1];
    if (last?.classList.contains("grid")) last.append(entry);  // Eingaben hintereinander in ein Raster
    else items.push(el("div", { class: "grid" }, entry));
  }
  if (!groups.advanced.length) return groups.basic;
  return [groups.basic, collapsible("Erweitert", view, groups.advanced)];
}

/** Karte mit den Einstellungen eines Moduls: lädt, zeigt und speichert über /api/m/<id>/settings.
    Zeichnet neu, wenn das Layout kommt (Auswahl der Seiten). */
export function moduleSettings(ctx, id, title, sub, ...extra) {
  const body = el("div", { class: "stack", style: "gap:10px" });
  let data = null;
  const view = {};
  const save = saver("PUT", `/api/m/${id}/settings`, (res) => { data = res; draw(); }, 400, "Gespeichert");
  const patch = (p) => { Object.assign(data.settings, p); draw(); save(p); };
  const draw = () => fill(body, data ? schemaForm(data.schema, data.settings, patch, view) : null, ...extra);
  ctx.onUnmount(on("layout", draw));
  api("GET", `/api/m/${id}/settings`).then((res) => { data = res; draw(); });
  return card(title, sub, null, body);
}
