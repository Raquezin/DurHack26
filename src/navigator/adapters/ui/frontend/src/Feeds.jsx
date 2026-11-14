export function Feeds() {
  return (
    <section className="feeds">
      <figure>
        <img src="/static/demo-camera.jpg" alt="camera" decoding="async" />
        <figcaption>Camera</figcaption>
      </figure>
      <figure>
        <img src="/static/demo-depth.jpg" alt="depth" decoding="async" />
        <figcaption>Depth</figcaption>
      </figure>
    </section>
  );
}
