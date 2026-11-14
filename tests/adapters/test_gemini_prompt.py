import json
import math
from pathlib import Path

from navigator.adapters.reasoner.prompt import (
    GUIDANCE_PHRASES,
    SYSTEM_PROMPT,
    distance_grid,
    first_sentence,
    parse_answer,
    split_tags,
    user_text,
)
from navigator.domain.geometry import SceneGeometry
from navigator.domain.guidance import GuidanceRequest
from navigator.domain.phrases import PHRASE_TEXT, PhraseId

SCENES = Path(__file__).resolve().parents[2] / "fixtures" / "scenes"


def _geometry(name):
    data = json.loads((SCENES / f"{name}.json").read_text())
    return SceneGeometry(
        frame_id=data["frame_id"],
        t_capture_ns=data["t_capture_ns"],
        rows=data["rows"],
        cols=data["cols"],
        distances_m=tuple(math.inf if d is None else d for d in data["distances_m"]),
        valid=tuple(data["valid"]),
        horizontal_fov_deg=data["horizontal_fov_deg"],
    )


def test_system_prompt_states_division_of_labour():
    assert "nearer than 2 m" in SYSTEM_PROMPT
    assert "2 to 5 m" in SYSTEM_PROMPT
    assert "one short imperative" in SYSTEM_PROMPT
    for phrase in GUIDANCE_PHRASES:
        assert f"{phrase.name} = {PHRASE_TEXT[phrase]}" in SYSTEM_PROMPT
    assert "STOP" not in SYSTEM_PROMPT


def test_grid_rows_inf_and_invalid():
    assert distance_grid(_geometry("obstacle_left")).splitlines() == [
        "head: 2.8 4.1 - 4.0 ?",
        "torso: 2.7 2.6 - 4.1 2.7",
        "legs: 2.8 2.6 2.6 4.1 2.8",
    ]


def test_user_text_has_legend_grid_and_recent():
    request = GuidanceRequest(
        geometry=_geometry("doorway"),
        camera_jpeg=b"",
        recently_spoken=("Door ahead.", "Keep going straight."),
    )
    text = user_text(request)
    assert "far left, left, ahead, right, far right" in text
    assert "- means nothing within 10 m" in text
    assert "? means unreliable" in text
    assert "head: 2.8 4.1 4.1 4.1 2.8" in text
    assert text.endswith("Recently said: Door ahead. | Keep going straight.")


def test_user_text_without_recent():
    request = GuidanceRequest(
        geometry=_geometry("doorway"), camera_jpeg=b"", recently_spoken=()
    )
    assert user_text(request).endswith("Recently said: nothing")


def test_first_sentence():
    assert first_sentence("Turn") is None
    assert first_sentence("Turn left") is None
    assert first_sentence("Turn left.") == "Turn left."
    assert first_sentence(" Bear left! Then go") == "Bear left!"
    assert first_sentence("Door in 3.") is None
    assert first_sentence("Door in 3. Go") == "Door in 3."
    assert first_sentence("Door in 3.5") is None
    assert first_sentence("TURN_RIGHT") is None


def test_parse_phrase_names():
    assert parse_answer("TURN_RIGHT") == (PhraseId.TURN_RIGHT, "Turn right.")
    assert parse_answer(" `door_ahead`\n") == (PhraseId.DOOR_AHEAD, "Door ahead.")
    assert parse_answer("PATH_CLEAR.") == (PhraseId.PATH_CLEAR, "Path is clear.")


def test_parse_catalogue_text_maps_to_phrase():
    assert parse_answer("turn left.") == (PhraseId.TURN_LEFT, "Turn left.")


def test_parse_free_sentence():
    assert parse_answer("  Bear right   around the bench. ") == (
        None,
        "Bear right around the bench.",
    )


def test_parse_unknown_identifier_is_not_spoken():
    assert parse_answer("STOP_SLOW_DOWN") is None


def test_parse_empty():
    assert parse_answer("") is None
    assert parse_answer("  \n") is None


def test_split_tags_waits_for_the_end_of_the_line():
    assert split_tags("TAGS: car, road cross") is None
    assert split_tags("TAGS:") is None
    assert split_tags("TA") == ((), "TA")


def test_split_tags_then_instruction():
    assert split_tags("TAGS: Pavement, Car.\nTurn left.") == (
        ("pavement", "car"),
        "Turn left.",
    )
    assert split_tags("tags : door\nDOOR_AHEAD") == (("door",), "DOOR_AHEAD")


def test_split_tags_without_a_tags_line_keeps_the_answer():
    assert split_tags("Turn left.") == ((), "Turn left.")


def test_split_tags_final_accepts_an_unfinished_line():
    assert split_tags("TAGS: stairs", final=True) == (("stairs",), "")


def test_prompt_asks_for_tags_and_names_the_road_crossing_label():
    assert "TAGS:" in SYSTEM_PROMPT
    assert "'road crossing'" in SYSTEM_PROMPT
    assert "ROAD_CROSSING" in SYSTEM_PROMPT