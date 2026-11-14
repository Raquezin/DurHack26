const logEl = document.getElementById("log");
const imgs = {1: document.getElementById("camera"), 2: document.getElementById("depth")};
const shown = new Set(["hazard", "guidance_text", "utterance", "geometry"]);

function addLine(event) {
  const line = document.createElement("div");
  line.className = "event " + event.type;
  if (event.type === "hazard") {
    line.textContent = `hazard ${event.level} ${event.bearing} ${event.distance_m.toFixed(2)}m`;
  } else if (event.type === "guidance_text") {
    line.textContent = `guidance ${event.delta}`;
  } else if (event.type === "utterance") {
    line.textContent = `utterance ${event.outcome} "${event.text}" (${event.priority})`;
  } else {
    line.textContent = `geometry frame ${event.frame_id} age ${event.age_ms.toFixed(0)}ms`;
  }
  logEl.prepend(line);
  while (logEl.children.length > 100) logEl.lastChild.remove();
}

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = async (message) => {
    if (typeof message.data === "string") {
      const event = JSON.parse(message.data);
      if (shown.has(event.type)) addLine(event);
      return;
    }
    const bytes = new Uint8Array(message.data);
    const kind = bytes[0];
    const jpeg = bytes.slice(9);
    const blob = new Blob([jpeg], {type: "image/jpeg"});
    const img = imgs[kind];
    if (img) {
      if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
      img.src = URL.createObjectURL(blob);
    }
  };
  ws.onclose = () => setTimeout(connect, 1000);
}
connect();
