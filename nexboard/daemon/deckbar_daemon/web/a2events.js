/*
 * Gemeinsamer Ereignis-Strom aller Seiten eines Browser-Profils (SharedWorker, siehe a2shim.js).
 * Chromium erlaubt je Host nur 6 offene HTTP/1.1-Verbindungen. Mit einem EventSource pro Plugin-Fenster
 * und Widget wären die schnell belegt, und jede weitere Anfrage hinge. Hier läuft genau einer.
 */
"use strict";

const ports = new Set();
let source = null;

function connect() {
  source = new EventSource("/api/a2/events");
  source.onmessage = (e) => {
    for (const port of ports) port.postMessage(e.data);
  };
  // EventSource verbindet sich selbst neu (Daemon-Neustart)
}

self.onconnect = (e) => {
  const port = e.ports[0];
  ports.add(port);
  port.onmessage = (m) => {
    if (m.data === "bye") ports.delete(port);
  };
  port.start();
  if (!source) connect();
};
