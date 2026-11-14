from navigator.domain.tags import (
    MAX_TAG_CHARS,
    MAX_TAGS,
    ROAD_CROSSING,
    clean_tags,
    has_road_crossing,
)


def test_clean_lowercases_trims_and_drops_duplicates():
    assert clean_tags([" Car ", "car", "Bus.", "", "  "]) == ("car", "bus")


def test_clean_collapses_inner_whitespace():
    assert clean_tags(["Road   Crossing"]) == (ROAD_CROSSING,)


def test_clean_limits_count_and_length():
    many = [f"tag{i}" for i in range(MAX_TAGS + 3)]
    assert len(clean_tags(many)) == MAX_TAGS
    assert len(clean_tags(["x" * 100])[0]) == MAX_TAG_CHARS


def test_any_wording_of_a_crossing_counts():
    assert has_road_crossing(("car", ROAD_CROSSING))
    assert has_road_crossing(("crosswalk",))
    assert has_road_crossing(("zebra stripes",))
    assert has_road_crossing(("railway crossing",))


def test_a_road_alone_is_not_a_crossing():
    assert not has_road_crossing(("road", "car", "pavement"))
