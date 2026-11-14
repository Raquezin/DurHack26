from navigator.domain.geometry import SceneGeometry
from navigator.domain.phrases import PhraseId
from navigator.domain.policies.steering import (
    SteeringSettings,
    SteeringState,
    advise,
    path_clearance,
    steer,
)

S = SteeringSettings(look_m=3.0, confirm_frames=3, min_interval_s=3.0)
SECOND = 1_000_000_000


def scene(torso_and_legs, head=None):
    head = head or [8.0] * 5
    return SceneGeometry(
        frame_id=1,
        t_capture_ns=0,
        rows=3,
        cols=5,
        distances_m=tuple(head + torso_and_legs + torso_and_legs),
        valid=(True,) * 15,
        horizontal_fov_deg=58.0,
    )


def test_open_path_goes_straight():
    assert steer(scene([8.0] * 5), S) is PhraseId.GO_STRAIGHT


def test_walls_beside_the_path_do_not_block_it():
    assert steer(scene([2.0, 8.0, 8.0, 8.0, 2.0]), S) is PhraseId.GO_STRAIGHT


def test_head_row_does_not_steer():
    assert steer(scene([8.0] * 5, head=[1.0] * 5), S) is PhraseId.GO_STRAIGHT


def test_blocked_ahead_veers_to_open_neighbour():
    assert steer(scene([2.5, 6.0, 2.5, 2.5, 2.5]), S) is PhraseId.VEER_LEFT
    assert steer(scene([2.5, 2.5, 2.5, 6.0, 2.5]), S) is PhraseId.VEER_RIGHT


def test_only_far_side_open_turns():
    assert steer(scene([2.5, 2.5, 2.5, 2.5, 6.0]), S) is PhraseId.TURN_RIGHT


def test_nothing_open_says_nothing():
    assert steer(scene([2.5] * 5), S) is None


def test_neighbour_obstacle_inside_the_path_blocks_it():
    g = scene([8.0, 2.5, 8.0, 8.0, 8.0])
    assert path_clearance(g, S) == 2.5


def _run(phrases, step_s=0.1):
    state, spoken = SteeringState(), []
    for i, phrase in enumerate(phrases):
        state, said = advise(state, phrase, int(i * step_s * SECOND), S)
        spoken.append(said)
    return spoken


def test_speaks_once_confirmed_then_stays_quiet():
    straight = PhraseId.GO_STRAIGHT
    assert _run([straight] * 6) == [None, None, straight, None, None, None]


def test_flicker_is_never_spoken():
    left, right = PhraseId.VEER_LEFT, PhraseId.VEER_RIGHT
    assert _run([left, right] * 5) == [None] * 10


def test_change_waits_for_min_interval():
    straight, left = PhraseId.GO_STRAIGHT, PhraseId.VEER_LEFT
    spoken = _run([straight] * 3 + [left] * 40)
    assert spoken[2] is straight
    assert spoken.index(left) == 32
