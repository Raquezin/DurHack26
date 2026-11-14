from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TriggerSettings:
    interval_s: float = 1.5
    abandon_s: float = 1.0


def should_request(
    now_ns: int, last_request_ns: int | None, settings: TriggerSettings
) -> bool:
    if last_request_ns is None:
        return True
    return now_ns - last_request_ns >= int(settings.interval_s * 1_000_000_000)
