import re

from navigator.domain.geometry import SceneGeometry
from navigator.domain.guidance import GuidanceRequest
from navigator.domain.phrases import PHRASE_TEXT, PhraseId
from navigator.domain.tags import ROAD_CROSSING, clean_tags

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
        "Your job is the route: look 2 to 5 m ahead and say which way to go "
        "next.",
        "Answer with one short imperative of at most eight words. No "
        "preamble, no explanation, no distances unless they matter.",
        "When one of these phrase names fits, answer with the name alone:",
        *(f"{p.name} = {PHRASE_TEXT[p]}" for p in GUIDANCE_PHRASES),
        "Do not repeat a recent instruction unless the scene has changed.",
        "Your answer has two lines. The first is TAGS: then two to six short "
        "lowercase labels, comma separated, of what the camera sees that "
        "matters to a walker, for example pavement, person, car, stairs, "
        "door, bench. The second line is the instruction.",
        f"Use exactly the label '{ROAD_CROSSING}' whenever the way ahead "
        "crosses a road, crosswalk, zebra crossing, tram line or any lane "
        "where vehicles may pass, even when it looks empty. The depth data "
        "cannot see this danger, so then the instruction is ROAD_CROSSING "
        "and never GO_STRAIGHT or PATH_CLEAR.",
    ]
)

_ROWS = ("head", "torso", "legs")
_COLS = "far left, left, ahead, right, far right"
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
            f"Nearest surface per zone in metres. Columns: {_COLS}. "
            "Rows top to bottom. - means nothing within 10 m, ? means "
            "unreliable.",
            distance_grid(request.geometry),
            f"Recently said: {recent}",
        ]
    )


def split_tags(
    buffer: str, final: bool = False
) -> tuple[tuple[str, ...], str] | None:
    """Tags and the rest of the answer; None while the tags line is unfinished."""
    match = _TAGS_LINE.match(buffer)
    if match is None:
        return (), buffer
    if not match.group(2) and not final:
        return None
    return clean_tags(match.group(1).split(",")), buffer[match.end() :]


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
