/* Modul Discord-Bot: Gruppen-DPS (Webhook des Bots) und Run-API, mit Testknöpfen. */
import { fill, el, icon, api, S, on, field, input, button, chip, callout, card, settingsRow, sw, saver, toast, clampInt, fmtWhen, modOn, setModule } from "../core.js";

function resultLine(res) {
  if (!res?.text) return el("span", { class: "faint", text: "noch nichts gesendet" });
  return el("span", { class: res.ok ? "" : "", style: `color:${res.ok ? "var(--ok)" : "var(--bad)"}`, text: `${fmtWhen(res.at)} · ${res.text}` });
}

function botTab(ctx) {
  const box = el("div", { class: "stack" });
  const save = saver("PUT", "/api/bot", (res) => { S.bot = res; draw(); }, 350, "Bot-Einstellungen gespeichert");
  const patch = (p) => { Object.assign(S.bot.settings, p); save(p); };
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
      callout("warn", "shield-check", el("span", {}, "Beide Wege schicken Charakternamen deiner Mitspieler an den Server des Bots. Trag nur Adressen von Bots ein, denen deine Gruppe vertraut, und sprich das mit ihr ab.")),
      el("div", { class: "cols" },
        card("Gruppen-DPS", "Endstand der eigenen Gruppe nach einem Kampf", st.dps_enabled && st.dps_url ? chip("aktiv", "ok") : chip("aus"),
          settingsRow("Senden", b.targets.dps || "Keine Adresse eingetragen", sw(st.dps_enabled, (v) => patch({ dps_enabled: v }))),
          el("div", { class: "grid", style: "margin-top:6px" },
            field("Webhook-URL des Bots", input(st.dps_url, (v) => patch({ dps_url: v.trim() }), { type: "password", autocomplete: "off", spellcheck: "false", lazy: true, placeholder: "http://bot:8787/dps/<token>" }), "TheWashBot: /dps-webhook kanal:#… zeigt die Adresse"),
            el("div", { class: "grid g2" },
              field("Mindestdauer (s)", input(st.dps_min_seconds, (v) => patch({ dps_min_seconds: clampInt(v, 0, 3600, 20) }), { type: "number", min: 0, max: 3600 })),
              field("Mindestens Mitglieder", input(st.dps_min_party, (v) => patch({ dps_min_party: clampInt(v, 1, 8, 2) }), { type: "number", min: 1, max: 8 })))),
          settingsRow("Nur Bosse", "Trash-Mobs nicht melden", sw(st.dps_boss_only, (v) => patch({ dps_boss_only: v }))),
          settingsRow("Nur besiegte", "Wipes und Abbrüche nicht melden", sw(st.dps_kills_only, (v) => patch({ dps_kills_only: v }))),
          el("div", { class: "row wrap", style: "margin-top:14px" },
            button("Letzten Kampf senden", test("dps"), "sm", "send", { disabled: !st.dps_url || !b.last_fight }),
            el("span", { class: "hint small" }, b.last_fight ? `Letzter: ${b.last_fight.target} (${b.last_fight.party} in der Gruppe)` : "Noch kein Kampf seit dem Start.")),
          el("p", { class: "hint small", style: "margin-top:10px" }, resultLine(b.result.dps))),
        card("Dungeon-Runs", "Run-Ergebnis zum Zusammenführen mehrerer Spieler", st.runs_enabled && st.runs_url && st.runs_token ? chip("aktiv", "ok") : chip("aus"),
          !modOn("aion2.runs") ? callout("info", "information-outline", el("span", {}, "Braucht das Modul „AION 2 · Dungeon-Runs“ (es erkennt, wann ein Run vorbei ist)."), button("Einschalten", () => setModule("aion2.runs", true).catch((e) => toast(e.message, true)), "sm primary")) : null,
          settingsRow("Senden", b.targets.runs || "Keine Adresse eingetragen", sw(st.runs_enabled, (v) => patch({ runs_enabled: v }))),
          el("div", { class: "grid", style: "margin-top:6px" },
            field("Run-API des Bots", input(st.runs_url, (v) => patch({ runs_url: v.trim() }), { type: "password", autocomplete: "off", spellcheck: "false", lazy: true, placeholder: "https://…/api/aion/fight" }), "TheWashBot: /aion zeigt Adresse und Token"),
            field("Token", input(st.runs_token, (v) => patch({ runs_token: v.trim() }), { type: "password", autocomplete: "off", spellcheck: "false", lazy: true }))),
          el("div", { class: "row wrap", style: "margin-top:14px" },
            button("Letzten Run senden", test("runs"), "sm", "send", { disabled: !(st.runs_url && st.runs_token) })),
          el("p", { class: "hint small", style: "margin-top:10px" }, resultLine(b.result.runs)))),
      card("Bot-Steuerung", "Kommt später", null,
        el("p", { class: "hint", text: "Hier soll der Bot selbst verwaltet werden (Kanäle, Rollen, Musik). Bis dahin läuft die Einrichtung über die Slash-Befehle bzw. das Dashboard des Bots." })));
  };
  ctx.onUnmount(on("bot", draw));
  draw();
  if (!S.bot) api("GET", "/api/bot").then((r) => { S.bot = r; draw(); });
  return box;
}

export default {
  tabs: [{ id: "bot", label: "Anbindung", icon: "robot" }],
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
  render(tab, ctx) { return botTab(ctx); },
};
