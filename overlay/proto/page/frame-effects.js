/* Wird vom Host in jedes Unterfenster eingehängt (WebEngineScript, runsOnSubFrames) und wirkt nur in
 * der Meter-Oberfläche: setzt den gewählten Namenseffekt auf die eigene Zeile (.item.isUser),
 * ohne die A2Tools-Oberfläche anzufassen. Den CSS-Platzhalter unten ersetzt der Host durch effects.css. */
(() => {
  if (window === window.top) return;
  const style = document.createElement("style");
  style.textContent = __EFFECTS_CSS__;
  document.head.append(style);

  let fx = "";
  const SEL = ".item.isUser .content .name";
  const apply = () => {
    for (const el of document.querySelectorAll(".item .content .name")) {
      const mine = fx && el.matches(SEL);
      const want = mine ? `dbx-fx dbx-fx-${fx}` : "";
      const cur = [...el.classList].filter((c) => c.startsWith("dbx-fx"));
      if (cur.join(" ") === want) continue; // A2Tools rendert Zeilen neu → Klassen ggf. wieder setzen
      el.classList.remove(...cur);
      if (want) el.classList.add(...want.split(" "));
    }
  };
  addEventListener("message", (e) => {
    if (e.data && "deckbarNameFx" in e.data) { fx = e.data.deckbarNameFx || ""; apply(); }
  });
  new MutationObserver(apply).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
})();
