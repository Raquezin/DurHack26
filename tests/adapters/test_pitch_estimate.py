import torch

from navigator.adapters.perception.zones import estimate_pitch_deg, floor_depth, focal_px


def _floor_scene(pitch_deg, height=480, width=640):
    focal = focal_px(width, 58.0)
    floor = floor_depth(height, focal, 1.4, pitch_deg).expand(height, width).clone()
    floor[torch.isinf(floor)] = 20.0
    return floor, torch.ones_like(floor, dtype=torch.bool), focal


def test_level_floor_reads_level():
    depth, usable, focal = _floor_scene(0.0)
    assert abs(estimate_pitch_deg(depth, usable, focal, 1.4) - 0.0) < 0.5


def test_tilted_phone_is_measured():
    depth, usable, focal = _floor_scene(25.0)
    assert abs(estimate_pitch_deg(depth, usable, focal, 1.4) - 25.0) < 0.5


def test_a_near_wall_gives_no_estimate():
    depth, usable, focal = _floor_scene(25.0)
    depth[:] = 0.8
    assert estimate_pitch_deg(depth, usable, focal, 1.4) is None


def test_estimate_is_clamped():
    depth, usable, focal = _floor_scene(60.0)
    assert estimate_pitch_deg(depth, usable, focal, 1.4) == 40.0
