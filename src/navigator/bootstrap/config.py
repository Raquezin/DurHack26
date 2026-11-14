from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    adapters: dict[str, str] = field(default_factory=dict)
    camera_device: int = 0
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    camera_fourcc: str = "MJPG"
    hfov_deg: float = 58.0
    grid_rows: int = 3
    grid_cols: int = 5
    perception_model: str = "da3metric-large"
    input_long_side: int = 504
    scale: float = 1.0
    mount_height_m: float = 1.4
    pitch_deg: float = 0.0
    session_dir: Path = Path("fixtures/sessions/default")
    scripted_start_m: float = 4.0
    scripted_speed_mps: float = 0.5
    reasoner_text: str = "Keep going straight."
    reasoner_phrase: str | None = "GO_STRAIGHT"
    reasoner_delay_s: float = 0.2
    reasoner_tags: str = "pavement, wall"
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_max_output_tokens: int = 64
    elevenlabs_model: str = "eleven_flash_v2_5"
    tone_delay_s: float = 0.05
    tone_seconds_per_char: float = 0.03
    audio_device: int | None = None
    audio_block_frames: int = 240
    wav_path: Path = Path("out/speech.wav")
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    phone_host: str = "127.0.0.1"
    phone_port: int = 8001
    stop_m: float = 1.2
    caution_m: float = 2.0
    path_half_width_m: float = 0.4
    hazard_confirm_frames: int = 2
    trigger_min_interval_s: float = 2.0
    trigger_keepalive_s: float = 8.0
    guidance_max_age_s: float = 5.0
    steering_look_m: float = 3.0
    deadline_offset_ms: float = 0.0
    preview_every: int = 1
    hazard_phrase_cooldown_s: float = 2.0
    guidance_phrase_cooldown_s: float = 5.0
    phrase_cache_dir: Path = Path("out/phrase_cache")
    timing_window: int = 600
    timing_interval_s: float = 1.0


PRESETS = {
    "all-fakes": {
        "clock": "system",
        "frame_source": "synthetic",
        "scene_perception": "scripted",
        "scene_reasoner": "scripted",
        "speech_synthesizer": "tone",
        "audio_sink": "recording",
        "event_publisher": "log",
    },
    "replay": {
        "clock": "system",
        "frame_source": "replay",
        "scene_perception": "replay",
        "scene_reasoner": "scripted",
        "speech_synthesizer": "tone",
        "audio_sink": "recording",
        "event_publisher": "log",
    },
    "live": {
        "clock": "system",
        "frame_source": "webcam",
        "scene_perception": "gpu",
        "scene_reasoner": "gemini",
        "speech_synthesizer": "elevenlabs",
        "audio_sink": "device",
        "event_publisher": "web",
    },
    "phone": {
        "clock": "system",
        "frame_source": "phone",
        "scene_perception": "gpu",
        "scene_reasoner": "gemini",
        "speech_synthesizer": "elevenlabs",
        "audio_sink": "phone",
        "event_publisher": "web",
    },
    "video": {
        "clock": "system",
        "frame_source": "replay",
        "scene_perception": "gpu",
        "scene_reasoner": "gemini",
        "speech_synthesizer": "elevenlabs",
        "audio_sink": "wav",
        "event_publisher": "web",
    },
    "live-offline": {
        "clock": "system",
        "frame_source": "webcam",
        "scene_perception": "gpu",
        "scene_reasoner": "scripted",
        "speech_synthesizer": "tone",
        "audio_sink": "device",
        "event_publisher": "web",
    },
}


def resolve(preset: str, overrides: dict[str, str]) -> Settings:
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}")
    adapters = dict(PRESETS[preset])
    adapters.update(overrides)
    return Settings(adapters=adapters)


def apply_overrides(settings: Settings, pairs: list[str]) -> Settings:
    import typing

    hints = typing.get_type_hints(Settings)
    values = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        if key not in hints:
            raise ValueError(f"unknown setting {key!r}")
        values[key] = _convert(raw, hints[key])
    return replace(settings, **values)


def _convert(raw: str, hint):
    import types
    import typing

    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        if raw.lower() in ("none", ""):
            return None
        return _convert(raw, args[0])
    if hint is bool:
        return raw.lower() in ("1", "true", "yes", "on")
    if hint is Path:
        return Path(raw)
    if hint is int:
        return int(raw)
    if hint is float:
        return float(raw)
    return raw
