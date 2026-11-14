import json

from PIL import Image

from navigator.adapters.camera.replay import ReplayFrameSource
from navigator.adapters.clock.system import SystemClock

INTERVAL_NS = 20_000_000


def write_session(path, count=3, width=32, height=24):
    (path / "frames").mkdir(parents=True)
    frames, geometry = [], []
    for index in range(count):
        name = f"frames/{index:05d}.jpg"
        Image.new("RGB", (width, height), (100 + index * 60, 0, 0)).save(path / name)
        frames.append(
            {
                "frame_id": index,
                "t_capture_ns": 5_000 + index * INTERVAL_NS,
                "width": width,
                "height": height,
                "file": name,
            }
        )
        geometry.append(
            {
                "frame_id": index,
                "t_capture_ns": 5_000 + index * INTERVAL_NS,
                "rows": 3,
                "cols": 5,
                "distances_m": [None] + [1.0 + index] * 14,
                "valid": [False] + [True] * 14,
                "horizontal_fov_deg": 70.0,
            }
        )
    for name, rows in (("frames.jsonl", frames), ("geometry.jsonl", geometry)):
        (path / name).write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_loops_with_strictly_increasing_ids(tmp_path):
    session = write_session(tmp_path / "s")
    with ReplayFrameSource(clock=SystemClock(), session_dir=session) as source:
        ids, last = [], -1
        while len(ids) < 8:
            frame = source.next_frame(last, timeout_s=1.0)
            last = frame.frame_id
            ids.append(last)
    assert ids == sorted(set(ids))
    assert ids[-1] >= 7
    assert {i % 3 for i in ids} == {0, 1, 2}


def test_pixels_are_bgr_and_restamped(tmp_path):
    session = write_session(tmp_path / "s")
    clock = SystemClock()
    before = clock.now_ns()
    with ReplayFrameSource(clock=clock, session_dir=session) as source:
        frame = source.next_frame(0, timeout_s=1.0)
    assert frame.t_capture_ns >= before
    blue, green, red = frame.pixels[0], frame.pixels[1], frame.pixels[2]
    assert red > 100 and blue < 20 and green < 20
