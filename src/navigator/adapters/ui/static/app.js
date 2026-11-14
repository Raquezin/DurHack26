const logEl = document.getElementById("log");
const label = document.getElementById("speech-label");
const line = document.getElementById("speech-line");
const link = document.getElementById("link");
const imgs = {
  1: document.getElementById("camera"),
  2: document.getElementById("depth"),
};
const seen = {1: -1n, 2: -1n};
const shown = new Set(["hazard", "guidance_text", "utterance"]);

let requestId = null;
let guidance = "";
let stopped = false;

window.addEventListener("pagehide", () => {
  stopped = true;
});

function addLine(event) {
  const row = document.createElement("div");
  row.className = "event " + event.type;
  if (event.type === "hazard") {
    row.textContent = `hazard ${event.level} ${event.bearing} ${Number(event.distance_m).toFixed(2)}m`;
  } else if (event.type === "guidance_text") {
    row.textContent = `guidance ${event.delta}`;
  } else if (event.type === "utterance") {
    row.textContent = `utterance ${event.outcome} "${event.text}" (${event.priority})`;
  }
  const top = logEl.firstElementChild;
  if (top && top.textContent === row.textContent) return;
  logEl.prepend(row);
  while (logEl.children.length > 16) logEl.lastChild.remove();
}

function onGuidance(event) {
  if (event.request_id !== requestId) {
    requestId = event.request_id;
    guidance = "";
  }
  guidance += event.delta;
  label.textContent = "Next";
  line.textContent = guidance || "…";
  if (event.final) guidance = "";
  addLine(event);
}

function onUtterance(event) {
  if (event.outcome === "spoken") {
    label.textContent = "Speaking";
    line.textContent = event.text;
  } else if (
    line.textContent === event.text &&
    event.outcome !== "dropped_repeat"
  ) {
    label.textContent = String(event.outcome).replaceAll("_", " ");
  }
  addLine(event);
}

function showPreview(bytes) {
  const kind = bytes[0];
  const img = imgs[kind];
  if (!img || bytes.length < 9) return;
  const frameId = new DataView(
    bytes.buffer,
    bytes.byteOffset,
    bytes.byteLength
  ).getBigUint64(1);
  if (frameId < seen[kind]) return;
  seen[kind] = frameId;
  const blob = new Blob([bytes.slice(9)], {type: "image/jpeg"});
  if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
  img.src = URL.createObjectURL(blob);
}

function connect() {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${scheme}//${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => {
    document.body.dataset.link = "live";
    link.textContent = "live";
  };
  ws.onmessage = (message) => {
    if (typeof message.data === "string") {
      let event;
      try {
        event = JSON.parse(message.data);
      } catch (err) {
        return;
      }
      if (event.type === "guidance_text") onGuidance(event);
      else if (event.type === "utterance") onUtterance(event);
      else if (shown.has(event.type)) addLine(event);
      return;
    }
    showPreview(new Uint8Array(message.data));
  };
  ws.onclose = () => {
    document.body.dataset.link = "offline";
    link.textContent = "offline";
    if (!stopped) setTimeout(connect, 400);
  };
}

connect();
