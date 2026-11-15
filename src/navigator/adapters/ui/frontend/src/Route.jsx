import { useCallback, useRef } from "react";

const SPAN_M = 3;
const DEPTH_M = 8;
const GRID_M = 2;
const PAD_PX = 14;
const FREE = "#fbfaf7";
const GRID = "#cfcbc1";
const INK = "#1c1b19";
const MUTED = "#7d7970";
const STOP = "#c4402f";

function fit(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.round(canvas.clientWidth * ratio);
  const height = Math.round(canvas.clientHeight * ratio);
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  return ratio;
}

function trace(context, points) {
  context.beginPath();
  points.forEach(([x, y], index) =>
    index ? context.lineTo(x, y) : context.moveTo(x, y),
  );
}

function dot(context, [x, y], radius, fill, stroke, width) {
  context.beginPath();
  context.arc(x, y, radius, 0, 2 * Math.PI);
  context.fillStyle = fill;
  context.fill();
  context.lineWidth = width;
  context.strokeStyle = stroke;
  context.stroke();
}

function obstacleText(route) {
  return `${route.label ?? "obstacle"} ${route.blocker[1].toFixed(1)} m`;
}

function drawOverlay(canvas, route) {
  const ratio = fit(canvas);
  const context = canvas.getContext("2d");
  const { width, height } = canvas;
  const pixel = ([u, v]) => [u * width, v * height];
  context.clearRect(0, 0, width, height);
  context.font = `${11 * ratio}px Geist, system-ui, sans-serif`;
  context.textBaseline = "middle";

  const line = route.picture_line.map(pixel);
  if (line.length >= 2) {
    context.lineJoin = "round";
    context.lineCap = "round";
    trace(context, line);
    context.lineWidth = 3 * ratio;
    context.strokeStyle = "rgb(28 27 25 / 0.55)";
    context.stroke();
    context.lineWidth = 1.5 * ratio;
    context.strokeStyle = FREE;
    context.stroke();
    dot(
      context,
      line[line.length - 1],
      2.5 * ratio,
      FREE,
      "rgb(28 27 25 / 0.55)",
      ratio,
    );
  }

  if (route.picture_blocker) {
    const [x, y] = pixel(route.picture_blocker);
    dot(context, [x, y], 5 * ratio, "rgb(196 64 47 / 0.18)", STOP, 1.5 * ratio);
    const text = obstacleText(route);
    const padX = 6 * ratio;
    const pillW = context.measureText(text).width + 2 * padX;
    const pillH = 16 * ratio;
    const gapX = 11 * ratio;
    const left = route.picture_blocker[0] > 0.5;
    let pillX = left ? x - gapX - pillW : x + gapX;
    let pillY = y - pillH / 2;
    pillX = Math.min(Math.max(pillX, 0), width - pillW);
    pillY = Math.min(Math.max(pillY, 0), height - pillH);
    context.beginPath();
    context.roundRect(pillX, pillY, pillW, pillH, pillH / 2);
    context.fillStyle = FREE;
    context.fill();
    context.fillStyle = STOP;
    context.textAlign = "left";
    context.fillText(text, pillX + padX, pillY + pillH / 2);
  }
}

export function drawRoute(canvas, route) {
  const ratio = fit(canvas);
  const context = canvas.getContext("2d");
  const { width, height } = canvas;
  const pad = PAD_PX * ratio;
  const scale = Math.min(
    (width - 2 * pad) / (2 * SPAN_M),
    (height - 2 * pad) / DEPTH_M,
  );
  const place = ([x, z]) => [width / 2 + x * scale, height - pad - z * scale];
  context.clearRect(0, 0, width, height);
  context.font = `${11 * ratio}px Geist, system-ui, sans-serif`;
  context.textBaseline = "middle";

  trace(context, [[0, 0], ...route.boundary].map(place));
  context.closePath();
  context.fillStyle = FREE;
  context.fill();

  context.lineWidth = ratio;
  context.strokeStyle = GRID;
  context.fillStyle = MUTED;
  context.textAlign = "left";
  for (let depth = GRID_M; depth <= DEPTH_M; depth += GRID_M) {
    const y = place([0, depth])[1];
    trace(context, [
      [pad + 28 * ratio, y],
      [width - pad, y],
    ]);
    context.stroke();
    context.fillText(`${depth} m`, pad, y);
  }

  const waypoints = route.waypoints.map(place);
  context.lineJoin = "round";
  context.lineCap = "round";
  context.lineWidth = 3 * ratio;
  context.strokeStyle = INK;
  trace(context, waypoints);
  context.stroke();
  waypoints.forEach((point, index) =>
    dot(context, point, (index ? 4.5 : 6.5) * ratio, INK, FREE, 2 * ratio),
  );

  if (route.blocker) {
    const [x, y] = place(route.blocker);
    dot(context, [x, y], 9 * ratio, "rgb(196 64 47 / 0.18)", STOP, 2.5 * ratio);
    const text = obstacleText(route);
    const onLeft = route.blocker[0] < 0;
    context.fillStyle = STOP;
    context.textAlign = onLeft ? "right" : "left";
    context.fillText(text, x + (onLeft ? -14 : 14) * ratio, y);
  }
}

export function useRoute() {
  const canvas = useRef(null);
  const overlay = useRef(null);
  const onRoute = useCallback((event) => {
    if (canvas.current) drawRoute(canvas.current, event);
    if (overlay.current) drawOverlay(overlay.current, event);
  }, []);
  return { canvas, overlay, onRoute };
}

export function Route({ route }) {
  return (
    <figure>
      <div className="picture">
        <canvas ref={route.canvas} aria-label="path" />
      </div>
      <figcaption>Path</figcaption>
    </figure>
  );
}
