import pytest

np = pytest.importorskip("numpy")
labeller = pytest.importorskip("navigator.adapters.reasoner.labeller")

from navigator.domain.tags import SceneTag

HEIGHT, WIDTH = 300, 500
NAMES = ("floor", "wall", "door", "person")
FLOOR, WALL, DOOR, PERSON = range(4)


def _extent(outline):
    xs, ys = zip(*outline)
    return min(xs), min(ys), max(xs), max(ys)


def test_outline_follows_the_largest_region_as_fractions():
    mask = np.zeros((HEIGHT, WIDTH), dtype=bool)
    mask[60:241, 300:401] = True
    mask[280:290, 10:20] = True
    assert _extent(labeller.outline(mask)) == pytest.approx((0.6, 0.2, 0.8, 0.8), abs=0.01)


def test_thin_slivers_are_smoothed_away():
    mask = np.zeros((HEIGHT, WIDTH), dtype=bool)
    mask[100:200, 100:200] = True
    mask[150:152, 200:400] = True
    assert _extent(labeller.outline(labeller.smoothed(mask))) == pytest.approx(
        (0.2, 1 / 3, 0.4, 2 / 3), abs=0.01
    )


def test_an_empty_mask_has_no_outline():
    assert labeller.outline(np.zeros((HEIGHT, WIDTH), dtype=bool)) == ()


def test_structure_is_outlined_and_the_rest_left_to_the_detector():
    labels = np.full((HEIGHT, WIDTH), FLOOR)
    labels[:151, :251] = WALL
    labels[100:250, 300:400] = PERSON
    labels[:20, 480:] = DOOR
    [wall] = labeller.structure_tags(labels, NAMES)
    assert wall.label == "wall"
    assert _extent(wall.outline) == pytest.approx((0.0, 0.0, 0.5, 0.5), abs=0.01)


BOX = [100.0, 100.0, 200.0, 200.0]


def _found(name, score, box=BOX):
    return {"class_name": name, "score": score, "box": box}


def _names(detections, limit=5):
    kept = labeller.prominent(detections, WIDTH, HEIGHT, limit)
    return [d["class_name"] for d in kept]


def test_only_confident_detections_are_kept_up_to_the_limit():
    detections = [
        _found("person", 0.9),
        _found("chair", 0.8),
        _found("bench", 0.7),
        _found("car", 0.3),
    ]
    assert _names(detections) == ["person", "chair", "bench"]
    assert _names(detections, limit=2) == ["person", "chair"]


def test_objects_a_walker_does_not_care_about_are_dropped():
    assert _names([_found("spoon", 0.9), _found("person", 0.9)]) == ["person"]


def test_small_distant_objects_are_dropped():
    assert _names([_found("person", 0.9, [100.0, 100.0, 120.0, 150.0])]) == []


def test_boxes_the_detector_garbled_are_dropped():
    garbled = (
        [181.8, 0.0, -0.0001, 154.5],
        [10.0, float("nan"), 300.0, 400.0],
        [10.0, 20.0, float("inf"), 400.0],
    )
    assert _names([_found("person", 0.9, box) for box in garbled]) == []


