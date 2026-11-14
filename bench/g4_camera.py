import argparse
import random
import threading

import cv2
import numpy as np

from navigator.adapters.camera.webcam import WebcamFrameSource
from navigator.adapters.clock.system import SystemClock

MODES = (
    ("MJPG", 640, 480),
    ("MJPG", 1280, 720),
    ("MJPG", 1920, 1080),
    ("YUYV", 640, 480),
)
SETTLE_FRAMES = 15
WINDOW = "g4"


def _source(clock, device, fourcc, width, height, fps):
    return WebcamFrameSource(
        clock=clock, device=device, width=width, height=height, fps=fps, fourcc=fourcc
    )


def _stats(values_ms):
    p50, p95, p99 = np.percentile(values_ms, [50, 95, 99])
    return p50, p95, p99


def intervals(device, fps, seconds):
    clock = SystemClock()
    print("| format | size | frames | interval p50 ms | p95 | p99 | jitter p99 ms | skipped |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for fourcc, width, height in MODES:
        with _source(clock, device, fourcc, width, height, fps) as camera:
            stamps, ids, last = [], [], -1
            end_ns = clock.now_ns() + int((seconds + 1) * 1e9)
            while clock.now_ns() < end_ns:
                frame = camera.next_frame(last, 1.0)
                if frame is None:
                    break
                last = frame.frame_id
                stamps.append(frame.t_capture_ns)
                ids.append(frame.frame_id)
                size = f"{frame.width}x{frame.height}"
        stamps, ids = stamps[SETTLE_FRAMES:], ids[SETTLE_FRAMES:]
        gaps = np.diff(stamps) / 1e6
        p50, p95, p99 = _stats(gaps)
        jitter = np.percentile(np.abs(gaps - p50), 99)
        skipped = int(np.sum(np.diff(ids) - 1))
        print(
            f"| {fourcc} | {size} | {len(stamps)} | {p50:.2f} | {p95:.2f} | {p99:.2f} | {jitter:.2f} | {skipped} |"
        )


def _collect(camera, stop, samples):
    last = -1
    while not stop.is_set():
        frame = camera.next_frame(last, 0.5)
        if frame is None:
            continue
        last = frame.frame_id
        image = np.frombuffer(frame.pixels, np.uint8).reshape(frame.height, frame.width, 3)
        h, w = frame.height // 4, frame.width // 4
        samples.append((frame.t_capture_ns, float(image[h:-h, w:-w].mean())))


def _delays(flashes, samples):
    stamps = np.array([t for t, _ in samples])
    levels = np.array([b for _, b in samples])
    settled = {True: [], False: []}
    for (t0, white), (t1, _) in zip(flashes, flashes[1:]):
        half = (t0 + t1) // 2
        settled[white].extend(levels[(stamps > half) & (stamps < t1)])
    threshold = (np.median(settled[True]) + np.median(settled[False])) / 2
    delays = []
    for t_flash, white in flashes[1:]:
        after = stamps > t_flash
        crossed = after & ((levels > threshold) == white)
        if crossed.any():
            delays.append((stamps[np.argmax(crossed)] - t_flash) / 1e6)
    return threshold, np.median(settled[True]), np.median(settled[False]), delays


def glass(device, fourcc, width, height, fps, flashes_n):
    clock = SystemClock()
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    planes = {
        white: np.full((540, 960, 3), 255 if white else 0, np.uint8)
        for white in (True, False)
    }
    samples, flashes, stop = [], [], threading.Event()
    with _source(clock, device, fourcc, width, height, fps) as camera:
        collector = threading.Thread(target=_collect, args=(camera, stop, samples))
        collector.start()
        cv2.imshow(WINDOW, planes[False])
        cv2.waitKey(1500)
        for index in range(flashes_n):
            white = index % 2 == 0
            cv2.imshow(WINDOW, planes[white])
            cv2.waitKey(1)
            flashes.append((clock.now_ns(), white))
            cv2.waitKey(int(500 + random.random() * 300))
        flashes.append((clock.now_ns(), None))
        stop.set()
        collector.join()
    cv2.destroyAllWindows()
    threshold, white_level, black_level, delays = _delays(flashes, samples)
    print(f"{fourcc} {width}x{height}: levels white {white_level:.1f} black {black_level:.1f} threshold {threshold:.1f}")
    if len(delays) < flashes_n // 2:
        print(f"only {len(delays)} of {flashes_n - 1} flashes detected; is the camera facing the screen?")
        return
    p50, p95, p99 = _stats(delays)
    print(
        f"screen-to-frame over {len(delays)} flashes: p50 {p50:.1f} ms, p95 {p95:.1f} ms, p99 {p99:.1f} ms, min {min(delays):.1f} ms (includes display latency)"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--glass", action="store_true")
    parser.add_argument("--fourcc", default="MJPG")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--flashes", type=int, default=40)
    args = parser.parse_args()
    if args.glass:
        glass(args.device, args.fourcc, args.width, args.height, args.fps, args.flashes)
    else:
        intervals(args.device, args.fps, args.seconds)


if __name__ == "__main__":
    main()
