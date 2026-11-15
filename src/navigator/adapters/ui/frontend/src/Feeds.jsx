import { useCallback, useRef, useState } from "react";

import { Hazard } from "./Hazard.jsx";
import { createMotion } from "./motion.js";
import { Route } from "./Route.jsx";
import { Tags } from "./Tags.jsx";

const KIND_CAMERA = 1;
const KIND_DEPTH = 2;

export function useFeeds() {
  const camera = useRef(null);
  const depth = useRef(null);
  const newest = useRef({ [KIND_CAMERA]: -1n, [KIND_DEPTH]: -1n });
  const painting = useRef({ [KIND_CAMERA]: false, [KIND_DEPTH]: false });
  const pending = useRef({ [KIND_CAMERA]: null, [KIND_DEPTH]: null });
  const [ratio, setRatio] = useState(null);
  const [motion] = useState(createMotion);

  const draw = useCallback(
    async (kind, frameId, jpeg) => {
      const bitmap = await createImageBitmap(
        new Blob([jpeg], { type: "image/jpeg" }),
      );
      const canvas = kind === KIND_CAMERA ? camera.current : depth.current;
      if (canvas && frameId >= newest.current[kind]) {
        newest.current[kind] = frameId;
        if (canvas.width !== bitmap.width) canvas.width = bitmap.width;
        if (canvas.height !== bitmap.height) canvas.height = bitmap.height;
        canvas.getContext("2d").drawImage(bitmap, 0, 0);
        if (kind === KIND_CAMERA) {
          setRatio(bitmap.width / bitmap.height);
          motion.observe(bitmap, Number(frameId));
        }
      }
      bitmap.close();
    },
    [motion],
  );

  const onPreview = useCallback(
    async (kind, frameId, jpeg) => {
      if (kind !== KIND_CAMERA && kind !== KIND_DEPTH) return;
      if (painting.current[kind]) {
        const held = pending.current[kind];
        if (!held || frameId >= held.frameId)
          pending.current[kind] = { frameId, jpeg };
        return;
      }
      painting.current[kind] = true;
      try {
        await draw(kind, frameId, jpeg);
      } finally {
        painting.current[kind] = false;
      }
      const next = pending.current[kind];
      pending.current[kind] = null;
      if (next) onPreview(kind, next.frameId, next.jpeg);
    },
    [draw],
  );

  return { camera, depth, ratio, motion, onPreview };
}

export function Feeds({ feeds, route, hazard, tags, link }) {
  return (
    <section
      className="feeds"
      style={feeds.ratio ? { "--ratio": feeds.ratio } : undefined}
    >
      <figure>
        <div className="picture">
          <canvas ref={feeds.camera} aria-label="camera" />
          <Hazard hazard={hazard} />
        </div>
        <figcaption>
          <span>Camera</span>
          <span className="link" data-state={link}>
            {link}
          </span>
        </figcaption>
      </figure>
      <figure>
        <div className="picture">
          <canvas ref={feeds.depth} aria-label="depth" />
          <Tags tags={tags} motion={feeds.motion} />
          <canvas ref={route.overlay} className="path" aria-label="path on depth" />
        </div>
        <figcaption>Depth + SAM + Path</figcaption>
      </figure>
      <Route route={route} />
    </section>
  );
}
