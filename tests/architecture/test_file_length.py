import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_LINES = 300


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [ROOT / line for line in out]


def _is_text(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if b"\x00" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def test_every_file_under_max_lines():
    offenders = []
    for path in _tracked_files():
        if path.name == "uv.lock" or not _is_text(path):
            continue
        lines = path.read_text().splitlines()
        if len(lines) >= MAX_LINES:
            offenders.append(f"{path.relative_to(ROOT)}: {len(lines)}")
    assert not offenders, offenders
