from navigator.domain.geometry import SceneGeometry
from navigator.domain.phrases import PhraseId
from navigator.domain.policies.steering import (
    SteeringSettings,
    SteeringState,
    advise,
    path_clearance,
    permits,
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
    assert steer(scene([8.0] * 5), S)[0] is PhraseId.GO_STRAIGHT


def test_walls_beside_the_path_do_not_block_it():
    assert steer(scene([2.0, 8.0, 8.0, 8.0, 2.0]), S)[0] is PhraseId.GO_STRAIGHT


def test_head_row_does_not_steer():
    assert steer(scene([8.0] * 5, head=[1.0] * 5), S)[0] is PhraseId.GO_STRAIGHT


def test_blocked_ahead_veers_to_open_neighbour():
    assert steer(scene([2.5, 6.0, 2.5, 2.5, 2.5]), S)[0] is PhraseId.VEER_LEFT
    assert steer(scene([2.5, 2.5, 2.5, 6.0, 2.5]), S)[0] is PhraseId.VEER_RIGHT


def test_only_far_side_open_turns():
    assert steer(scene([2.5, 2.5, 2.5, 2.5, 6.0]), S)[0] is PhraseId.TURN_RIGHT


def test_nothing_open_says_nothing():
    assert steer(scene([2.5] * 5), S)[0] is None


def test_both_sides_open_turns_to_the_roomier_one():
    assert steer(scene([6.0, 2.5, 2.5, 2.5, 9.0]), S)[0] is PhraseId.TURN_RIGHT
    assert steer(scene([9.0, 2.5, 2.5, 2.5, 6.0]), S)[0] is PhraseId.TURN_LEFT


def test_cloud_direction_into_open_space_is_permitted():
    g = scene([6.0, 2.5, 2.5, 2.5, 6.0])
    assert permits(g, PhraseId.TURN_LEFT, S)
    assert permits(g, PhraseId.TURN_RIGHT, S)


def test_cloud_direction_into_a_wall_is_refused():
    g = scene([1.5, 1.5, 1.5, 6.0, 1.5])
    assert steer(g, S)[0] is PhraseId.VEER_RIGHT
    assert not permits(g, PhraseId.TURN_LEFT, S)
    assert not permits(g, PhraseId.VEER_LEFT, S)
    assert permits(g, PhraseId.VEER_RIGHT, S)


def test_veer_and_turn_both_mean_that_side():
    g = scene([1.5, 1.5, 1.5, 1.5, 6.0])
    assert permits(g, PhraseId.VEER_RIGHT, S)
    assert permits(g, PhraseId.TURN_RIGHT, S)
    assert not permits(g, PhraseId.TURN_LEFT, S)


def test_a_side_without_a_hazard_counts_as_open_in_tight_spaces():
    g = scene([2.2, 1.5, 1.0, 1.5, 1.5])
    assert steer(g, S)[0] is None
    assert permits(g, PhraseId.TURN_LEFT, S)
    assert not permits(g, PhraseId.TURN_RIGHT, S)


def test_straight_refused_when_the_path_is_blocked():
    assert not permits(scene([8.0, 8.0, 1.5, 8.0, 8.0]), PhraseId.GO_STRAIGHT, S)
    assert permits(scene([8.0] * 5), PhraseId.GO_STRAIGHT, S)


def test_non_directional_answers_always_permitted():
    g = scene([2.5] * 5)
    assert permits(g, PhraseId.DOOR_AHEAD, S)
    assert permits(g, None, S)


def test_neighbour_obstacle_inside_the_path_blocks_it():
    g = scene([8.0, 1.2, 8.0, 8.0, 8.0])
    assert path_clearance(g, S) == 1.2


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


def test_direction_change_waits_for_min_interval():
    left, right = PhraseId.VEER_LEFT, PhraseId.VEER_RIGHT
    spoken = _run([left] * 3 + [right] * 40)
    assert spoken[2] is left
    assert spoken.index(right) == 32


def test_held_phrase_is_repeated_after_the_repeat_interval():
    straight = PhraseId.GO_STRAIGHT
    spoken = _run([straight] * 310)
    assert [i for i, said in enumerate(spoken) if said] == [2, 302]


def test_turns_toward_open_space_past_a_near_obstacle():
    assert steer(scene([2.5, 2.5, 8.0, 1.0, 9.0]), S)[0] is PhraseId.TURN_RIGHT


def test_tie_at_the_far_edges_goes_to_the_roomier_side():
    assert steer(scene([10.0, 5.0, 1.0, 2.0, 10.0]), S)[0] is PhraseId.TURN_LEFT
    assert steer(scene([10.0, 2.0, 1.0, 5.0, 10.0]), S)[0] is PhraseId.TURN_RIGHT


def test_back_to_straight_waits_for_min_interval():
    straight, left = PhraseId.GO_STRAIGHT, PhraseId.VEER_LEFT
    spoken = _run([left] * 3 + [straight] * 40)
    assert spoken[2] is left
    assert spoken.index(straight) == 32


def fine(columns):
    return SceneGeometry(
        frame_id=1, t_capture_ns=0, rows=3, cols=15,
        distances_m=tuple([8.0] * 15 + list(columns) * 2),
        valid=(True,) * 45, horizontal_fov_deg=58.0,
    )


def test_a_gap_too_narrow_to_walk_through_is_not_a_way():
    narrow = [1.5] * 15
    narrow[11] = 6.0
    assert steer(fine(narrow), S)[0] is None


def test_a_gap_as_wide_as_the_walker_is_a_way():
    wide = [1.5] * 15
    wide[10:14] = [6.0] * 4
    assert steer(fine(wide), S)[0] is PhraseId.VEER_RIGHT


def test_committed_side_is_kept_while_viable():
    g = fine([8.0] * 7 + [2.0] + [6.0] * 7)
    assert steer(g, S)[0] is PhraseId.VEER_LEFT
    assert steer(g, S, committed=1) == (PhraseId.VEER_RIGHT, 1)


def test_commitment_dropped_when_the_side_closes():
    g = fine([8.0] * 7 + [2.0] + [1.5] * 7)
    assert steer(g, S, committed=1) == (PhraseId.VEER_LEFT, -1)


def test_commitment_cleared_when_the_path_opens():
    assert steer(fine([8.0] * 15), S, committed=-1) == (PhraseId.GO_STRAIGHT, None)


def test_much_roomier_side_pulls_the_commitment():
    g = fine([4.0] * 7 + [2.0] + [9.0] * 7)
    assert steer(g, S, committed=-1) == (PhraseId.VEER_RIGHT, 1)


def test_no_way_clears_the_commitment():
    assert steer(fine([1.5] * 15), S, committed=1) == (None, None)


def test_committed_side_refuses_opposite_cloud_direction():
    g = scene([1.5, 1.5, 1.5, 6.0, 1.5])
    assert not permits(g, PhraseId.TURN_LEFT, S, committed=1)
    assert not permits(g, PhraseId.VEER_LEFT, S, committed=1)
    assert permits(g, PhraseId.VEER_RIGHT, S, committed=1)


def test_dead_commitment_does_not_block_cloud_directions():
    g = scene([1.5, 1.5, 1.5, 6.0, 1.5])
    assert permits(g, PhraseId.TURN_RIGHT, S, committed=-1)
