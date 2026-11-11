/* DPS-Meter: die Oberfläche des A2Tools-Meters als iframe (gleicher Ursprung). Ihr Shim (web/a2shim.js)
 * schickt Fenster-Befehle an die Seite; was davon das Widget selbst betrifft, beantwortet es hier:
 * Größe, Ziehen an Kopf- oder Fußzeile, Sperren, Bildschirmfoto. Dazu der Namenseffekt auf der eigenen
 * Zeile (effects.css), der nur im Kampf animiert. */
import * as host from "../host.js";
import * as layout from "../layout.js";
import { rectOf } from "../util.js";

const BLANK = "about:blank";
// Fenster-Befehle des Meters, die im Overlay nichts zu tun haben, mit ihrer Antwort
const NO_OPS = {
  start_tool_drag: null, window_resize_drag: null, begin_tool_resize: null, main_window_ready: null,
  window_show: null, details_window_ready: null, begin_window_resize: false, finish_window_resize: true,
  tool_window_ready: true, window_focus: true, overlay_lock_supported: true,
};

export default {
  events: ["dps"],
  click: true,
  defaultPos: () => [48, Math.max(40, innerHeight - 380)],

  mount(root, ctx) {
    const frame = document.createElement("iframe");
    frame.title = "DPS-Meter";
    frame.src = BLANK;
    root.append(frame);
    let fighting = false;
    let lockRect = null; // Schloss-Knopf der Meter-Oberfläche, in iframe-Koordinaten
    let cardOpen = false; // Karte (Popup) im Meter offen: dann nimmt auch gesperrt das ganze Meter Klicks an
    let lastDown = null; // letzter Mausdruck im Meter, in Seitenkoordinaten
    let effectsCss = null;

    const scale = () => ctx.cfg().scale || 1;
    /** Punkt im iframe → Punkt auf der Seite. */
    const toPage = (x, y) => {
      const r = root.getBoundingClientRect();
      return [r.left + x * scale(), r.top + y * scale()];
    };

    /** Erst laden, wenn das Widget an ist: das Meter rechnet sonst unsichtbar mit. */
    function load() {
      if (ctx.cfg()?.enabled && frame.getAttribute("src") === BLANK) frame.src = "/";
    }

    /* ---------------------------------------------------------- Namenseffekt */
    function markOwnRow(doc) {
      const fx = layout.current()?.fx || "";
      for (const name of doc.querySelectorAll(".item .content .name")) {
        const want = fx && name.closest(".item.isUser") ? `dbx-fx dbx-fx-${fx}` : "";
        const have = [...name.classList].filter((c) => c.startsWith("dbx-fx"));
        if (have.join(" ") === want) continue; // das Meter rendert Zeilen neu → Klassen ggf. wieder setzen
        name.classList.remove(...have);
        if (want) name.classList.add(...want.split(" "));
      }
    }

    async function applyFx() {
      const doc = frame.contentDocument;
      if (!doc?.head || !layout.current()) return;
      if (!doc.getElementById("deckbar-fx")) {
        effectsCss ??= await (await fetch("effects.css")).text();
        const style = doc.createElement("style");
        style.id = "deckbar-fx";
        style.textContent = effectsCss;
        doc.head.append(style);
        // Nur die Zeilenliste: das Meter hängt Zeilen ein und schaltet isUser an ihnen um
        const rows = doc.querySelector(".list:not(.barPreviewList)") || doc.documentElement;
        new MutationObserver(() => markOwnRow(doc)).observe(rows,
          { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
      }
      markOwnRow(doc);
      fxIdle();
    }

    /** Effekt nur im Kampf animieren (außerhalb steht er still und kostet nichts). */
    function fxIdle() {
      frame.contentDocument?.documentElement?.classList.toggle("dbx-idle", !fighting);
    }

    /* ---------------------------------------------------------- Ziehen an Kopf- oder Fußzeile */
    function watchDown() {
      const win = frame.contentWindow;
      if (!win || win.__deckbarDown) return;
      win.__deckbarDown = true;
      // am Fenster und in der Capture-Phase: vor dem Listener des Meters, der start_drag auslöst
      win.addEventListener("mousedown", (e) => { lastDown = toPage(e.clientX, e.clientY); }, true);
    }

    /** Das Meter meldet einen Mausdruck auf Kopf- oder Fußzeile: ab jetzt folgt das Widget der Maus. Eine
     * durchsichtige Fläche über allem fängt die Bewegungen, auch wenn die Maus das iframe verlässt;
     * Bewegungen, die das iframe noch selbst bekommt, zählen ebenso. */
    function startDrag() {
      const doc = frame.contentDocument;
      if (!doc || ctx.mode() === "edit" || startDrag.active) return;
      const c = ctx.cfg();
      const shield = document.createElement("div");
      shield.className = "drag-shield";
      document.body.append(shield);
      let last = lastDown; // wo der Mausdruck war, sonst ginge die erste Bewegung verloren
      const follow = (p) => {
        if (last) {
          c.x = Math.round(c.x + p[0] - last[0]);
          c.y = Math.round(c.y + p[1] - last[1]);
          ctx.place();
        }
        last = p;
      };
      const onPage = (e) => (e.buttons & 1 ? follow([e.clientX, e.clientY]) : stop());
      // Seitenkoordinaten zum Zeitpunkt des Ereignisses (vor dem Verschieben des iframes gerechnet)
      const onFrame = (e) => (e.buttons & 1 ? follow(toPage(e.clientX, e.clientY)) : stop());
      const stop = () => {
        if (!startDrag.active) return;
        startDrag.active = false;
        shield.remove();
        removeEventListener("pointermove", onPage, true);
        removeEventListener("pointerup", stop, true);
        doc.removeEventListener("mousemove", onFrame, true);
        doc.removeEventListener("mouseup", stop, true);
        layout.release();
        ctx.regionsChanged();
        ctx.save();
      };
      [c.x, c.y] = toPage(0, 0).map(Math.round);
      startDrag.active = true;
      layout.hold();
      addEventListener("pointermove", onPage, true);
      addEventListener("pointerup", stop, true);
      doc.addEventListener("mousemove", onFrame, true);
      doc.addEventListener("mouseup", stop, true);
    }

    /* ---------------------------------------------------------- Fenster-Befehle des Meters */
    for (const [cmd, answer] of Object.entries(NO_OPS)) host.handle(cmd, () => answer);
    host.handle("resize_window", (args) => {
      root.style.width = `${Math.ceil(Number(args.width) || 1)}px`;
      root.style.height = `${Math.ceil(Number(args.height) || 1)}px`;
      ctx.regionsChanged();
      return null;
    });
    host.handle("start_drag", () => { startDrag(); return null; });
    host.handle("set_overlay_locked", (args) => { host.requestMode(args.locked ? "lock" : "click"); return null; });
    host.handle("set_overlay_card_open", (args) => {
      cardOpen = !!args.open;
      ctx.regionsChanged();
      return null;
    });
    host.handle("set_lock_button_rect", (args) => {
      lockRect = { x: +args.x || 0, y: +args.y || 0, width: +args.width || 0, height: +args.height || 0 };
      ctx.regionsChanged();
      return null;
    });
    host.handle("capture_screenshot", (args) => {
      // Rechteck aus Meter-Koordinaten in die der ganzen Fläche umrechnen
      const r = root.getBoundingClientRect();
      const [x, y] = toPage(+args.x || 0, +args.y || 0);
      return host.forward("capture_screenshot", { ...args, x, y,
        width: (+args.width || r.width / scale()) * scale(), height: (+args.height || r.height / scale()) * scale() });
    });

    frame.addEventListener("load", () => {
      watchDown();
      applyFx();
      ctx.regionsChanged();
    });

    return {
      onEvent(_, data) {
        fighting = !!data.dps_active;
        fxIdle();
      },
      onLayout() {
        load();
        applyFx();
      },
      /** Gesperrt nimmt nur der Schloss-Knopf Klicks an, mit offener Karte das ganze Meter. */
      regions() {
        const whole = rectOf(root);
        if (cardOpen) return { click: [whole], lock: [whole] };
        if (!lockRect) return { click: [whole], lock: [] };
        const [x, y] = toPage(lockRect.x, lockRect.y).map(Math.floor);
        return { click: [whole], lock: [[x, y, Math.ceil(lockRect.width * scale()), Math.ceil(lockRect.height * scale())]] };
      },
    };
  },
};
