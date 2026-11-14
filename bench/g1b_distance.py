import argparse
import math
import statistics

from rig import add_arguments, rig, settings_from

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--distances", type=float, nargs="+", default=[1.0, 2.0, 3.0])
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--row", type=int, default=1)
    add_arguments(parser)
    args = parser.parse_args()
    settings = settings_from(args)
    results = []
    with rig(settings) as (_, camera, perception):
        for truth in args.distances:
            input(f"Face a wall {truth:.2f} m away (tape to the lens), then press Enter ")
            median, low, high = measure(camera, perception, args.frames, args.row)
            error = (median - truth) / truth
            results.append((truth, median, error))
            print(f"  measured {median:.3f} m (min {low:.3f}, max {high:.3f}), error {error:+.1%}")
    print(f"camera {args.camera}, long side {settings.input_long_side}, hfov {settings.hfov_deg}, scale {settings.scale}")
    print("| tape m | measured m | error |")
    print("| --- | --- | --- |")
    for truth, median, error in results:
        print(f"| {truth:.2f} | {median:.3f} | {error:+.1%} |")
    worst = max(abs(e) for _, _, e in results)
    fit = statistics.median(t / m for t, m, _ in results)
    print(f"worst error {worst:.1%} ({'pass' if worst <= BOUND else 'fail'} at {BOUND:.0%}); scale that fits: {fit * settings.scale:.3f}")


if __name__ == "__main__":
    main()
