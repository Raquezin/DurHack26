let audioCtx = null;
let nextTime = 0;
let playing = [];

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
