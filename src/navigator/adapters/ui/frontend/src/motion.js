const WALK_PHRASES = new Set([
  "Keep going straight.",
  "Path is clear.",
  "Move a little left.",
  "Move a little right.",
  "Turn left.",
  "Turn right.",
]);

const HALT_PHRASES = new Set([
  "Stop.",
  "Careful, obstacle ahead.",
  "Obstacle on your left.",
  "Obstacle on your right.",
  "Slow down.",
  "Door ahead.",
]);

// jumpSpin 0: a full spin shows the bare side of the body, where the fur is lost.
const POSTURES = {
  look: { state: "default", turn: 1, jumpEvery: 8, speed: 1, interactive: true, jumpSpin: 0 },
  halt: { state: "default", turn: 1, jumpEvery: 0, speed: 0.8, interactive: false, jumpSpin: 0 },
  walk: { state: "working", turn: 1, jumpEvery: 8, speed: 1.1, interactive: false, jumpSpin: 0 },
};

export function postureForPhrase(text) {
  if (WALK_PHRASES.has(text)) return "walk";
  if (HALT_PHRASES.has(text)) return "halt";
  return "look";
}

export function botMotion(posture, hazardActive) {
  return POSTURES[hazardActive ? "halt" : posture];
}
