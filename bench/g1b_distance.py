import argparse
import math
import statistics

from navigator.adapters.camera.webcam import WebcamFrameSource
from navigator.adapters.clock.system import SystemClock
from navigator.adapters.perception.gpu import GpuScenePerception
from navigator.bootstrap.config import Settings

BOUND = 0.15


def _ahead(geometry, row):
    index = row * geometry.cols + geometry.cols // 2
    return geometry.distances_m[index], geometry.valid[index]


def measure(camera, perception, frames, row):
    values, last = [], -1
    for _ in range(frames):
        frame = camera.next_frame(last, 1.0)
        if frame is None:
            continue
        last = frame.frame_id
        distance, valid = _ahead(perception.perceive(frame, False).geometry, row)
        if valid and not math.isinf(distance):
            values.append(distance)
    if not values:
        raise SystemExit("ahead zone never valid within 10 m; check the camera")
    return statistics.median(values), min(values), max(values)


def main():
    s = Settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--distances", type=float, nargs="+", default=[1.0, 2.0, 3.0])
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--row", type=int, default=1)
    parser.add_argument("--long-side", type=int, default=s.input_long_side)
    parser.add_argument("--hfov", type=float, default=s.hfov_deg)
    parser.add_argument("--scale", type=float, default=s.scale)
    args = parser.parse_args()
    clock = SystemClock()
    camera = WebcamFrameSource(
        clock=clock,
        device=s.camera_device,
        width=s.camera_width,
        height=s.camera_height,
        fps=s.camera_fps,
        fourcc=s.camera_fourcc,
    )
    perception = GpuScenePerception(
        clock=clock,
        model=s.perception_model,
        input_long_side=args.long_side,
        rows=s.grid_rows,
        cols=s.grid_cols,
        horizontal_fov_deg=args.hfov,
        scale=args.scale,
        mount_height_m=s.mount_height_m,
        pitch_deg=s.pitch_deg,
    )
    results = []
    with camera, perception:
        perception.warm_up()
        for truth in args.distances:
            input(f"Face a wall {truth:.2f} m away (tape to the lens), then press Enter ")
            median, low, high = measure(camera, perception, args.frames, args.row)
            error = (median - truth) / truth
            results.append((truth, median, error))
            print(f"  measured {median:.3f} m (min {low:.3f}, max {high:.3f}), error {error:+.1%}")
    print("| tape m | measured m | error |")
    print("| --- | --- | --- |")
    for truth, median, error in results:
        print(f"| {truth:.2f} | {median:.3f} | {error:+.1%} |")
    worst = max(abs(e) for _, _, e in results)
    fit = statistics.median(t / m for t, m, _ in results)
    print(f"worst error {worst:.1%} ({'pass' if worst <= BOUND else 'fail'} at {BOUND:.0%}); scale that fits: {fit * args.scale:.3f}")


if __name__ == "__main__":
    main()
