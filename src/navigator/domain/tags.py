from collections.abc import Iterable

ROAD_CROSSING = "road crossing"
MAX_TAGS = 6
MAX_TAG_CHARS = 24
_CROSSING_WORDS = ("crossing", "crosswalk", "zebra")


def clean_tags(raw: Iterable[str]) -> tuple[str, ...]:
    tags: list[str] = []
    for item in raw:
        tag = " ".join(item.lower().split()).strip(".")[:MAX_TAG_CHARS].strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tuple(tags[:MAX_TAGS])


def has_road_crossing(tags: Iterable[str]) -> bool:
    return any(word in tag for tag in tags for word in _CROSSING_WORDS)
