import { useEffect, useRef, useState } from "react";

import {
  blend,
  bounds,
  follow,
  pair,
  resample,
  turned,
  turnOnto,
} from "./shapes.js";

const CROSSING = /crossing|crosswalk|zebra/;
const TRAFFIC =
  /\b(road|street|traffic|car|bus|truck|vehicle|bike|bicycle|motorcycle|scooter|tram)s?\b/;
const HUES = [205, 150, 280, 35, 325, 95, 250, 180];
const MORPH_MS = 250;
const MISSED_MS = 700;
const SETTLE_MS = 300;
const SMOOTHING = 0.45;

export function tagLevel(label) {
  if (CROSSING.test(label)) return "stop";
  if (TRAFFIC.test(label)) return "caution";
  return "plain";
}

function hue(label) {
  let sum = 0;
  for (const character of label) sum += character.codePointAt(0);
  return HUES[sum % HUES.length];
}

function since([seenX, seenY], [x, y]) {
  return [x - seenX, y - seenY];
}

function pointsNow(track, now, travelled) {
  const progress = Math.min(1, (now - track.startedAt) / MORPH_MS);
  return blend(
    follow(track.from, since(track.fromSeen, travelled)),
    follow(track.to, since(track.toSeen, travelled)),
    progress,
  );
}

function area({ left, right, top, bottom }) {
  return (right - left) * (bottom - top);
}

function paint(track, elements, now, travelled) {
  const points = pointsNow(track, now, travelled);
  const { left, right, top, bottom } = bounds(points);
  elements.polygon.setAttribute(
    "points",
    points.map((point) => point.join(",")).join(" "),
  );
  elements.label.style.left = `${((left + right) / 2) * 100}%`;
  elements.label.style.top = `${((top + bottom) / 2) * 100}%`;
  const opacity = track.gone || now - track.bornAt < SETTLE_MS ? 0 : 1;
  elements.polygon.style.opacity = opacity;
  elements.label.style.opacity = opacity;
}

function useTracks(tags, motion) {
  const [tracks, setTracks] = useState([]);
  const nextId = useRef(0);

  useEffect(() => {
    const now = performance.now();
    const travelled = motion.now();
    const seen = motion.at(tags.frameId);
    const shapes = tags.list
      .filter((tag) => tag.outline.length >= 3)
      .map((tag) => {
        const points = resample(tag.outline);
        return {
          label: tag.label,
          points,
          shown: follow(points, since(seen, travelled)),
        };
      });
    setTracks((previous) => {
      const alive = previous.filter((track) => !track.gone);
      const trackOf = pair(
        alive.map((track) => ({
          label: track.label,
          shown: pointsNow(track, now, travelled),
        })),
        shapes,
      );
      const kept = new Set(trackOf.values());
      const moved = shapes.map((shape, index) => {
        const track = alive[trackOf.get(index)];
        if (!track) {
          nextId.current += 1;
          return {
            id: nextId.current,
            label: shape.label,
            from: shape.points,
            fromSeen: seen,
            to: shape.points,
            toSeen: seen,
            startedAt: now,
            matchedAt: now,
            bornAt: now,
            settled: false,
          };
        }
        const from = pointsNow(track, now, travelled);
        return {
          ...track,
          from,
          fromSeen: travelled,
          to: blend(
            from,
            turned(shape.shown, turnOnto(shape.shown, from)),
            SMOOTHING,
          ),
          toSeen: travelled,
          startedAt: now,
          matchedAt: now,
          settled: true,
        };
      });
      const missed = alive
        .filter((_, index) => !kept.has(index))
        .map((track) => ({
          ...track,
          gone: !track.settled || now - track.matchedAt > MISSED_MS,
        }));
      return [...moved, ...missed].sort(
        (a, b) => area(bounds(b.to)) - area(bounds(a.to)),
      );
    });
  }, [tags, motion]);

  return tracks;
}

export function Tags({ tags, motion }) {
  const tracks = useTracks(tags, motion);
  const elements = useRef(new Map());
  const loose = tags.list.filter((tag) => tag.outline.length < 3);

  useEffect(() => {
    let frame = 0;
    const step = () => {
      const now = performance.now();
      const travelled = motion.now();
      for (const track of tracks) {
        const found = elements.current.get(track.id);
        if (found?.polygon && found?.label) paint(track, found, now, travelled);
      }
      if (tracks.length > 0) frame = requestAnimationFrame(step);
    };
    step();
    return () => cancelAnimationFrame(frame);
  }, [tracks, motion]);

  const remember = (id, part) => (node) => {
    const found = elements.current.get(id) ?? {};
    if (node) elements.current.set(id, { ...found, [part]: node });
    else elements.current.delete(id);
  };

  return (
    <>
      <svg
        className="shapes"
        viewBox="0 0 1 1"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {tracks.map((track) => (
          <polygon
            key={track.id}
            ref={remember(track.id, "polygon")}
            data-level={tagLevel(track.label)}
            style={{ "--hue": hue(track.label) }}
          />
        ))}
      </svg>
      {tracks.map((track) => (
        <span
          key={track.id}
          ref={remember(track.id, "label")}
          className="shape-label"
          data-level={tagLevel(track.label)}
          style={{ "--hue": hue(track.label) }}
        >
          {track.label}
        </span>
      ))}
      {loose.length > 0 && (
        <p className="tags" aria-label="Elsewhere in the scene">
          {loose.map((tag) => (
            <span
              key={tag.label}
              className="tag"
              data-level={tagLevel(tag.label)}
            >
              {tag.label}
            </span>
          ))}
        </p>
      )}
    </>
  );
}
