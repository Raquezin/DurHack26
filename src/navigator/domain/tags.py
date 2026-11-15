from collections.abc import Iterable
from dataclasses import dataclass

ROAD_CROSSING = "road crossing"
MAX_TAGS = 24
MAX_TAG_CHARS = 24
_CROSSING_WORDS = ("crossing", "crosswalk", "zebra")

Outline = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class SceneTag:
    label: str
    outline: Outline = ()


def clean_tags(raw: Iterable[SceneTag]) -> tuple[SceneTag, ...]:
    tags: list[SceneTag] = []
    for item in raw:
        label = " ".join(item.label.lower().split()).strip(".")
        tag = SceneTag(label[:MAX_TAG_CHARS].strip(), item.outline)
        if tag.label and tag not in tags:
            tags.append(tag)
    return tuple(tags[:MAX_TAGS])


def has_road_crossing(tags: Iterable[SceneTag]) -> bool:
    return any(word in tag.label for tag in tags for word in _CROSSING_WORDS)
