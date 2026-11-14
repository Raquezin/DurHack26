from dataclasses import dataclass

from navigator.domain.geometry import SceneGeometry
from navigator.domain.path import scene_changed


@dataclass(frozen=True, slots=True)
class TriggerSettings:
    min_interval_s: float = 2.0
    keepalive_s: float = 8.0
    max_age_s: float = 5.0
    change_ratio: float = 1.25
    change_fraction: float = 0.2
    stale_ratio: float = 1.6
    stale_fraction: float = 0.4
    max_m: float = 10.0


def scene_moved(
    before: SceneGeometry, after: SceneGeometry, settings: TriggerSettings
) -> bool:
    return scene_changed(
        before, after, settings.change_ratio, settings.change_fraction, settings.max_m
    )


def still_valid(
    asked: SceneGeometry, latest: SceneGeometry, settings: TriggerSettings
) -> bool:
    return not scene_changed(
        asked, latest, settings.stale_ratio, settings.stale_fraction, settings.max_m
    )


def should_request(
    now_ns: int,
    last_ns: int | None,
    last: SceneGeometry | None,
    current: SceneGeometry,
    settings: TriggerSettings,
) -> bool:
    if last_ns is None or last is None:
        return True
    elapsed_ns = now_ns - last_ns
    if elapsed_ns < settings.min_interval_s * 1e9:
        return False
    return elapsed_ns >= settings.keepalive_s * 1e9 or scene_moved(last, current, settings)
