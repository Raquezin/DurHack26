import argparse
import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np
from rig import add_arguments, first_frame, rig, settings_from

from navigator.domain.frame import Frame

ROOT = Path(__file__).resolve().parents[1]
VIDEO_LONG_SIDE = 640


def _args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="default")
    parser.add_argument("--seconds", type=float, default=9.0)
    parser.add_argument("--quality", type=int, default=75)
    parser.add_argument("--video", type=Path, default=None)
    add_arguments(parser)
    args = parser.parse_args()
    return args, settings_from(args)


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
            "vertical_fov_deg": round(geometry.vertical_fov_deg, 4),
            "mount_height_m": geometry.mount_height_m,
            "pitch_deg": round(geometry.pitch_deg, 2),
        }
    )


def _camera_frames(clock, camera, seconds):
    last = first_frame(camera).frame_id
    end_ns = clock.now_ns() + int(seconds * 1e9)
    while clock.now_ns() < end_ns:
        frame = camera.next_frame(last, 1.0)
        if frame is not None:
            last = frame.frame_id
            yield frame


def _video_frames(path: Path):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit(f"cannot open {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    index = 0
    while True:
        ok, image = capture.read()
        if not ok:
            break
        factor = VIDEO_LONG_SIDE / max(image.shape[:2])
        if factor < 1:
            image = cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        height, width = image.shape[:2]
        yield Frame(
            frame_id=index,
            t_capture_ns=int(index * 1e9 / fps),
            width=width,
            height=height,
            pixels=np.ascontiguousarray(image).tobytes(),
        )
        index += 1
    capture.release()


def record(args, settings):
    out = ROOT / "fixtures" / "sessions" / args.name
    frames, geometries = [], []
    with rig(settings, camera=args.video is None) as (clock, camera, perception):
        source = (
            _video_frames(args.video)
            if args.video is not None
            else _camera_frames(clock, camera, args.seconds)
        )
        for frame in source:
            if not frames:
                shutil.rmtree(out, ignore_errors=True)
                (out / "frames").mkdir(parents=True)
                print(f"recording into {out}")
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
