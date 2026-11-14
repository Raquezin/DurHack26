import argparse
import asyncio
import json
import subprocess
import threading
import wave
from pathlib import Path

import cv2
import numpy as np

from navigator.adapters.audio.recording import RecordingAudioSink
from navigator.adapters.clock.system import SystemClock
from navigator.bootstrap.config import apply_overrides, resolve
from navigator.bootstrap.main import run
from navigator.domain.events import (
    GuidanceTextEvent,
    HazardEvent,
    Outcome,
    PreviewEvent,
    PreviewKind,
    UtteranceEvent,
)
from navigator.domain.speech import SAMPLE_RATE_HZ, Priority

ROOT = Path(__file__).resolve().parents[1]
FPS = 30
TILE = (360, 480)
CAPTION_S = 2.5
COLOURS = {"HAZARD": (40, 40, 230), "GEMINI": (230, 160, 40), "LOCAL": (60, 190, 60)}


class StampedEvents:
    def __init__(self, clock) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self.events = []

    def publish(self, event) -> None:
        with self._lock:
            self.events.append((self._clock.now_ns(), event))


def session_seconds(session: Path) -> float:
    stamps = [json.loads(line)["t_capture_ns"] for line in (session / "frames.jsonl").read_text().splitlines()]
    return (stamps[-1] - stamps[0]) / 1e9


def captions(events, t0):
    asked = []
    out = []
    for t, event in events:
        if isinstance(event, GuidanceTextEvent):
            asked.append((t, event.delta))
        elif isinstance(event, UtteranceEvent) and event.outcome is Outcome.SPOKEN:
            if event.priority is Priority.HAZARD:
                source = "HAZARD"
            elif any(text == event.text and t - when < 6e9 for when, text in asked):
                source = "GEMINI"
            else:
                source = "LOCAL"
            out.append(((t - t0) / 1e9, source, event.text, event.age_ms))
    return out


def audio_track(plays, interrupts, t0, seconds):
    track = np.zeros(int(seconds * SAMPLE_RATE_HZ), np.int16)
    timeline = sorted(
        [(t, np.frombuffer(c.samples, np.int16)) for t, c in plays] + [(t, None) for t in interrupts],
        key=lambda item: item[0],
    )
    cursor = 0
    for t, samples in timeline:
        at = int((t - t0) / 1e9 * SAMPLE_RATE_HZ)
        if samples is None:
            track[max(0, at):cursor] = 0
            cursor = min(cursor, max(0, at))
            continue
        start = max(at, cursor, 0)
        end = min(len(track), start + len(samples))
        track[start:end] = samples[: max(0, end - start)]
        cursor = max(cursor, end)
    return track


def _tile(jpeg):
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    return cv2.resize(image, TILE)


def frames(events, lines, hazards, t0, seconds):
    previews = sorted(
        ((t - t0) / 1e9, e.kind, e.jpeg) for t, e in events if isinstance(e, PreviewEvent)
    )
    latest = {PreviewKind.CAMERA: None, PreviewKind.DEPTH: None}
    index = 0
    blank = np.zeros((TILE[1], TILE[0], 3), np.uint8)
    for n in range(int(seconds * FPS)):
        now = n / FPS
        while index < len(previews) and previews[index][0] <= now:
            latest[previews[index][1]] = previews[index][2]
            index += 1
        tiles = [_tile(latest[k]) if latest[k] else blank for k in (PreviewKind.CAMERA, PreviewKind.DEPTH)]
        top = np.hstack(tiles)
        panel = np.full((150, top.shape[1], 3), 24, np.uint8)
        cv2.putText(panel, f"t = {now:4.1f} s", (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        hazard = [h for h in hazards if 0 <= now - h[0] < 1.0]
        if hazard:
            cv2.putText(panel, hazard[-1][1], (150, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOURS["HAZARD"], 2)
        recent = [c for c in lines if 0 <= now - c[0] < CAPTION_S][-3:]
        for row, (_, source, text, age_ms) in enumerate(recent):
            y = 62 + row * 34
            cv2.putText(panel, source, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOURS[source], 2)
            cv2.putText(panel, f"{text}  ({age_ms:.0f} ms)", (130, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (240, 240, 240), 2)
        yield np.vstack([top, panel])


def render(args) -> None:
    settings = apply_overrides(resolve("video", {}), [f"session_dir={args.session}", "preview_every=1", *args.overrides])
    clock = SystemClock()
    sink = RecordingAudioSink(clock=clock)
    events = StampedEvents(clock)
    seconds = args.seconds or session_seconds(args.session) * args.loops
    t0 = clock.now_ns()
    asyncio.run(run(settings, seconds + 2.0, provided={"clock": clock, "audio_sink": sink, "event_publisher": events}))
    first = min((t for t, e in events.events if isinstance(e, PreviewEvent)), default=t0)
    lines = captions(events.events, first)
    hazards = [((t - first) / 1e9, f"hazard {e.level.value} {e.bearing.value} {e.distance_m:.2f} m") for t, e in events.events if isinstance(e, HazardEvent)]
    track = audio_track(sink.plays, sink.interrupts, first, seconds)
    wav_path = args.out.with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE_HZ)
        wav.writeframes(track.tobytes())
    height, width = TILE[1] + 150, TILE[0] * 2
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
         "-r", str(FPS), "-i", "-", "-i", str(wav_path), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(args.out)],
        stdin=subprocess.PIPE,
    )
    for frame in frames(events.events, lines, hazards, first, seconds):
        ffmpeg.stdin.write(frame.tobytes())
    ffmpeg.stdin.close()
    ffmpeg.wait()
    wav_path.unlink()
    for at, source, text, age_ms in lines:
        print(f"{at:5.1f} s  {source:<6} {text}  (capture to playback {age_ms:.0f} ms)")
    print(f"{args.out}: {seconds:.1f} s, {len(lines)} spoken lines")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=Path, default=ROOT / "fixtures" / "sessions" / "default")
    parser.add_argument("--loops", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "run.mp4")
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    render(parser.parse_args())


if __name__ == "__main__":
    main()
