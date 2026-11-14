import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_all_fakes_run_prints_event_sequence():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "navigator.bootstrap",
            "--preset",
            "all-fakes",
            "--duration-s",
            "7",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    events = [json.loads(line) for line in proc.stdout.splitlines()]
    types = [e["type"] for e in events]
    assert "geometry" in types
    hazards = [e for e in events if e["type"] == "hazard"]
    assert hazards
    first_hazard = types.index("hazard")
    assert "geometry" in types[:first_hazard]
    levels = [h["level"] for h in hazards]
    assert "caution" in levels
    assert "stop" in levels
    assert levels.index("caution") < levels.index("stop")
    utterances = [e for e in events if e["type"] == "utterance"]
    spoken = [u for u in utterances if u["outcome"] == "spoken"]
    assert spoken
