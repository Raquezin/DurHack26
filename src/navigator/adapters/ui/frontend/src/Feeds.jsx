import { useCallback, useRef } from "react";

const KIND_CAMERA = 1;
const KIND_DEPTH = 2;

export function usePreviews() {
  const camera = useRef(null);
  const depth = useRef(null);
  const newest = useRef({ [KIND_CAMERA]: -1n, [KIND_DEPTH]: -1n });

  const show = useCallback((kind, frameId, jpeg) => {
    const image = kind === KIND_CAMERA ? camera.current : kind === KIND_DEPTH ? depth.current : null;
    if (!image || frameId < newest.current[kind]) return;
    newest.current[kind] = frameId;
    const previous = image.src;
    image.src = URL.createObjectURL(new Blob([jpeg], { type: "image/jpeg" }));
    if (previous.startsWith("blob:")) URL.revokeObjectURL(previous);
  }, []);

  return { camera, depth, show };
}

export function Feeds({ camera, depth }) {
  return (
    <section className="feeds">
      <figure>
        <img ref={camera} alt="camera" decoding="async" />
        <figcaption>Camera</figcaption>
      </figure>
      <figure>
        <img ref={depth} alt="depth" decoding="async" />
        <figcaption>Depth</figcaption>
      </figure>
    </section>
  );
}
