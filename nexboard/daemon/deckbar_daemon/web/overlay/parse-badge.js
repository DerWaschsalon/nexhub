/* Parse-Plakette an den Namen im A2Tools-Meter (Widget meter.js): nach einem Boss-Kill EU-Parse und, bei
 * Gildenmitgliedern, Gildenwert aus dem Hub (Daemon: Ereignis dps-parses). Farbstufen wie im Hub und im Run-Bild
 * (run_image.PARSE_TIERS, ParseValue.svelte). Stil in parses.css, das meter.js ins iframe legt. */

/** Stufe eines Parse-Werts 0–100, wie Warcraft Logs. */
export function tierOf(value) {
  if (value >= 100) return "gold";
  if (value >= 99) return "pink";
  if (value >= 95) return "orange";
  if (value >= 75) return "purple";
  if (value >= 50) return "blue";
  if (value >= 25) return "green";
  return "gray";
}

/** Plakette für [eu, guild] als { cls, eu, guild }; null ohne EU-Wert. */
export function badgeFor(parse) {
  const [eu, guild] = Array.isArray(parse) ? parse : [];
  if (!Number.isInteger(eu)) return null;
  return { cls: `dbx-parse dbx-tier-${tierOf(eu)}`, eu: String(eu), guild: Number.isInteger(guild) ? String(guild) : "" };
}

/** Plaketten im Dokument des Meters setzen: hinter jeden Namen mit Parse eine, sonst keine. Ändert das DOM nur, wo
 * sich etwas ändert (der MutationObserver von meter.js ruft das bei jeder Änderung der Liste wieder auf). */
export function markParses(doc, players) {
  for (const name of doc.querySelectorAll(".item .content .name")) {
    const want = players ? badgeFor(players[name.textContent.trim()]) : null;
    let have = name.nextElementSibling?.classList.contains("dbx-parse") ? name.nextElementSibling : null;
    if (!want) {
      have?.remove();
      continue;
    }
    if (have && have.className === want.cls && have.dataset.eu === want.eu && have.dataset.guild === want.guild) continue;
    if (!have) {
      have = doc.createElement("span");
      name.after(have);
    }
    have.className = want.cls;
    have.dataset.eu = want.eu;
    have.dataset.guild = want.guild;
    have.textContent = want.eu;
    if (want.guild) {
      const g = doc.createElement("small");
      g.textContent = want.guild;
      have.append(g);
    }
    have.title = want.guild ? `EU ${want.eu} · Gilde ${want.guild}` : `EU ${want.eu}`;
  }
}
