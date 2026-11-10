/* Modul Discord-Bot: Gruppen-DPS (Webhook des Bots) und Run-API, mit Testknöpfen. */
import { fill, el, api, S, on, button, chip, callout, card, settingsRow, toast, fmtWhen, modOn, setModule } from "../core.js";
import { moduleSettings } from "../form.js";

function resultLine(res) {
  if (!res?.text) return el("span", { class: "faint", text: "noch nichts gesendet" });
  return el("span", { class: res.ok ? "" : "", style: `color:${res.ok ? "var(--ok)" : "var(--bad)"}`, text: `${fmtWhen(res.at)} · ${res.text}` });
}

function botTab(ctx) {
  const box = el("div", { class: "stack" });
  const test = (kind) => async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    try { const r = await api("POST", `/api/bot/test/${kind}`); S.bot = r; toast(`Gesendet: ${r.text}`); draw(); } catch (err) { toast(err.message, true); } finally { b.disabled = false; }
  };
  const draw = () => {
    const b = S.bot;
    if (!b) return;
    const st = b.settings;
    fill(box,
      card("Gesendet", "Letzter Versand je Weg", null,
        !modOn("aion2.runs") ? callout("info", "information-outline", el("span", {}, "Runs schicken braucht das Modul „AION 2 · Dungeon-Runs“ (es erkennt, wann ein Run vorbei ist)."), button("Einschalten", () => setModule("aion2.runs", true).catch((e) => toast(e.message, true)), "sm primary")) : null,
        settingsRow("Gruppen-DPS", b.last_fight ? `Letzter Kampf: ${b.last_fight.target} (${b.last_fight.party} in der Gruppe)` : "Noch kein Kampf seit dem Start.",
          button("Letzten Kampf senden", test("dps"), "sm", "send", { disabled: !st.dps_url || !b.last_fight })),
        el("p", { class: "hint small" }, resultLine(b.result.dps)),
        settingsRow("Dungeon-Runs", b.targets.runs || "Keine Adresse eingetragen",
          button("Letzten Run senden", test("runs"), "sm", "send", { disabled: !(st.runs_url && st.runs_token) })),
        el("p", { class: "hint small" }, resultLine(b.result.runs))));
  };
  ctx.onUnmount(on("bot", draw));
  draw();
  if (!S.bot) api("GET", "/api/bot").then((r) => { S.bot = r; draw(); });
  return el("div", { class: "stack" },
    callout("warn", "shield-check", el("span", {}, "Beide Wege schicken Charakternamen deiner Mitspieler an den Server des Bots. Trag nur Adressen von Bots ein, denen deine Gruppe vertraut, und sprich das mit ihr ab.")),
    moduleSettings(ctx, "discord.bot", "Anbindung", "Gruppen-DPS nach Kämpfen und Ergebnisse nach Runs"),
    box);
}

export default {
  status: () => {
    const r = S.bot?.result || {};
    if ([r.dps, r.runs].some((x) => x && x.ok === false)) return "bad";
    const st = S.bot?.settings;
    return st && ((st.dps_enabled && st.dps_url) || (st.runs_enabled && st.runs_url)) ? "" : "off";
  },
  card() {
    const b = S.bot;
    const st = b?.settings || {};
    const last = [b?.result?.dps, b?.result?.runs].filter((x) => x?.at).sort((x, y) => y.at - x.at)[0];
    return el("div", { class: "stack", style: "gap:10px" },
      el("div", { class: "row wrap" }, chip("Gruppen-DPS", st.dps_enabled && st.dps_url ? "ok" : ""), chip("Runs", st.runs_enabled && st.runs_url ? "ok" : "")),
      last ? resultLine(last) : el("span", { class: "faint", text: "Noch nichts gesendet." }));
  },
  pages: [{ id: "discord.bot", render: (tab, ctx) => botTab(ctx) }],
};
