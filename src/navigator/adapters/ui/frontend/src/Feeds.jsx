import { useCallback, useRef, useState } from "react";

import { Hazard } from "./Hazard.jsx";
import { Tags } from "./Tags.jsx";

const KIND_CAMERA = 1;
const KIND_DEPTH = 2;

export function useFeeds() {
  const camera = useRef(null);
  const depth = useRef(null);
  const newest = useRef({ [KIND_CAMERA]: -1n, [KIND_DEPTH]: -1n });
  const [ratio, setRatio] = useState(null);

  const onPreview = useCallback((kind, frameId, jpeg) => {
    const image =
      kind === KIND_CAMERA
        ? camera.current
        : kind === KIND_DEPTH
          ? depth.current
          : null;
    if (!image || frameId < newest.current[kind]) return;
    newest.current[kind] = frameId;
    const previous = image.src;
    image.src = URL.createObjectURL(
      new Blob([jpeg], { type: "image/jpeg" }),
    );
    if (previous.startsWith("blob:")) URL.revokeObjectURL(previous);
  }, []);

  // Both previews come from the same frame, so one ratio sizes both pictures.
  const onCameraLoad = useCallback((event) => {
    setRatio(event.target.naturalWidth / event.target.naturalHeight);
  }, []);

  return { camera, depth, ratio, onPreview, onCameraLoad };
}

export function Feeds({ feeds, hazard, tags, link }) {
  return (
    <section
      className="feeds"
      style={feeds.ratio ? { "--ratio": feeds.ratio } : undefined}
    >
      <figure>
        <div className="picture">
          <img
            ref={feeds.camera}
            alt="camera"
            decoding="async"
            onLoad={feeds.onCameraLoad}
          />
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
          <img ref={feeds.depth} alt="depth" decoding="async" />
          <Tags tags={tags} />
        </div>
        <figcaption>Depth</figcaption>
      </figure>
    </section>
  );
}
