const WIDTH = 64;
const REACH = 0.35;
const CLEARLY_BETTER = 0.9;
const REMEMBERED_FRAMES = 240;

function difference(previous, current, width, height, dx, dy) {
  const left = Math.max(0, -dx);
  const right = Math.min(width, width - dx);
  const top = Math.max(0, -dy);
  const bottom = Math.min(height, height - dy);
  let sum = 0;
  for (let y = top; y < bottom; y += 1) {
    const row = y * width;
    const shifted = (y + dy) * width + dx;
    for (let x = left; x < right; x += 1)
      sum += Math.abs(current[shifted + x] - previous[row + x]);
  }
  return sum / ((right - left) * (bottom - top));
}

function refine(before, best, after) {
  const slope = Math.max(before, after) - best;
  return slope > 0 ? (0.5 * (before - after)) / slope : 0;
}

function halved(grey, width, height) {
  const halfWidth = width >> 1;
  const halfHeight = height >> 1;
  const half = new Float32Array(halfWidth * halfHeight);
  for (let y = 0; y < halfHeight; y += 1)
    for (let x = 0; x < halfWidth; x += 1) {
      const corner = 2 * y * width + 2 * x;
      half[y * halfWidth + x] =
        (grey[corner] +
          grey[corner + 1] +
          grey[corner + width] +
          grey[corner + width + 1]) /
        4;
    }
  return [half, halfWidth, halfHeight];
}

function closest(score, aroundX, aroundY, reachX, reachY) {
  let found = [Infinity, aroundX, aroundY];
  for (let dy = aroundY - reachY; dy <= aroundY + reachY; dy += 1)
    for (let dx = aroundX - reachX; dx <= aroundX + reachX; dx += 1) {
      const value = score(dx, dy);
      if (value < found[0]) found = [value, dx, dy];
    }
  return found;
}

export function shiftBetween(previous, current, width, height) {
  const [coarsePrevious, coarseWidth, coarseHeight] = halved(
    previous,
    width,
    height,
  );
  const [coarseCurrent] = halved(current, width, height);
  const [, coarseX, coarseY] = closest(
    (dx, dy) =>
      difference(
        coarsePrevious,
        coarseCurrent,
        coarseWidth,
        coarseHeight,
        dx,
        dy,
      ),
    0,
    0,
    Math.round(coarseWidth * REACH),
    Math.round(coarseHeight * REACH),
  );
  const score = (dx, dy) =>
    difference(previous, current, width, height, dx, dy);
  const [best, bestX, bestY] = closest(score, 2 * coarseX, 2 * coarseY, 1, 1);
  if (best > score(0, 0) * CLEARLY_BETTER) return [0, 0];
  const fineX = refine(score(bestX - 1, bestY), best, score(bestX + 1, bestY));
  const fineY = refine(score(bestX, bestY - 1), best, score(bestX, bestY + 1));
  return [(bestX + fineX) / width, (bestY + fineY) / height];
}

function luminance(pixels, count) {
  const grey = new Float32Array(count);
  for (let index = 0; index < count; index += 1)
    grey[index] =
      0.299 * pixels[index * 4] +
      0.587 * pixels[index * 4 + 1] +
      0.114 * pixels[index * 4 + 2];
  return grey;
}

export function createMotion() {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  const travelled = new Map();
  let previous = null;
  let total = [0, 0];

  return {
    observe(image, frameId) {
      const height = Math.round(
        (WIDTH * image.height) / image.width,
      );
      if (canvas.width !== WIDTH || canvas.height !== height) {
        canvas.width = WIDTH;
        canvas.height = height;
        previous = null;
      }
      context.drawImage(image, 0, 0, WIDTH, height);
      const current = luminance(
        context.getImageData(0, 0, WIDTH, height).data,
        WIDTH * height,
      );
      if (previous) {
        const [dx, dy] = shiftBetween(previous, current, WIDTH, height);
        total = [total[0] + dx, total[1] + dy];
      }
      previous = current;
      travelled.set(frameId, total);
      if (travelled.size > REMEMBERED_FRAMES)
        travelled.delete(travelled.keys().next().value);
    },
    at(frameId) {
      let found = null;
      for (const [seenFrame, position] of travelled) {
        if (seenFrame > frameId) break;
        found = position;
      }
      return found ?? total;
    },
    now() {
      return total;
    },
  };
}
