import { useCallback, useRef, useState } from "react";

import { Hazard } from "./Hazard.jsx";

const KIND_CAMERA = 1;
const KIND_DEPTH = 2;

export function useFeeds() {
  const camera = useRef(null);
  const depth = useRef(null);
  const newest = useRef({ [KIND_CAMERA]: -1n, [KIND_DEPTH]: -1n });
  const [cameraRatio, setCameraRatio] = useState(null);
  const [depthRatio, setDepthRatio] = useState(null);

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

  const onLoad = useCallback((kind, event) => {
    const ratio = event.target.naturalWidth / event.target.naturalHeight;
    (kind === KIND_CAMERA ? setCameraRatio : setDepthRatio)(ratio);
  }, []);

  return {
    camera,
    depth,
    cameraRatio,
    depthRatio,
    onPreview,
    onLoad,
  };
}

export function Feeds({ feeds, hazard, link }) {
  return (
    <section className="feeds">
      <figure>
        <div
          className="picture"
          style={feeds.cameraRatio && { "--ratio": feeds.cameraRatio }}
        >
          <div className="frame">
            <img
              ref={feeds.camera}
              alt="camera"
              decoding="async"
              onLoad={(event) => feeds.onLoad(KIND_CAMERA, event)}
            />
            <Hazard hazard={hazard} />
          </div>
        </div>
        <figcaption>
          <span>Camera</span>
          <span className="link" data-state={link}>
            {link}
          </span>
        </figcaption>
      </figure>
      <figure>
        <div
          className="picture"
          style={feeds.depthRatio && { "--ratio": feeds.depthRatio }}
        >
          <div className="frame">
            <img
              ref={feeds.depth}
              alt="depth"
              decoding="async"
              onLoad={(event) => feeds.onLoad(KIND_DEPTH, event)}
            />
          </div>
        </div>
        <figcaption>Depth</figcaption>
      </figure>
    </section>
  );
}
