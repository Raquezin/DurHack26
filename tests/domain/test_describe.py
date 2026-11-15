from navigator.domain.hazard import Bearing
from navigator.domain.policies.describe import describe
from navigator.domain.tags import SceneTag


def _outline(x0, y0, x1, y1):
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def test_names_the_thing_ahead():
    tags = (SceneTag("chair", _outline(0.4, 0.4, 0.6, 0.9)),)
    assert describe(tags, Bearing.AHEAD) == "There is a chair in front of you."


def test_names_the_side():
    left = (SceneTag("chair", _outline(0.05, 0.4, 0.25, 0.9)),)
    right = (SceneTag("chair", _outline(0.75, 0.4, 0.95, 0.9)),)
    assert describe(left, Bearing.LEFT) == "There is a chair on your left."
    assert describe(right, Bearing.RIGHT) == "There is a chair on your right."


def test_person_becomes_someone():
    tags = (SceneTag("person", _outline(0.4, 0.1, 0.6, 0.9)),)
    assert describe(tags, Bearing.AHEAD) == "There is someone in front of you."


def test_vowel_start_gets_an():
    tags = (SceneTag("apple", _outline(0.4, 0.4, 0.6, 0.9)),)
    assert describe(tags, Bearing.AHEAD) == "There is an apple in front of you."


def test_tag_without_outline_is_skipped():
    tags = (SceneTag("chair"),)
    assert describe(tags, Bearing.AHEAD) is None


def test_tag_outside_bearing_is_skipped():
    tags = (SceneTag("chair", _outline(0.75, 0.4, 0.95, 0.9)),)
    assert describe(tags, Bearing.LEFT) is None


def test_lowest_tag_wins_when_several_overlap():
    tags = (
        SceneTag("box", _outline(0.4, 0.1, 0.6, 0.4)),
        SceneTag("chair", _outline(0.4, 0.4, 0.6, 0.9)),
    )
    assert describe(tags, Bearing.AHEAD) == "There is a chair in front of you."


def test_tag_spanning_the_region_matches():
    tags = (SceneTag("person", _outline(0.1, 0.2, 0.7, 0.95)),)
    assert describe(tags, Bearing.AHEAD) == "There is someone in front of you."


def test_no_tags_no_sentence():
    assert describe((), Bearing.AHEAD) is None
