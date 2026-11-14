import argparse
import subprocess

import numpy as np
import torch
from fastforks import depth

from navigator.adapters.camera.webcam import WebcamFrameSource
from navigator.adapters.clock.system import SystemClock
from navigator.adapters.perception.gpu import GpuScenePerception
from navigator.adapters.perception.zones import intrinsics
from navigator.bootstrap.config import Settings
from navigator.domain.frame import Frame


def _frame(settings, synthetic):
    if not synthetic:
        clock = SystemClock()
        with WebcamFrameSource(
            clock=clock,
            device=settings.camera_device,
            width=settings.camera_width,
            height=settings.camera_height,
            fps=settings.camera_fps,
            fourcc=settings.camera_fourcc,
        ) as camera:
            for _ in range(30):
                frame = camera.next_frame(-1, 2.0)
            return frame
    h, w = settings.camera_height, settings.camera_width
    pixels = np.random.default_rng(0).integers(0, 256, h * w * 3, dtype=np.uint8)
    return Frame(0, 0, w, h, pixels.tobytes())


def _percentiles(samples_ms):
    p50, p95, p99 = np.percentile(samples_ms, [50, 95, 99])
    return p50, p95, p99, max(samples_ms)


def _timed(fn, runs):
    start, end = torch.cuda.Event(True), torch.cuda.Event(True)
    samples = []
    for index in range(runs):
        start.record()
        fn(index)
        end.record()
        end.synchronize()
        samples.append(start.elapsed_time(end))
    return _percentiles(samples)


def _forward(settings, frame, long_side, runs):
    model = depth.load(
        settings.perception_model, mode="kernels", options={"long_side": long_side}
    )
    image = np.frombuffer(frame.pixels, np.uint8).reshape(frame.height, frame.width, 3)
    rgb = torch.from_numpy(image[:, :, ::-1].copy()).cuda().permute(2, 0, 1).contiguous()
    k = intrinsics(frame.height, frame.width, settings.hfov_deg)
    for _ in range(20):
        model(rgb, intrinsics=k)
    stats = _timed(lambda i: model(rgb, intrinsics=k), runs)
    del model
    torch.cuda.empty_cache()
    return stats


def _perceive(settings, frame, long_side, runs, previews):
    clock = SystemClock()
    with GpuScenePerception(
        clock=clock,
        model=settings.perception_model,
        input_long_side=long_side,
        rows=settings.grid_rows,
        cols=settings.grid_cols,
        horizontal_fov_deg=settings.hfov_deg,
        scale=settings.scale,
        mount_height_m=settings.mount_height_m,
        pitch_deg=settings.pitch_deg,
    ) as perception:
        perception.warm_up()
        def step(i):
            f = Frame(i, clock.now_ns(), frame.width, frame.height, frame.pixels)
            perception.perceive(f, previews)
        return _timed(step, runs)


def _gpu_state():
    out = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,temperature.gpu,clocks.sm,power.draw",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--sizes", type=int, nargs="+", default=[504, 392])
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    frame = _frame(settings, args.synthetic)
    print(f"input {frame.width}x{frame.height}, {args.runs} warm frames, CUDA events")
    print(f"gpu before: {_gpu_state()}")
    print("| long side | stage | p50 ms | p95 ms | p99 ms | max ms |")
    print("| --- | --- | --- | --- | --- | --- |")
    for long_side in args.sizes:
        rows = {
            "forward": _forward(settings, frame, long_side, args.runs),
            "perceive": _perceive(settings, frame, long_side, args.runs, False),
            "perceive + previews": _perceive(
                settings, frame, long_side, args.runs, True
            ),
        }
        for stage, values in rows.items():
            cells = " | ".join(f"{v:.2f}" for v in values)
            print(f"| {long_side} | {stage} | {cells} |")
    print(f"gpu after: {_gpu_state()}")


if __name__ == "__main__":
    main()
