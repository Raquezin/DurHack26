from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TriggerSettings:
    interval_s: float = 1.5


def should_request(
    now_ns: int,
    last_request_ns: int,
    in_flight: bool,
    settings: TriggerSettings,
) -> bool:
    if in_flight:
        return False
    return now_ns - last_request_ns >= int(settings.interval_s * 1_000_000_000)
