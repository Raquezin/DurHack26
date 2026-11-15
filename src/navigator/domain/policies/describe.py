from navigator.domain.hazard import Bearing
from navigator.domain.tags import SceneTag

_REGION = {
    Bearing.LEFT: (0.0, 1 / 3),
    Bearing.AHEAD: (1 / 3, 2 / 3),
    Bearing.RIGHT: (2 / 3, 1.0),
}
_PLACE = {
    Bearing.LEFT: "on your left",
    Bearing.AHEAD: "ahead",
    Bearing.RIGHT: "on your right",
}
_VOWELS = "aeiou"


def _noun(label: str) -> str:
    if label == "person":
        return "someone"
    article = "an" if label[:1] in _VOWELS else "a"
    return f"{article} {label}"


def describe(tags: tuple[SceneTag, ...], bearing: Bearing) -> str | None:
    lo, hi = _REGION[bearing]
    found = [
        tag
        for tag in tags
        if tag.outline
        and min(x for x, _ in tag.outline) < hi
        and max(x for x, _ in tag.outline) > lo
    ]
    if not found:
        return None
    tag = max(found, key=lambda t: max(y for _, y in t.outline))
    return f"{_noun(tag.label).capitalize()} {_PLACE[bearing]}."
