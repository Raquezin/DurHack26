import math

import pytest

from navigator.domain.geometry import SceneGeometry
from navigator.domain.policies.route import floor_line, floor_mark


def _geometry(pitch_deg=0.0):
    return SceneGeometry(
        frame_id=1,
        t_capture_ns=0,
        rows=3,
        cols=15,
        distances_m=(8.0,) * 45,
        valid=(True,) * 45,
        horizontal_fov_deg=90.0,
        vertical_fov_deg=90.0,
        mount_height_m=1.4,
        pitch_deg=pitch_deg,
    )


def test_a_point_on_the_floor_marks_the_picture():
    g = _geometry()
    assert floor_mark(g, (0.0, 2.8)) == (0.5, 0.75)
    assert floor_mark(g, (1.4, 2.8)) == (0.75, 0.75)


def test_a_floor_contact_below_the_frame_sits_on_the_bottom_edge():
    assert floor_mark(_geometry(), (0.0, 0.7)) == (0.5, 1.0)


def test_a_tilted_camera_marks_the_horizon_at_mid_height():
    g = _geometry(pitch_deg=45.0)
    _, v = floor_mark(g, (0.0, 1.4 / math.sin(math.radians(45))))
    assert v == pytest.approx(0.5, abs=1e-3)


def test_a_straight_line_reaches_the_bottom_edge():
    g = _geometry()
    assert floor_line(g, ((0.0, 0.0), (0.0, 2.8))) == ((0.5, 1.0), (0.5, 0.75))


def test_a_bend_projects_every_leg():
    g = _geometry()
    line = floor_line(g, ((0.0, 0.0), (1.4, 2.8), (1.4, 5.6)))
    assert line == ((0.75, 1.0), (0.75, 0.75), (0.625, 0.625))


def test_a_line_wholly_below_the_frame_is_empty():
    assert floor_line(_geometry(), ((0.0, 0.0), (0.0, 1.0))) == ()


def test_the_origin_alone_is_empty():
    assert floor_line(_geometry(), ((0.0, 0.0),)) == ()


def test_a_camera_aimed_above_the_floor_draws_nothing():
    g = _geometry(pitch_deg=-50.0)
    assert floor_line(g, ((0.0, 0.0), (0.0, 5.0))) == ()


def test_the_clip_can_land_inside_a_later_leg():
    g = _geometry()
    line = floor_line(g, ((0.0, 0.0), (0.5, 1.0), (0.5, 2.8)))
    assert line == ((0.6786, 1.0), (0.5893, 0.75))
