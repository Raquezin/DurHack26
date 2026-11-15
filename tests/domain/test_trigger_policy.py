from navigator.domain.geometry import SceneGeometry
from navigator.domain.path import vertical_fov_deg
from navigator.domain.policies.trigger import (
    TriggerSettings,
    should_request,
    still_valid,
)

S = TriggerSettings(min_interval_s=2.0, keepalive_s=8.0)
SECOND = 1_000_000_000


def scene(distances):
    return SceneGeometry(
        frame_id=1,
        t_capture_ns=0,
        rows=3,
        cols=5,
        distances_m=tuple(distances),
        valid=(True,) * 15,
        horizontal_fov_deg=58.0,
        vertical_fov_deg=vertical_fov_deg(58.0, 640, 480),
        mount_height_m=1.4,
        pitch_deg=0.0,
    )


STILL = scene([4.0] * 15)
MOVED = scene([4.0] * 10 + [2.0] * 5)
NUDGED = scene([4.0] * 14 + [2.0])


def test_first_request_fires_immediately():
    assert should_request(0, None, None, STILL, S)


def test_changed_scene_fires_after_min_interval():
    assert should_request(2 * SECOND, 0, STILL, MOVED, S)


def test_changed_scene_waits_for_min_interval():
    assert not should_request(2 * SECOND - 1, 0, STILL, MOVED, S)


def test_unchanged_scene_waits_for_keepalive():
    assert not should_request(7 * SECOND, 0, STILL, STILL, S)
    assert should_request(8 * SECOND, 0, STILL, STILL, S)


def test_one_zone_changing_is_not_a_new_scene():
    assert not should_request(3 * SECOND, 0, STILL, NUDGED, S)


def test_distance_jitter_is_not_a_new_scene():
    jitter = scene([4.0 * 1.2] * 15)
    assert not should_request(3 * SECOND, 0, STILL, jitter, S)


def test_far_changes_beyond_range_are_ignored():
    far = scene([12.0] * 15)
    farther = scene([30.0] * 15)
    assert not should_request(3 * SECOND, 0, far, farther, S)


def test_walking_closer_keeps_an_answer_valid():
    closer = scene([3.0] * 15)
    assert still_valid(STILL, closer, S)


def test_a_different_view_makes_an_answer_stale():
    turned = scene([1.5] * 10 + [4.0] * 5)
    assert not still_valid(STILL, turned, S)
