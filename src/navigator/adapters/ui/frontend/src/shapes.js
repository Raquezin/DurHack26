const POINTS = 40;
const MATCH_DISTANCE = 0.2;
const EDGE = 0.01;

function signedArea(outline) {
  return outline.reduce((sum, [x, y], index) => {
    const [nextX, nextY] = outline[(index + 1) % outline.length];
    return sum + x * nextY - nextX * y;
  }, 0);
}

function fromTopClockwise(outline) {
  const ring = signedArea(outline) < 0 ? [...outline].reverse() : outline;
  const top = ring.reduce(
    (best, [x, y], index) =>
      y < ring[best][1] || (y === ring[best][1] && x < ring[best][0])
        ? index
        : best,
    0,
  );
  return [...ring.slice(top), ...ring.slice(0, top)];
}

export function resample(outline) {
  const ring = fromTopClockwise(outline);
  const lengths = ring.map(([x, y], index) => {
    const [nextX, nextY] = ring[(index + 1) % ring.length];
    return Math.hypot(nextX - x, nextY - y);
  });
  const step = lengths.reduce((sum, length) => sum + length, 0) / POINTS;
  const points = [];
  let edge = 0;
  let walked = 0;
  for (let index = 0; index < POINTS; index += 1) {
    const target = index * step;
    while (edge < ring.length - 1 && walked + lengths[edge] < target) {
      walked += lengths[edge];
      edge += 1;
    }
    const along = lengths[edge] ? (target - walked) / lengths[edge] : 0;
    const [x, y] = ring[edge];
    const [nextX, nextY] = ring[(edge + 1) % ring.length];
    points.push([x + (nextX - x) * along, y + (nextY - y) * along]);
  }
  return points;
}

export function bounds(points) {
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  return {
    left: Math.min(...xs),
    right: Math.max(...xs),
    top: Math.min(...ys),
    bottom: Math.max(...ys),
  };
}

function centre(points) {
  const { left, right, top, bottom } = bounds(points);
  return [(left + right) / 2, (top + bottom) / 2];
}

function slide(position, distance) {
  if (position <= EDGE || position >= 1 - EDGE) return position;
  return Math.min(1, Math.max(0, position + distance));
}

export function follow(points, [dx, dy]) {
  return points.map(([x, y]) => [slide(x, dx), slide(y, dy)]);
}

export function blend(from, to, progress) {
  return from.map(([x, y], index) => [
    x + (to[index][0] - x) * progress,
    y + (to[index][1] - y) * progress,
  ]);
}

function apart(from, to, turn) {
  return from.reduce((sum, [x, y], index) => {
    const [toX, toY] = to[(index + turn) % to.length];
    return sum + Math.hypot(toX - x, toY - y);
  }, 0);
}

export function turnOnto(points, onto) {
  let turn = 0;
  let least = Infinity;
  for (let candidate = 0; candidate < points.length; candidate += 1) {
    const distance = apart(onto, points, candidate);
    if (distance < least) [least, turn] = [distance, candidate];
  }
  return turn;
}

export function turned(points, turn) {
  return [...points.slice(turn), ...points.slice(0, turn)];
}

export function pair(tracks, shapes) {
  const candidates = [];
  tracks.forEach((track, trackIndex) => {
    const [trackX, trackY] = centre(track.shown);
    shapes.forEach((shape, shapeIndex) => {
      if (shape.label !== track.label) return;
      const [x, y] = centre(shape.shown);
      const distance = Math.hypot(x - trackX, y - trackY);
      if (distance <= MATCH_DISTANCE)
        candidates.push({ distance, trackIndex, shapeIndex });
    });
  });
  candidates.sort((a, b) => a.distance - b.distance);
  const trackOf = new Map();
  const taken = new Set();
  for (const { trackIndex, shapeIndex } of candidates) {
    if (trackOf.has(shapeIndex) || taken.has(trackIndex)) continue;
    trackOf.set(shapeIndex, trackIndex);
    taken.add(trackIndex);
  }
  return trackOf;
}
