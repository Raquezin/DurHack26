import re
import shutil
import subprocess
import sys
import time

import cv2

SIZES = ((640, 480), (1280, 720), (1920, 1080))
FORMATS = ("MJPG", "YUYV")


def v4l2_modes(device):
    if not shutil.which("v4l2-ctl"):
        return []
    out = subprocess.run(
        ["v4l2-ctl", "-d", device, "--list-formats-ext"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    modes, fourcc, size = [], None, None
    for line in out.splitlines():
        if m := re.search(r"\[\d+\]: '(\w+)'", line):
            fourcc = m.group(1)
        elif m := re.search(r"Size: Discrete (\d+)x(\d+)", line):
            size = (int(m.group(1)), int(m.group(2)))
        elif m := re.search(r"\(([\d.]+) fps\)", line):
            modes.append((fourcc, *size, float(m.group(1))))
    return modes


def v4l2_controls(device, names=("auto_exposure", "exposure_dynamic_framerate")):
    if not shutil.which("v4l2-ctl"):
        return "v4l2-ctl not found"
    out = subprocess.run(
        ["v4l2-ctl", "-d", device, "-C", ",".join(names)],
        capture_output=True,
        text=True,
        check=False,
    )
    return ", ".join((out.stdout + out.stderr).split("\n")).strip(", ")


def fourcc_name(value):
    return int(value).to_bytes(4, "little").decode(errors="replace")


def negotiate(index, fourcc, width, height, seconds=1.5):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    for _ in range(3):
        ok, frame = cap.read()
    frames, start = 0, time.perf_counter()
    while ok and time.perf_counter() - start < seconds:
        ok, frame = cap.read()
        frames += ok
    elapsed = time.perf_counter() - start
    result = {
        "request": f"{fourcc} {width}x{height}",
        "fourcc": fourcc_name(cap.get(cv2.CAP_PROP_FOURCC)),
        "size": f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",
        "fps_prop": f"{cap.get(cv2.CAP_PROP_FPS):.1f}",
        "fps_measured": f"{frames / elapsed:.1f}",
        "buffer": str(int(cap.get(cv2.CAP_PROP_BUFFERSIZE))),
        "frame": "x".join(map(str, frame.shape)) if ok else "none",
    }
    cap.release()
    return result


def table(rows):
    if not rows:
        return "(none)"
    keys = list(rows[0])
    widths = [max(len(k), *(len(str(r[k])) for r in rows)) for k in keys]
    line = lambda values: "  ".join(str(v).ljust(w) for v, w in zip(values, widths))
    return "\n".join(
        [line(keys), line("-" * w for w in widths), *(line(r.values()) for r in rows)]
    )


def report(index=0):
    device = f"/dev/video{index}"
    driver = [
        dict(zip(("fourcc", "width", "height", "fps"), m)) for m in v4l2_modes(device)
    ]
    opencv = [negotiate(index, f, w, h) for f in FORMATS for w, h in SIZES]
    controls = v4l2_controls(device)
    return f"v4l2 modes of {device}\n{table(driver)}\n\nOpenCV negotiated (CAP_V4L2, BUFFERSIZE=1; {controls})\n{table(opencv)}"


if __name__ == "__main__":
    print(report(int(sys.argv[1]) if len(sys.argv) > 1 else 0))
