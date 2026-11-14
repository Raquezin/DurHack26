import argparse
import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np

from navigator.adapters.camera.webcam import WebcamFrameSource
from navigator.adapters.clock.system import SystemClock
from navigator.adapters.perception.gpu import GpuScenePerception
from navigator.bootstrap.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def _args():
    s = Settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="default")
    parser.add_argument("--seconds", type=float, default=9.0)
    parser.add_argument("--quality", type=int, default=75)
    parser.add_argument("--device", type=int, default=s.camera_device)
    parser.add_argument("--width", type=int, default=s.camera_width)
    parser.add_argument("--height", type=int, default=s.camera_height)
    parser.add_argument("--fps", type=int, default=s.camera_fps)
    parser.add_argument("--fourcc", default=s.camera_fourcc)
    parser.add_argument("--model", default=s.perception_model)
    parser.add_argument("--long-side", type=int, default=s.input_long_side)
    parser.add_argument("--hfov", type=float, default=s.hfov_deg)
    parser.add_argument("--scale", type=float, default=s.scale)
    parser.add_argument("--mount-height", type=float, default=s.mount_height_m)
    parser.add_argument("--pitch", type=float, default=s.pitch_deg)
    return parser.parse_args(), s


def _geometry_line(index, geometry):
    return json.dumps(
        {
            "frame_id": index,
            "t_capture_ns": geometry.t_capture_ns,
            "rows": geometry.rows,
            "cols": geometry.cols,
            "distances_m": [
                None if math.isinf(d) else round(d, 4) for d in geometry.distances_m
            ],
            "valid": list(geometry.valid),
            "horizontal_fov_deg": geometry.horizontal_fov_deg,
        }
    )


def record(args, settings):
    out = ROOT / "fixtures" / "sessions" / args.name
    shutil.rmtree(out, ignore_errors=True)
    (out / "frames").mkdir(parents=True)
    clock = SystemClock()
    camera = WebcamFrameSource(
        clock=clock,
        device=args.device,
        width=args.width,
        height=args.height,
        fps=args.fps,
        fourcc=args.fourcc,
    )
    perception = GpuScenePerception(
        clock=clock,
        model=args.model,
        input_long_side=args.long_side,
        rows=settings.grid_rows,
        cols=settings.grid_cols,
        horizontal_fov_deg=args.hfov,
        scale=args.scale,
        mount_height_m=args.mount_height,
        pitch_deg=args.pitch,
    )
    frames, geometries = [], []
    with camera, perception:
        perception.warm_up()
        last = camera.next_frame(-1, 2.0).frame_id
        end_ns = clock.now_ns() + int(args.seconds * 1e9)
        while clock.now_ns() < end_ns:
            frame = camera.next_frame(last, 1.0)
            if frame is None:
                continue
            last = frame.frame_id
            geometry = perception.perceive(frame, False).geometry
            index = len(frames)
            name = f"frames/{index:05d}.jpg"
            image = np.frombuffer(frame.pixels, np.uint8).reshape(
                frame.height, frame.width, 3
            )
            _, jpeg = cv2.imencode(
                ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, args.quality]
            )
            (out / name).write_bytes(jpeg.tobytes())
            frames.append(
                json.dumps(
                    {
                        "frame_id": index,
                        "t_capture_ns": frame.t_capture_ns,
                        "width": frame.width,
                        "height": frame.height,
                        "file": name,
                    }
                )
            )
            geometries.append(_geometry_line(index, geometry))
    (out / "frames.jsonl").write_text("\n".join(frames) + "\n")
    (out / "geometry.jsonl").write_text("\n".join(geometries) + "\n")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    span_s = (
        json.loads(frames[-1])["t_capture_ns"] - json.loads(frames[0])["t_capture_ns"]
    ) / 1e9
    print(f"{out}: {len(frames)} frames over {span_s:.2f} s, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    record(*_args())
