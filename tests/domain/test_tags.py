from navigator.domain.tags import (
    MAX_TAG_CHARS,
    MAX_TAGS,
    ROAD_CROSSING,
    SceneTag,
    clean_tags,
    has_road_crossing,
)


def _tags(*labels):
    return tuple(SceneTag(label) for label in labels)


def test_clean_lowercases_trims_and_drops_duplicates():
    assert clean_tags(_tags(" Car ", "car", "Bus.", "", "  ")) == _tags(
        "car", "bus"
    )


def test_clean_collapses_inner_whitespace():
    assert clean_tags(_tags("Road   Crossing")) == _tags(ROAD_CROSSING)


def test_clean_limits_count_and_length():
    many = _tags(*(f"tag{i}" for i in range(MAX_TAGS + 3)))
    assert len(clean_tags(many)) == MAX_TAGS
    assert len(clean_tags(_tags("x" * 100))[0].label) == MAX_TAG_CHARS


def test_clean_keeps_the_same_label_in_two_places():
    left = ((0.1, 0.4), (0.2, 0.4), (0.2, 0.8))
    right = ((0.6, 0.4), (0.7, 0.4), (0.7, 0.8))
    people = (SceneTag("person", left), SceneTag("person", right))
    assert clean_tags(people + people[:1]) == people


def test_any_wording_of_a_crossing_counts():
    assert has_road_crossing(_tags("car", ROAD_CROSSING))
    assert has_road_crossing(_tags("crosswalk"))
    assert has_road_crossing(_tags("zebra stripes"))
    assert has_road_crossing(_tags("railway crossing"))


def test_a_road_alone_is_not_a_crossing():
    assert not has_road_crossing(_tags("road", "car", "pavement"))
