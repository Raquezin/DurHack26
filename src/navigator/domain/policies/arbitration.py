from navigator.domain.speech import Priority, Utterance


def is_stale(utterance: Utterance, now_ns: int) -> bool:
    return now_ns > utterance.deadline_ns


def preempts(new_priority: Priority, playing_priority: Priority) -> bool:
    return new_priority < playing_priority
