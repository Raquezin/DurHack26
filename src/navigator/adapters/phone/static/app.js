const LONG_SIDE = 504;
const JPEG_QUALITY = 0.7;
const THIN_LONG_SIDE = 384;
const THIN_JPEG_QUALITY = 0.5;
const VIDEO_BITRATE = 700000;
const VIDEO_CODECS = ["avc1.42001f", "avc1.42e01f"];
const KEYFRAME_EVERY = 60;
const ENCODER_BACKLOG = 15;
const QUEUE_BUDGET_MS = 100;
const INITIAL_WINDOW = 2;
const KIND_JPEG = 1;
const KIND_PCM = 2;
const KIND_H264 = 3;
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const ctx2d = canvas.getContext("2d");
const startButton = document.getElementById("start");
const rttEl = document.getElementById("rtt");
const fpsEl = document.getElementById("fps");
const audioEl = document.getElementById("audio");
const soundButton = document.getElementById("sound");

let ws = null;
let wakeLock = null;
let sentFrames = 0;
let sentAt = [];
let minRtt = null;
let sendWindow = INITIAL_WINDOW;
let encoder = null;
let thinLink = false;
let skipped = 0;
let encoderCodec = "";
let encoderSize = "";
let needKey = true;
let fed = 0;
let emitted = 0;
let encodingJpeg = false;
let suspended = false;
let lastFrameCall = 0;
let lastStats = 0;
let clips = 0;
let lastError = "";

function report(message) {
  lastError = String(message);
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({type: "log", message: lastError}));
}

window.addEventListener("error", (event) => report(`error ${event.message}`));
window.addEventListener("unhandledrejection", (event) => report(`rejection ${event.reason}`));

function connect() {
  sentAt = [];
  minRtt = null;
  sendWindow = INITIAL_WINDOW;
  needKey = true;
  suspended = false;
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = ws = new WebSocket(`${scheme}//${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = (message) => {
    if (typeof message.data === "string") {
      const payload = JSON.parse(message.data);
      if (payload.type === "ack" || payload.type === "jpeg") {
        const full = sentAt.length >= sendWindow;
        const sent = sentAt.shift();
        if (payload.type === "jpeg") stopEncoder("server rejected video");
        if (sent === undefined) return;
        const rtt = performance.now() - sent;
        minRtt = minRtt === null ? rtt : Math.min(minRtt, rtt);
        if (rtt > minRtt + QUEUE_BUDGET_MS) sendWindow = Math.max(1, sendWindow - 1);
        else if (full) sendWindow++;
        rttEl.textContent = `rtt ${Math.round(rtt)} ms`;
      } else if (payload.type === "interrupt") {
        interruptAudio();
      }
      return;
    }
    const bytes = new Uint8Array(message.data);
    if (bytes[0] !== KIND_PCM) return;
    clips++;
    if (!audioCtx) return report("pcm received before audio unlocked");
    try { schedulePcm(message.data); } catch (e) { report(`pcm ${e}`); }
  };
  ws.onclose = () => {
    if (ws === socket && !suspended) setTimeout(connect, 1000);
  };
}

function frameSize() {
  const longSide = thinLink && !encoder ? THIN_LONG_SIDE : LONG_SIDE;
  const scale = Math.min(1, longSide / Math.max(video.videoWidth, video.videoHeight));
  return [2 * Math.round(video.videoWidth * scale / 2), 2 * Math.round(video.videoHeight * scale / 2)];
}

function transmit(message) {
  ws.send(message);
  sentAt.push(performance.now());
  sentFrames++;
}

function sendFrame() {
  lastFrameCall = performance.now();
  if (!ws || ws.readyState !== 1 || !video.videoWidth || encodingJpeg) return;
  if (sentAt.length >= sendWindow) {
    skipped++;
    return;
  }
  const [width, height] = frameSize();
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  ctx2d.drawImage(video, 0, 0, width, height);
  if (encoder && thinLink) encodeVideo(width, height);
  else encodeJpeg();
}

function encodeJpeg() {
  encodingJpeg = true;
  setTimeout(() => { encodingJpeg = false; }, 2000);
  const socket = ws;
  canvas.toBlob(async (blob) => {
    try {
      if (!blob || socket !== ws || socket.readyState !== 1) return;
      const message = new Uint8Array(1 + blob.size);
      message[0] = KIND_JPEG;
      message.set(new Uint8Array(await blob.arrayBuffer()), 1);
      if (socket === ws && socket.readyState === 1) transmit(message);
    } finally {
      encodingJpeg = false;
    }
  }, "image/jpeg", thinLink ? THIN_JPEG_QUALITY : JPEG_QUALITY);
}

function encoderConfig(codec, width, height) {
  return {codec, width, height, bitrate: VIDEO_BITRATE, framerate: 30, latencyMode: "realtime", avc: {format: "annexb"}};
}

async function startEncoder() {
  if (!("VideoEncoder" in window)) return;
  const [width, height] = frameSize();
  for (const codec of VIDEO_CODECS) {
    const config = encoderConfig(codec, width, height);
    try {
      if (!(await VideoEncoder.isConfigSupported(config)).supported) continue;
      const candidate = new VideoEncoder({output: sendChunk, error: (e) => stopEncoder(`encoder ${e.message}`)});
      candidate.configure(config);
      encoder = candidate;
      encoderCodec = codec;
      encoderSize = `${width}x${height}`;
      return;
    } catch (e) {
      report(`video ${codec} ${e}`);
    }
  }
}

function stopEncoder(reason) {
  report(reason);
  const stopped = encoder;
  encoder = null;
  if (stopped && stopped.state !== "closed") {
    try { stopped.close(); } catch (e) {}
  }
}

function encodeVideo(width, height) {
  const size = `${width}x${height}`;
  try {
    if (size !== encoderSize) {
      encoder.configure(encoderConfig(encoderCodec, width, height));
      encoderSize = size;
      needKey = true;
      fed = 0;
      emitted = 0;
    }
    const frame = new VideoFrame(canvas, {timestamp: Math.round(performance.now() * 1000)});
    encoder.encode(frame, {keyFrame: needKey || fed % KEYFRAME_EVERY === 0});
    frame.close();
  } catch (e) {
    return stopEncoder(`encode ${e}`);
  }
  needKey = false;
  fed++;
  if (fed - emitted > ENCODER_BACKLOG) stopEncoder("encoder stalled");
}

function sendChunk(chunk) {
  emitted++;
  if (!ws || ws.readyState !== 1) {
    needKey = true;
    return;
  }
  const message = new Uint8Array(1 + chunk.byteLength);
  message[0] = KIND_H264;
  chunk.copyTo(message.subarray(1));
  transmit(message);
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
  if (document.visibilityState === "visible") {
    requestWakeLock();
    if (!ws || ws.readyState >= 2) connect();
  } else {
    suspended = true;
    if (ws && ws.readyState === 1) ws.close();
  }
});

setInterval(() => {
  const now = performance.now();
  const fps = sentFrames * 1000 / (now - lastStats || 1);
  if (skipped > sentFrames) thinLink = true;
  const mode = !thinLink ? "jpeg" : encoder ? "h264" : "jpeg-small";
  fpsEl.textContent = `fps ${fps.toFixed(0)} ${mode}`;
  const audioState = audioCtx ? audioCtx.state : "none";
  audioEl.textContent = `audio ${audioState} clips ${clips}`;
  if (document.visibilityState === "visible" && video.videoWidth && ws && ws.readyState === 1 && now - lastFrameCall > 3000) frameLoop();
  if (ws && ws.readyState === 1) {
    const rtt = parseFloat(rttEl.textContent.split(" ")[1]) || 0;
    ws.send(JSON.stringify({type: "stats", rtt_ms: rtt, fps, audio: audioState, clips, video: mode, error: lastError}));
  }
  sentFrames = 0;
  skipped = 0;
  lastStats = now;
}, 2000);

startButton.onclick = async () => {
  unlockAudio();
  const stream = await navigator.mediaDevices.getUserMedia({
    video: {facingMode: "environment", width: 640, height: 480},
    audio: false,
  });
  video.srcObject = stream;
  const track = stream.getVideoTracks()[0];
  for (const event of ["mute", "unmute", "ended"]) {
    track.addEventListener(event, () => report(`camera ${event}`));
  }
  await video.play();
  startEncoder();
  await requestWakeLock();
  connect();
  frameLoop();
  lastStats = performance.now();
  startButton.hidden = true;
};

soundButton.onclick = () => unlockAudio();
