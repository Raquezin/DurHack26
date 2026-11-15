import pytest
import torch

from navigator.adapters.perception.zones import fit_floor, floor_depth, focal_px
from navigator.domain.geometry import SceneGeometry
from navigator.domain.path import vertical_fov_deg
from navigator.domain.policies.route import floor_mark


def _floor_scene(pitch_deg, height=480, width=640):
    focal = focal_px(width, 58.0)
    floor = floor_depth(height, focal, 1.4, pitch_deg).expand(height, width).clone()
    floor[torch.isinf(floor)] = 20.0
    return floor, torch.ones_like(floor, dtype=torch.bool), focal


def test_level_floor_reads_level():
    depth, usable, focal = _floor_scene(0.0)
    pitch_deg, height_m = fit_floor(depth, usable, focal, 1.4)
    assert abs(pitch_deg - 0.0) < 0.5
    assert abs(height_m - 1.4) < 0.03


def test_tilted_phone_is_measured():
    depth, usable, focal = _floor_scene(25.0)
    pitch_deg, height_m = fit_floor(depth, usable, focal, 1.4)
    assert abs(pitch_deg - 25.0) < 0.5
    assert abs(height_m - 1.4) < 0.03


def test_a_higher_lens_is_measured():
    focal = focal_px(640, 58.0)
    depth = floor_depth(480, focal, 1.6, 5.0).expand(480, 640).clone()
    depth[torch.isinf(depth)] = 20.0
    usable = torch.ones_like(depth, dtype=torch.bool)
    pitch_deg, height_m = fit_floor(depth, usable, focal, 1.4)
    assert abs(pitch_deg - 5.0) < 0.5
    assert abs(height_m - 1.6) < 0.03


def test_furniture_in_front_of_the_floor_still_fits():
    depth, usable, focal = _floor_scene(5.0)
    depth[int(480 * 0.6) :, : int(640 * 0.7)] *= 0.6
    pitch_deg, height_m = fit_floor(depth, usable, focal, 1.4)
    assert abs(pitch_deg - 5.0) < 0.5
    assert abs(height_m - 1.4) < 0.03


def test_a_near_wall_gives_no_estimate():
    depth, usable, focal = _floor_scene(25.0)
    depth[:] = 0.8
    assert fit_floor(depth, usable, focal, 1.4) is None


def test_a_wall_hiding_all_but_a_strip_gives_no_estimate():
    depth, usable, focal = _floor_scene(5.0)
    depth[: int(480 * 0.9), :] = 0.8
    assert fit_floor(depth, usable, focal, 1.4) is None


def test_a_tabletop_instead_of_the_floor_gives_no_estimate():
    focal = focal_px(640, 58.0)
    depth = floor_depth(480, focal, 0.65, 5.0).expand(480, 640).clone()
    depth[torch.isinf(depth)] = 20.0
    usable = torch.ones_like(depth, dtype=torch.bool)
    assert fit_floor(depth, usable, focal, 1.4) is None


def test_floor_mark_inverts_floor_depth():
    geometry = SceneGeometry(
        frame_id=1,
        t_capture_ns=0,
        rows=3,
        cols=5,
        distances_m=(8.0,) * 15,
        valid=(True,) * 15,
        horizontal_fov_deg=58.0,
        vertical_fov_deg=vertical_fov_deg(58.0, 640, 480),
        mount_height_m=1.4,
        pitch_deg=25.0,
    )
    floor = floor_depth(480, focal_px(640, 58.0), 1.4, 25.0)
    for row in (300, 400, 479):
        depth = floor[row, 0].item()
        assert floor_mark(geometry, (0.0, depth))[1] == pytest.approx(
            (row + 0.5) / 480, abs=1e-3
        )
