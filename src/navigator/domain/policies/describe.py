from dataclasses import dataclass

from navigator.domain.geometry import SceneGeometry
from navigator.domain.hazard import Bearing
from navigator.domain.path import below_head, in_path
from navigator.domain.policies.trigger import TriggerSettings, still_valid
from navigator.domain.tags import Outline, SceneTag

_PLACE = {
    Bearing.LEFT: "on your left",
    Bearing.AHEAD: "ahead",
    Bearing.RIGHT: "on your right",
}
_VOWELS = "aeiou"
_MAX_AGE_NS = 2_500_000_000
_SAMPLES_ACROSS = 2
_SAMPLES_DOWN = 4
_SURFACE_RATIO = 1.3
_MIN_SHARE = 0.25
_CLEAR_SHARE = 0.5


@dataclass(frozen=True, slots=True)
class TagMap:
    asked: SceneGeometry
    tags: tuple[SceneTag, ...]
    coverage: tuple[tuple[float, ...], ...]


def _noun(label: str) -> str:
    if label == "person":
        return "someone"
    article = "an" if label[:1] in _VOWELS else "a"
    return f"{article} {label}"


def describe(tag: SceneTag, bearing: Bearing) -> str:
    return f"{_noun(tag.label).capitalize()} {_PLACE[bearing]}."


def _inside(outline: Outline, x: float, y: float) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(outline, outline[1:] + outline[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _coverage(outline: Outline, geometry: SceneGeometry) -> tuple[float, ...]:
    if not outline:
        return (0.0,) * (geometry.rows * geometry.cols)
    xs = [x for x, _ in outline]
    ys = [y for _, y in outline]
    width, height = 1 / geometry.cols, 1 / geometry.rows
    samples = _SAMPLES_ACROSS * _SAMPLES_DOWN
    shares = []
    for row in range(geometry.rows):
        for col in range(geometry.cols):
            left, top = col * width, row * height
            if (
                min(xs) >= left + width
                or max(xs) <= left
                or min(ys) >= top + height
                or max(ys) <= top
            ):
                shares.append(0.0)
                continue
            hits = sum(
                _inside(
                    outline,
                    left + (i + 0.5) * width / _SAMPLES_ACROSS,
                    top + (j + 0.5) * height / _SAMPLES_DOWN,
                )
                for i in range(_SAMPLES_ACROSS)
                for j in range(_SAMPLES_DOWN)
            )
            shares.append(hits / samples)
    return tuple(shares)


def tag_map(asked: SceneGeometry, tags: tuple[SceneTag, ...]) -> TagMap:
    return TagMap(asked, tags, tuple(_coverage(tag.outline, asked) for tag in tags))


def usable(
    marked: TagMap | None, latest: SceneGeometry, settings: TriggerSettings
) -> bool:
    if marked is None:
        return False
    if latest.t_capture_ns - marked.asked.t_capture_ns > _MAX_AGE_NS:
        return False
    return still_valid(marked.asked, latest, settings)


def _surface(
    geometry: SceneGeometry, distance_m: float, half_width_m: float
) -> list[int]:
    zones = []
    for row in below_head(geometry):
        for col in range(geometry.cols):
            i = row * geometry.cols + col
            d = geometry.distances_m[i]
            if (
                geometry.valid[i]
                and d <= distance_m * _SURFACE_RATIO
                and in_path(geometry, col, d, half_width_m)
            ):
                zones.append(i)
    return zones


def blocker_tag(
    marked: TagMap | None,
    geometry: SceneGeometry,
    zone: tuple[float, int, int],
    half_width_m: float,
    settings: TriggerSettings,
) -> SceneTag | None:
    if not usable(marked, geometry, settings):
        return None
    surface = _surface(geometry, zone[0], half_width_m)
    found = []
    for tag, coverage in zip(marked.tags, marked.coverage):
        share = sum(coverage[i] for i in surface) / len(surface)
        if share >= _MIN_SHARE:
            found.append((share, sum(coverage), tag))
    if not found:
        return None
    clear = [item for item in found if item[0] >= _CLEAR_SHARE]
    if clear:
        return min(clear, key=lambda item: item[1])[2]
    return max(found, key=lambda item: item[0])[2]
