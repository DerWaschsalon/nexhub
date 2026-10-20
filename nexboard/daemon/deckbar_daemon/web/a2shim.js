/*
 * Ersatz für window.__TAURI__, damit die Oberfläche des A2Tools DPS Meter (GPL-3.0, unverändert aus
 * capture/a2tools) im NexBoard-Overlay läuft. Steht in index.html vor allen anderen Skripten (a2ui.py).
 *
 *   Daten-Commands     → POST /api/a2/invoke (Daemon → deckbar-capture)
 *   Fenster-Commands   → Qt-Overlay über QWebChannel (Objekt "host", siehe overlay/deckbar-overlay),
 *                        bzw. eingebettet in die Overlay-Seite (web/overlay/) an deren
 *                        window.__DECKBAR_OVERLAY__.hostCall (gleicher Ursprung)
 *   Events             → GET /api/a2/events (Server-Sent Events) und Signal host.event
 *
 * Das Overlay setzt vorab window.__DECKBAR_WINDOW__ = {label, view}. Im normalen Browser fehlt es,
 * dann läuft alles als Hauptfenster und Fenster-Commands tun nichts (zum Ausprobieren).
 */
(function () {
  "use strict";

  const WIN = window.__DECKBAR_WINDOW__ || { label: "main", view: "main" };
  if (WIN.view && WIN.view !== "main") window.__A2_VIEW__ = WIN.view;
  // Tool-Fenster zeigen sich selbst (show/setFocus), kein main_window_ready
  window.__A2_WINDOW_STARTUP__ = { loadsHidden: false, reusesSettings: false };

  // Einstellungen synchron in localStorage, damit schon der erste Render stimmt
  try {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/a2/invoke", false);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.send(JSON.stringify({ cmd: "get_settings", args: {} }));
    const settings = JSON.parse(xhr.responseText).result || {};
    for (const [k, v] of Object.entries(settings)) localStorage.setItem(k, v);
  } catch (e) {
    console.warn("NexBoard: Einstellungen nicht geladen", e);
  }

  // ------------------------------------------------------------------ Qt-Overlay
  // Eingebettet als Widget der Overlay-Seite: die Seite ist der Host
  const EMBED = (() => {
    try { return window.parent !== window ? window.parent.__DECKBAR_OVERLAY__ || null : null; } catch { return null; }
  })();
  const hostReady = new Promise((resolve) => {
    if (EMBED) return resolve(null);
    if (typeof QWebChannel === "undefined" || !window.qt || !qt.webChannelTransport) return resolve(null);
    new QWebChannel(qt.webChannelTransport, (ch) => resolve(ch.objects.host || null));
  });

  const HOST_COMMANDS = new Set([
    "open_url", "quit_app", "start_drag", "start_tool_drag", "resize_window", "begin_tool_resize",
    "begin_window_resize", "finish_window_resize", "overlay_lock_supported", "set_overlay_locked",
    "set_lock_button_rect", "set_overlay_card_open", "main_window_ready", "tool_window_ready", "details_window_ready",
    "open_settings_window", "close_settings_window", "open_details_window", "close_details_window",
    "request_details_view", "take_pending_details_request", "close_tool_window", "list_monitors",
    "capture_screenshot", "window_show", "window_focus", "window_resize_drag",
  ]);
  // Ohne Overlay (Browser): was die Seite dann bekommt
  const NO_HOST = {
    overlay_lock_supported: false, list_monitors: [], take_pending_details_request: null,
    tool_window_ready: true, capture_screenshot: { clipboard: false, file: null },
  };

  async function hostCall(cmd, args) {
    if (EMBED) return EMBED.hostCall(cmd, args || {});
    const host = await hostReady;
    if (!host) {
      if (cmd === "request_details_view") throw "kein Overlay"; // Seite öffnet die Details dann inline
      if (cmd === "open_url") return void window.open(args.url, "_blank");
      return NO_HOST[cmd] ?? null;
    }
    return new Promise((resolve, reject) => {
      host.call(cmd, JSON.stringify(args || {}), (text) => {
        let res;
        try { res = JSON.parse(text); } catch { return reject("ungültige Antwort"); }
        if (res && "error" in res) reject(res.error);
        else resolve(res ? res.result : null);
      });
    });
  }

  async function invoke(cmd, args) {
    args = args || {};
    if (cmd === "compositor_resize_supported") return false; // Größe über expandViewport, wie unter X11
    if (HOST_COMMANDS.has(cmd)) return hostCall(cmd, args);
    const r = await fetch("/api/a2/invoke", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cmd, args }),
    });
    let body = {};
    try { body = await r.json(); } catch {}
    if (!r.ok) throw body.error || `${cmd}: HTTP ${r.status}`;
    return body.result;
  }

  // ------------------------------------------------------------------ Events
  const listeners = new Map(); // Name → Map(id → Callback)
  let nextId = 1;

  function dispatch(event, payload) {
    const set = listeners.get(event);
    if (!set) return;
    for (const [id, cb] of [...set]) {
      try { cb({ event, id, payload }); } catch (e) { console.error(`Listener ${event}`, e); }
    }
  }

  function listen(event, cb) {
    const id = nextId++;
    if (!listeners.has(event)) listeners.set(event, new Map());
    listeners.get(event).set(id, cb);
    return Promise.resolve(() => listeners.get(event)?.delete(id));
  }

  function connectEvents() {
    const es = new EventSource("/api/a2/events");
    es.onmessage = (e) => {
      try {
        const m = JSON.parse(e.data);
        dispatch(m.event, m.payload);
      } catch {}
    };
    // EventSource verbindet sich selbst neu (Daemon-Neustart)
  }
  connectEvents();
  hostReady.then((host) => {
    if (host) host.event.connect((name, json) => dispatch(name, json ? JSON.parse(json) : null));
  });

  // ------------------------------------------------------------------ __TAURI__
  const currentWindow = {
    label: WIN.label,
    show: () => invoke("window_show"),
    setFocus: () => invoke("window_focus"),
    startResizeDragging: (direction) => invoke("window_resize_drag", { direction }),
  };

  window.__TAURI__ = {
    core: { invoke },
    event: { listen, emit: async (event, payload) => dispatch(event, payload) },
    opener: { open: (url) => invoke("open_url", { url }), openUrl: (url) => invoke("open_url", { url }) },
    window: { getCurrentWindow: () => currentWindow },
  };
  window.__TAURI_INTERNALS__ = { invoke };

  // ------------------------------------------------------------------ Einstellungsfenster
  // Wie SETTINGS_WINDOW_SCRIPT in app.rs: Beenden, Schließen-Knopf und Escape
  if (WIN.view === "settings") {
    const hide = () => {
      window.dispatchEvent(new Event("settings-hidden"));
      dispatch("settings-hidden", null);
      invoke("close_settings_window");
    };
    document.addEventListener("click", (e) => {
      if (e.target.closest?.(".quitButton")) { e.preventDefault(); e.stopPropagation(); invoke("quit_app"); }
      else if (e.target.closest?.(".settingsClose")) { e.preventDefault(); e.stopPropagation(); hide(); }
    }, true);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); }, true);
  }
})();
