from enum import Enum


class PhraseId(Enum):
    STOP = "stop"
    CAUTION_AHEAD = "caution_ahead"
    CAUTION_LEFT = "caution_left"
    CAUTION_RIGHT = "caution_right"
    VEER_LEFT = "veer_left"
    VEER_RIGHT = "veer_right"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    GO_STRAIGHT = "go_straight"
    PATH_CLEAR = "path_clear"
    SLOW_DOWN = "slow_down"
    DOOR_AHEAD = "door_ahead"
    ROAD_CROSSING = "road_crossing"


PHRASE_TEXT = {
    PhraseId.STOP: "Stop.",
    PhraseId.CAUTION_AHEAD: "Careful, obstacle ahead.",
    PhraseId.CAUTION_LEFT: "Obstacle on your left.",
    PhraseId.CAUTION_RIGHT: "Obstacle on your right.",
    PhraseId.VEER_LEFT: "Move a little left.",
    PhraseId.VEER_RIGHT: "Move a little right.",
    PhraseId.TURN_LEFT: "Turn left.",
    PhraseId.TURN_RIGHT: "Turn right.",
    PhraseId.GO_STRAIGHT: "Keep going straight.",
    PhraseId.PATH_CLEAR: "Path is clear.",
    PhraseId.SLOW_DOWN: "Slow down.",
    PhraseId.DOOR_AHEAD: "Door ahead.",
    PhraseId.ROAD_CROSSING: "Road crossing ahead. Stop.",
}
