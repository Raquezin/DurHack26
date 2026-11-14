const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const ctx2d = canvas.getContext("2d");
const startButton = document.getElementById("start");
const rttEl = document.getElementById("rtt");
const fpsEl = document.getElementById("fps");
const audioEl = document.getElementById("audio");
const soundButton = document.getElementById("sound");

let ws = null;
let audioCtx = null;
let nextTime = 0;
let playing = [];
let wakeLock = null;
let sentFrames = 0;
let lastStats = 0;
let clips = 0;
let lastError = "";

function report(message) {
  lastError = String(message);
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({type: "log", message: lastError}));
}

window.addEventListener("error", (event) => report(`error ${event.message}`));
window.addEventListener("unhandledrejection", (event) => report(`rejection ${event.reason}`));

function unlockAudio() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (navigator.audioSession) {
    try { navigator.audioSession.type = "playback"; } catch (e) {}
  }
  audioCtx.resume();
  const beep = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  gain.gain.value = 0.2;
  beep.frequency.value = 880;
  beep.connect(gain).connect(audioCtx.destination);
  beep.start();
  beep.stop(audioCtx.currentTime + 0.2);
}

function schedulePcm(data) {
  const int16 = new Int16Array(data.slice(1, data.byteLength - ((data.byteLength - 1) % 2)));
  if (audioCtx.state !== "running") audioCtx.resume();
  const floats = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) floats[i] = int16[i] / 32768;
  const buffer = audioCtx.createBuffer(1, floats.length, 24000);
  buffer.copyToChannel(floats, 0);
  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(audioCtx.destination);
  nextTime = Math.max(audioCtx.currentTime, nextTime);
  source.start(nextTime);
  nextTime += buffer.duration;
  playing.push(source);
  source.onended = () => {
    playing = playing.filter((s) => s !== source);
  };
}

function interruptAudio() {
  for (const source of playing) {
    try { source.stop(); } catch (e) {}
  }
  playing = [];
  nextTime = 0;
}

function connect() {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${scheme}//${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = (message) => {
    if (typeof message.data === "string") {
      const payload = JSON.parse(message.data);
      if (payload.type === "pong") {
        rttEl.textContent = `rtt ${Math.round(performance.now() - payload.t)} ms`;
      } else if (payload.type === "interrupt") {
        interruptAudio();
      }
      return;
    }
    const bytes = new Uint8Array(message.data);
    if (bytes[0] !== 2) return;
    clips++;
    if (!audioCtx) return report("pcm received before audio unlocked");
    try { schedulePcm(message.data); } catch (e) { report(`pcm ${e}`); }
  };
  ws.onclose = () => setTimeout(connect, 1000);
}

function sendFrame() {
  if (!ws || ws.readyState !== 1 || ws.bufferedAmount !== 0) return;
  if (!video.videoWidth) return;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  ctx2d.drawImage(video, 0, 0);
  canvas.toBlob((blob) => {
    if (!blob || !ws || ws.readyState !== 1 || ws.bufferedAmount !== 0) return;
    blob.arrayBuffer().then((buffer) => {
      const head = new Uint8Array(1 + buffer.byteLength);
      head[0] = 1;
      head.set(new Uint8Array(buffer), 1);
      ws.send(head);
      sentFrames++;
    });
  }, "image/jpeg", 0.7);
}

function frameLoop() {
  sendFrame();
  if (video.requestVideoFrameCallback) {
    video.requestVideoFrameCallback(frameLoop);
  } else {
    requestAnimationFrame(frameLoop);
  }
}

async function requestWakeLock() {
  try {
    if ("wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen");
  } catch (e) {}
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") requestWakeLock();
});

setInterval(() => {
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({type: "ping", t: performance.now()}));
  }
}, 1000);

setInterval(() => {
  const now = performance.now();
  const fps = sentFrames * 1000 / (now - lastStats || 1);
  fpsEl.textContent = `fps ${fps.toFixed(0)}`;
  const audioState = audioCtx ? audioCtx.state : "none";
  audioEl.textContent = `audio ${audioState} clips ${clips}`;
  if (ws && ws.readyState === 1) {
    const rtt = parseFloat(rttEl.textContent.split(" ")[1]) || 0;
    ws.send(JSON.stringify({type: "stats", rtt_ms: rtt, fps, audio: audioState, clips, error: lastError}));
  }
  sentFrames = 0;
  lastStats = now;
}, 2000);

startButton.onclick = async () => {
  unlockAudio();
  const stream = await navigator.mediaDevices.getUserMedia({
    video: {facingMode: "environment", width: 640, height: 480},
    audio: false,
  });
  video.srcObject = stream;
  await video.play();
  await requestWakeLock();
  connect();
  frameLoop();
  lastStats = performance.now();
  startButton.hidden = true;
};

soundButton.onclick = () => unlockAudio();
