/* Karte des Moduls AION 2 · Radar: Cubes, ihre Spawnpunkte und Fundorte, Teleporter und du als Pfeil in
 * Blickrichtung. Ziehen = verschieben, Mausrad = Zoom, ⌖ = wieder dir folgen.
 *
 * Kartenbilder und Kartenlogik (MiniMap) kommen aus dem installierten Plugin Pet Soul Tracker, nichts
 * davon liegt hier doppelt. Ohne das Plugin sagt das Widget, was fehlt. Die Monster der Pet-Arten zeigt
 * weiter der Pet Soul Tracker in seinem eigenen Fenster. */
import * as host from "../host.js";
import { el } from "../util.js";
import { COLOR, circle } from "./radar-draw.js";

const PLUGIN_FILES = "/__a2plugin__/pet-souls/";
const ICON_PX = 20; // Teleporter-Symbol, bleibt beim Zoomen gleich groß
const PULSE_MS = 100; // Cubes pulsieren: so oft neu zeichnen, solange einer da ist
const STALE_MS = 15_000; // ohne Blickrichtung wird eine so alte Position blass
const SOURCE_URL = "https://www.aion2timers.com/map/";

function loadScript(url) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.onload = resolve;
    script.onerror = reject;
    document.head.append(script);
  });
}

function build(root) {
  const head = root.appendChild(el("div", "map-head"));
  const ui = {
    name: head.appendChild(el("span", "map-name")), status: head.appendChild(el("span", "map-status")),
    canvas: root.appendChild(el("canvas", "map-canvas")),
    buttons: root.appendChild(el("div", "map-buttons")),
    note: root.appendChild(el("p", "map-note")), tip: root.appendChild(el("div", "map-tip")),
    source: root.appendChild(el("a", "map-source", "Karte: Aion 2 Timers")),
    pictures: root.appendChild(el("div")),
  };
  const button = (text, title) => {
    const b = ui.buttons.appendChild(el("button", "", text));
    b.type = "button";
    b.title = title;
    return b;
  };
  Object.assign(ui, { zoomIn: button("+", "Vergrößern"), zoomOut: button("−", "Verkleinern"), follow: button("⌖", "Zurück zu dir") });
  ui.pictures.hidden = ui.tip.hidden = ui.note.hidden = true;
  ui.source.href = SOURCE_URL;
  ui.source.title = "Kartenbilder und Spawnpunkte: Aion 2 Timers, Live-Karte öffnen";
  return ui;
}

export default {
  events: ["radar"],
  click: true,
  hud: true,
  defaultPos: () => [innerWidth - 420, 520],

  mount(root, ctx) {
    const ui = build(root);
    let radar = { aktiv: false };
    let map = null; // MiniMap des Pet Soul Trackers
    let loading = null;
    let data = null; // Spawnpunkte, Fundorte, Teleporter der gezeigten Karte (GET /api/radar/karte)
    let dataKey = "";
    let icon = null; // Teleporter-Symbol
    let drawn = []; // gezeichnete Teleporter [Name, x, y], für den Tipp
    let me = null; // {pos, at}
    let followSetting = null;
    let gliding = 0; // laufender Schritt des sanften Nachführens

    /* ---------------------------------------------------------- MiniMap aus dem Plugin */
    async function loadMiniMap() {
      try {
        await loadScript(`${PLUGIN_FILES}maps.js`);
        await loadScript(`${PLUGIN_FILES}minimap.js`);
      } catch {
        ui.note.hidden = false;
        ui.note.textContent = "Die Karte braucht das Plugin Pet Soul Tracker (Im Spiel → Plugins).";
        return;
      }
      for (const id of Object.keys(PET_MAPS)) {
        const img = ui.pictures.appendChild(el("img", "mapPic"));
        img.dataset.map = id;
        img.loading = "lazy";
        img.src = `${PLUGIN_FILES}maps/${id}.webp`;
      }
      map = new PetMiniMap.MiniMap(
        { canvas: ui.canvas, zoomIn: ui.zoomIn, zoomOut: ui.zoomOut, follow: ui.follow, note: ui.note });
      // Die MiniMap kennt als Figur nur ihren Punkt: sie bekommt keine, folgt hier dir, und der Pfeil kommt
      // mit allem, was nur das Radar kennt, in drawOverlay
      const drawMap = map.draw.bind(map);
      map.draw = () => {
        const following = map.follow;
        if (following && me) {
          glideTo(me.pos);
          map.follow = false;
        }
        drawMap();
        map.follow = following;
        ui.follow.hidden = following;
        drawOverlay();
      };
      update();
    }

    /** Sanft zur Position, ein Teleport springt (wie #glideTo der MiniMap). */
    function glideTo(target) {
      const far = (limit) => Math.hypot(target[0] - map.center[0], target[1] - map.center[1]) > limit;
      if (!map.center || far(50_000)) {
        map.center = [target[0], target[1]];
        return;
      }
      map.center = [map.center[0] + (target[0] - map.center[0]) * 0.35, map.center[1] + (target[1] - map.center[1]) * 0.35];
      if (far(map.zoom * 50) && !gliding) {
        gliding = requestAnimationFrame(() => {
          gliding = 0;
          map.draw();
        });
      }
    }

    /* ---------------------------------------------------------- Daten des Radars zur Karte */
    /** Neu holen, wenn eine andere Karte gewählt ist oder neue Spawnpunkte dazukamen. */
    async function loadData() {
      const key = `${radar.karte}|${radar.punkte}`;
      if (key === dataKey) return;
      dataKey = key;
      try {
        data = await (await fetch("/api/radar/karte")).json();
      } catch (e) {
        dataKey = "";
        host.log(`Karte nicht geladen: ${e}`);
        return;
      }
      if (data.symbol && data.name) {
        const img = new Image();
        img.onload = () => { icon = img; };
        img.src = `/api/radar/karte/symbol?karte=${encodeURIComponent(data.name)}`;
      }
      map?.draw();
    }

    /** Teleporter und Fundorte stehen in Bild-Koordinaten der Radar-Karte: zurück in die Welt. */
    function imageToWorld(u, v) {
      const [a, b, c, d, e, f] = data.m;
      const det = a * e - b * d;
      return [(e * (u - c) - b * (v - f)) / det, (a * (v - f) - d * (u - c)) / det];
    }

    /** Die Karte, auf der du stehst (Zonen-ID = Karten-ID), sonst die auf der NexBoard-Seite eingestellte. */
    function mapId() {
      if (PET_MAPS[radar.zone]) return String(radar.zone);
      return Object.keys(PET_MAPS).find((id) => PET_MAPS[id].name === radar.karte) || null;
    }

    function update() {
      if (!radar.aktiv || !ctx.cfg()?.enabled) return;
      loadData();
      if (!map) {
        loading ??= loadMiniMap();
        return;
      }
      const follow = radar.einstellungen?.karte_folgen;
      if (follow !== followSetting) { // auf der NexBoard-Seite umgestellt
        followSetting = follow;
        map.follow = !!follow;
      }
      me = radar.position ? { pos: radar.position, at: Date.now() - (radar.position_alter || 0) * 1000 } : null;
      const id = mapId();
      map.set({ mapId: id, you: null });
      ui.name.textContent = PET_MAPS[id]?.name || "";
      ui.status.textContent = data?.punkte?.length ? `${data.punkte.length} Spawnpunkte` : "";
    }

    /* ---------------------------------------------------------- Zeichnen über dem Kartenbild */
    /** Gleiche Rechnung wie MiniMap.draw: Welt → Leinwand. */
    function drawOverlay() {
      if (!map?.center || !ui.canvas.isConnected) return;
      const width = ui.canvas.clientWidth || 300;
      const height = ui.canvas.clientHeight || 220;
      const perPixel = map.zoom * 100;
      const screen = (x, y) => [width / 2 + (x - map.center[0]) / perPixel, height / 2 + (y - map.center[1]) / perPixel];
      const c = ui.canvas.getContext("2d");
      drawn = [];
      if (data?.m && PET_MAPS[map.scene.mapId]?.name === data.name) drawMapData(c, screen);
      drawCubes(c, screen);
      if (me) drawMe(c, ...screen(me.pos[0], me.pos[1]));
    }

    function drawMapData(c, screen) {
      c.fillStyle = COLOR.findSpot;
      for (const [u, v] of data.fundorte || []) {
        circle(c, ...screen(...imageToWorld(u, v)), 3.5);
        c.fill();
      }
      c.lineWidth = 1.6;
      for (const [x, y, source] of data.punkte || []) {
        c.strokeStyle = source === "radar" ? COLOR.spawnSeen : COLOR.spawnManual;
        circle(c, ...screen(x, y), 4.5);
        c.stroke();
      }
      if (!icon) return;
      for (const [name, u, v] of data.teleporter || []) {
        const [x, y] = screen(...imageToWorld(u, v));
        c.drawImage(icon, x - ICON_PX / 2, y - ICON_PX / 2, ICON_PX, ICON_PX);
        drawn.push([name, x, y]);
      }
    }

    function drawCubes(c, screen) {
      const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 200);
      for (const cube of radar.aktiv ? radar.cubes || [] : []) {
        const [x, y] = screen(cube.x, cube.y);
        c.fillStyle = `rgba(255, 82, 82, ${(60 + 80 * pulse) / 255})`;
        circle(c, x, y, 9 + 4 * pulse);
        c.fill();
        c.fillStyle = COLOR.cube;
        circle(c, x, y, 5);
        c.fill();
      }
    }

    /** Du: ein Pfeil in Blickrichtung, sonst ein Punkt (veraltet blass). */
    function drawMe(c, x, y) {
      c.save();
      // Stehst du still, altert die Position, die Blickrichtung aber nicht: mit Richtung bleibt der Pfeil kräftig
      c.globalAlpha = !radar.kurs && Date.now() - me.at > STALE_MS ? 0.5 : 1;
      c.fillStyle = "rgba(255, 255, 255, .18)";
      circle(c, x, y, 14);
      c.fill();
      c.translate(x, y);
      c.lineJoin = "round";
      c.strokeStyle = "#14161e";
      c.lineWidth = 2.5;
      c.fillStyle = "#ffe066";
      if (radar.kurs) {
        // Karte: Norden oben, Welt +x rechts, Welt +y unten. Also im Uhrzeigersinn von Norden
        c.rotate(Math.atan2(radar.kurs[0], -radar.kurs[1]));
        c.beginPath();
        c.moveTo(0, -14);
        c.lineTo(9, 10);
        c.lineTo(0, 5);
        c.lineTo(-9, 10);
        c.closePath();
      } else {
        circle(c, 0, 0, 6);
      }
      c.stroke();
      c.fill();
      c.restore();
    }

    function showTip(e) {
      const r = ui.canvas.getBoundingClientRect();
      const s = ctx.cfg().scale || 1;
      const [mx, my] = [(e.clientX - r.left) / s, (e.clientY - r.top) / s];
      const hit = drawn.find(([, x, y]) => Math.abs(x - mx) <= ICON_PX / 2 && Math.abs(y - my) <= ICON_PX / 2);
      ui.tip.hidden = !hit;
      if (!hit) return;
      ui.tip.textContent = hit[0];
      ui.tip.style.left = `${mx + 12}px`;
      ui.tip.style.top = `${my + 12}px`;
    }

    ui.canvas.addEventListener("pointermove", showTip);
    ui.source.addEventListener("click", (e) => {
      e.preventDefault();
      host.forward("open_url", { url: SOURCE_URL }).catch(() => {});
    });
    const resize = new ResizeObserver(() => map?.draw());
    resize.observe(ui.canvas);
    const pulse = setInterval(() => { if (radar.aktiv && radar.cubes?.length && ctx.cfg()?.enabled) map?.draw(); }, PULSE_MS);

    return {
      onEvent(_, next) {
        radar = next;
        update();
      },
      onLayout: update,
      destroy() {
        clearInterval(pulse);
        resize.disconnect();
      },
    };
  },
};
