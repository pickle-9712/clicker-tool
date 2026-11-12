// Relay server: serves the control panel and forwards messages from
// "sender" connections to "receiver" connections in the same room.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT) || 8787;
const PUBLIC_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "public");
const MAX_TEXT = 300;
const ROOM_RE = /^[A-Z0-9]{4,16}$/;

// room code -> { senders: Set<ws>, receivers: Set<ws> }
const rooms = new Map();

function getRoom(code) {
  let room = rooms.get(code);
  if (!room) {
    room = { senders: new Set(), receivers: new Set() };
    rooms.set(code, room);
  }
  return room;
}

function send(ws, obj) {
  if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(obj));
}

function broadcastStatus(room) {
  const status = { type: "status", receivers: room.receivers.size, senders: room.senders.size };
  for (const ws of room.senders) send(ws, status);
  for (const ws of room.receivers) send(ws, status);
}

const SOUNDS_DIR = path.join(PUBLIC_DIR, "sounds");

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");

  // list of available click sounds, for the receiver to download
  if (url.pathname === "/sounds") {
    fs.readdir(SOUNDS_DIR, (err, names) => {
      const list = err ? [] : names.filter((n) => /^[\w-]+\.(mp3|wav)$/.test(n));
      res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(list));
    });
    return;
  }
  const m = url.pathname.match(/^\/sounds\/([\w-]+\.(mp3|wav))$/);
  if (m) {
    fs.readFile(path.join(SOUNDS_DIR, m[1]), (err, data) => {
      if (err) return res.writeHead(404).end("not found");
      res.writeHead(200, { "Content-Type": m[2] === "mp3" ? "audio/mpeg" : "audio/wav" }).end(data);
    });
    return;
  }

  const file = url.pathname === "/" ? "index.html" : null;
  if (!file) {
    res.writeHead(404).end("not found");
    return;
  }
  fs.readFile(path.join(PUBLIC_DIR, file), (err, data) => {
    if (err) return res.writeHead(500).end("error");
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }).end(data);
  });
});

const wss = new WebSocketServer({ server, path: "/ws", maxPayload: 4096 });

wss.on("connection", (ws, req) => {
  const url = new URL(req.url, "http://x");
  const role = url.searchParams.get("role");
  const code = (url.searchParams.get("room") || "").toUpperCase();

  if (!["sender", "receiver"].includes(role) || !ROOM_RE.test(code)) {
    ws.close(1008, "bad role or room");
    return;
  }

  const room = getRoom(code);
  const set = role === "sender" ? room.senders : room.receivers;
  set.add(ws);
  broadcastStatus(room);

  // simple rate limit: 30 messages per second per sender
  let windowStart = Date.now();
  let count = 0;

  ws.isAlive = true;
  ws.on("pong", () => (ws.isAlive = true));

  ws.on("message", (raw) => {
    if (role !== "sender") return; // receivers only listen
    const now = Date.now();
    if (now - windowStart > 1000) { windowStart = now; count = 0; }
    if (++count > 30) return;

    let msg;
    try { msg = JSON.parse(raw); } catch { return; }

    let out;
    if (msg.type === "click") out = { type: "click" };
    else if (msg.type === "text" && typeof msg.text === "string") out = { type: "text", text: msg.text.slice(0, MAX_TEXT) };
    else if (msg.type === "clear") out = { type: "clear" };
    else return;

    for (const r of room.receivers) send(r, out);
  });

  ws.on("close", () => {
    set.delete(ws);
    if (room.senders.size === 0 && room.receivers.size === 0) rooms.delete(code);
    else broadcastStatus(room);
  });
});

// drop dead connections (e.g. laptop went to sleep)
setInterval(() => {
  for (const ws of wss.clients) {
    if (!ws.isAlive) { ws.terminate(); continue; }
    ws.isAlive = false;
    ws.ping();
  }
}, 30000);

server.listen(PORT, () => console.log(`clicker relay listening on http://localhost:${PORT}`));
