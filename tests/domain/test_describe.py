from navigator.domain.geometry import SceneGeometry
from navigator.domain.hazard import Bearing
from navigator.domain.path import blocking_zone
from navigator.domain.policies.describe import (
    blocker_tag,
    describe,
    tag_map,
    usable,
)
from navigator.domain.policies.trigger import TriggerSettings
from navigator.domain.tags import SceneTag

T = TriggerSettings()
SECOND = 1_000_000_000
HALF = 0.4
FAR = 5.0


def _outline(x0, y0, x1, y1):
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _geometry(columns=(FAR, FAR, 1.0, FAR, FAR), t_capture_ns=0, cols=5):
    return SceneGeometry(
        frame_id=1,
        t_capture_ns=t_capture_ns,
        rows=3,
        cols=cols,
        distances_m=(FAR,) * cols + tuple(columns) * 2,
        valid=(True,) * (3 * cols),
        horizontal_fov_deg=58.0,
    )


def _named(tags, geometry=None, asked=None):
    geometry = geometry or _geometry()
    marked = tag_map(asked or geometry, tuple(tags))
    return blocker_tag(marked, geometry, blocking_zone(geometry, HALF), HALF, T)


CHAIR = SceneTag("chair", _outline(0.4, 0.4, 0.6, 0.9))


def test_sentence_names_the_thing_and_the_side():
    assert describe(CHAIR, Bearing.AHEAD) == "A chair ahead."
    assert describe(CHAIR, Bearing.LEFT) == "A chair on your left."
    assert describe(CHAIR, Bearing.RIGHT) == "A chair on your right."


def test_person_becomes_someone():
    assert describe(SceneTag("person"), Bearing.AHEAD) == "Someone ahead."


def test_vowel_start_gets_an():
    assert describe(SceneTag("apple"), Bearing.AHEAD) == "An apple ahead."


def test_coverage_is_the_share_of_each_zone_inside_the_outline():
    marked = tag_map(_geometry(), (CHAIR, SceneTag("door")))
    chair, door = marked.coverage
    assert chair[5 + 2] == 0.75 and chair[10 + 2] == 0.75
    assert chair[2] == 0.0 and chair[5 + 1] == 0.0
    assert door == (0.0,) * 15


def test_tag_on_the_blocking_surface_is_named():
    assert _named([CHAIR]) is CHAIR


def test_tag_beside_the_blocking_surface_is_not_named():
    beside = SceneTag("chair", _outline(0.8, 0.4, 1.0, 0.9))
    assert _named([beside]) is None


def test_tag_without_outline_is_not_named():
    assert _named([SceneTag("chair")]) is None


def test_no_tags_no_name():
    assert _named([]) is None


def test_sliver_of_the_surface_is_not_enough():
    sliver = SceneTag("bench", _outline(0.0, 0.93, 1.0, 1.0))
    assert _named([sliver]) is None
    assert _named([sliver, CHAIR]) is CHAIR


def test_smaller_tag_wins_when_both_cover_the_surface():
    wall = SceneTag("wall", _outline(0.0, 0.0, 1.0, 1.0))
    person = SceneTag("person", _outline(0.38, 0.2, 0.62, 0.98))
    assert _named([wall, person]) is person
    assert _named([person, wall]) is person


def test_background_tag_sharing_one_zone_does_not_name_a_wide_near_surface():
    pillar = (FAR,) * 4 + (0.9,) * 6 + (FAR,) * 5
    geometry = _geometry(pillar, cols=15)
    wall = SceneTag("wall", _outline(0.25, 0.1, 0.68, 1.0))
    person = SceneTag("person", _outline(0.6, 0.4, 0.68, 0.7))
    assert _named([person, wall], geometry) is wall
    assert _named([person], geometry) is None


def test_bounding_box_overlap_is_not_enough():
    corner = SceneTag(
        "table",
        ((0.0, 0.34), (0.99, 0.34), (0.99, 0.36), (0.02, 0.36), (0.02, 0.99), (0.0, 0.99)),
    )
    assert _named([corner]) is None


def test_only_the_near_surface_counts_not_what_stands_behind_it():
    geometry = _geometry((FAR, FAR, 1.0, FAR, FAR))
    low = SceneTag("suitcase", _outline(0.4, 0.34, 0.6, 1.0))
    assert _named([low], geometry) is low
    stepped = SceneGeometry(
        frame_id=1,
        t_capture_ns=0,
        rows=3,
        cols=5,
        distances_m=(FAR,) * 5 + (FAR, FAR, 4.0, FAR, FAR) + (FAR, FAR, 1.0, FAR, FAR),
        valid=(True,) * 15,
        horizontal_fov_deg=58.0,
    )
    behind = SceneTag("door", _outline(0.4, 0.34, 0.6, 0.66))
    assert _named([behind], stepped) is None


def test_tags_from_the_same_scene_are_usable():
    marked = tag_map(_geometry(), (CHAIR,))
    assert usable(marked, _geometry(t_capture_ns=SECOND), T)


def test_no_tags_yet_means_none_usable():
    assert not usable(None, _geometry(), T)


def test_old_tags_are_not_named():
    assert _named([CHAIR], _geometry(t_capture_ns=3 * SECOND), asked=_geometry()) is None


def test_tags_from_a_scene_that_has_since_changed_are_not_named():
    turned = _geometry((1.0, 1.0, 1.0, 1.0, 1.0), t_capture_ns=SECOND)
    assert _named([CHAIR], turned, asked=_geometry((FAR,) * 5)) is None
