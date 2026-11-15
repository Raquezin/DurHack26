import re

from navigator.domain.geometry import SceneGeometry
from navigator.domain.guidance import GuidanceRequest
from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.tags import ROAD_CROSSING, SceneTag, clean_tags

GUIDANCE_PHRASES = (
    PhraseId.GO_STRAIGHT,
    PhraseId.VEER_LEFT,
    PhraseId.VEER_RIGHT,
    PhraseId.TURN_LEFT,
    PhraseId.TURN_RIGHT,
    PhraseId.PATH_CLEAR,
    PhraseId.SLOW_DOWN,
    PhraseId.DOOR_AHEAD,
    PhraseId.ROAD_CROSSING,
)

SYSTEM_PROMPT = "\n".join(
    [
        "You guide a blind pedestrian who walks with a chest-mounted camera "
        "and hears your words through headphones.",
        "A local system already warns about every obstacle nearer than 2 m. "
        "Do not talk about those.",
        "Your job is the route 2 to 5 m ahead: say how far the walker can "
        "keep going, and name a direction only when the way ahead is closing "
        "or something new blocks it — never while the current direction "
        "still works.",
        "Answer with one short imperative of at most eight words. No "
        "preamble, no explanation.",
        "On an open path say \"Continue for N metres\" with N the metres "
        "ahead. When one of these phrase names fits, answer with the name "
        "alone:",
        *(f"{p.name} = {PHRASE_TEXT[p]}" for p in GUIDANCE_PHRASES),
        "Do not repeat a recent instruction unless the scene has changed.",
        "Your answer has two lines. The first is TAGS: then two to six short "
        "lowercase labels, comma separated, of what the camera sees that "
        "matters to a walker. After each label write @ and where it is in "
        "the picture: its row (head, torso or legs) then its column (far "
        "left, left, ahead, right or far right), for example table@legs "
        "left, person@torso ahead, wall@head far right, door@torso right. "
        "The second line is the instruction.",
        f"Use exactly the label '{ROAD_CROSSING}' whenever the way ahead "
        "crosses a road, crosswalk, zebra crossing, tram line or any lane "
        "where vehicles may pass, even when it looks empty. The depth data "
        "cannot see this danger, so then the instruction is ROAD_CROSSING "
        "and never GO_STRAIGHT or PATH_CLEAR.",
    ]
)

_ROWS = ("head", "torso", "legs")
_COL_NAMES = ("far left", "left", "ahead", "right", "far right")
_TERMINATOR = re.compile(r"[.!?](?=\s)|(?<!\d)[.!?]$")
_IDENTIFIER = re.compile(r"[A-Z]+(?:_[A-Z]+)+")
_BY_TEXT = {text.casefold(): p for p, text in PHRASE_TEXT.items()}
_TAGS_LINE = re.compile(r"\s*tags\s*:\s*([^\n]*)(\n|$)", re.IGNORECASE)


def _cell(distance_m: float, valid: bool) -> str:
    if not valid:
        return "?"
    if distance_m == float("inf"):
        return "-"
    return f"{distance_m:.1f}"


def distance_grid(geometry: SceneGeometry) -> str:
    names = _ROWS if geometry.rows == len(_ROWS) else range(geometry.rows)
    lines = []
    for row, name in enumerate(names):
        start = row * geometry.cols
        cells = zip(
            geometry.distances_m[start : start + geometry.cols],
            geometry.valid[start : start + geometry.cols],
        )
        lines.append(f"{name}: " + " ".join(_cell(d, v) for d, v in cells))
    return "\n".join(lines)


def user_text(request: GuidanceRequest) -> str:
    recent = " | ".join(request.recently_spoken) or "nothing"
    return "\n".join(
        [
            "Nearest surface per zone in metres. Columns run from far left "
            "to far right. "
            "Rows top to bottom. - means nothing within 10 m, ? means "
            "unreliable.",
            distance_grid(request.geometry),
            f"Recently said: {recent}",
        ]
    )


def _tag(item: str) -> SceneTag:
    label, _, place = item.partition("@")
    row, _, col = " ".join(place.lower().split()).strip(".").partition(" ")
    if row in _ROWS and col in _COL_NAMES:
        top, left = _ROWS.index(row), _COL_NAMES.index(col)
        rows, cols = len(_ROWS), len(_COL_NAMES)
        x0, x1 = left / cols, (left + 1) / cols
        y0, y1 = top / rows, (top + 1) / rows
        return SceneTag(label, ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
    return SceneTag(label)


def parse_tags(line: str) -> tuple[SceneTag, ...]:
    return clean_tags(_tag(item) for item in line.split(","))


def split_tags(
    buffer: str, final: bool = False
) -> tuple[tuple[SceneTag, ...], str] | None:
    match = _TAGS_LINE.match(buffer)
    if match is None:
        return (), buffer
    if not match.group(2) and not final:
        return None
    return parse_tags(match.group(1)), buffer[match.end() :]


def first_sentence(buffer: str) -> str | None:
    match = _TERMINATOR.search(buffer)
    return buffer[: match.end()].strip() if match else None


def parse_answer(answer: str) -> tuple[PhraseId | None, str] | None:
    sentence = " ".join(answer.split())
    name = sentence.strip("`*\"' .").upper()
    if name in PhraseId.__members__:
        phrase = PhraseId[name]
        return phrase, PHRASE_TEXT[phrase]
    if _IDENTIFIER.fullmatch(name):
        return None
    if sentence.casefold() in _BY_TEXT:
        phrase = _BY_TEXT[sentence.casefold()]
        return phrase, PHRASE_TEXT[phrase]
    return (None, sentence) if sentence else None
