import sys
from collections.abc import Callable

from navigator.bootstrap.config import Settings
from navigator.bootstrap.secrets import Secrets
from navigator.domain.phrases import PhraseId
from navigator.domain.tags import clean_tags
from navigator.ports.clock import Clock

Builder = Callable[[Settings, Clock, Secrets], object]


def _clock_system(settings, clock, secrets, resources):
    from navigator.adapters.clock.system import SystemClock

    return SystemClock()


def _clock_manual(settings, clock, secrets, resources):
    from navigator.adapters.clock.manual import ManualClock

    return ManualClock(start_ns=0)


def _frame_synthetic(settings, clock, secrets, resources):
    from navigator.adapters.camera.synthetic import SyntheticFrameSource

    return SyntheticFrameSource(
        clock=clock,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
    )


def _frame_webcam(settings, clock, secrets, resources):
    from navigator.adapters.camera.webcam import WebcamFrameSource

    return WebcamFrameSource(
        clock=clock,
        device=settings.camera_device,
        width=settings.camera_width,
        height=settings.camera_height,
        fps=settings.camera_fps,
        fourcc=settings.camera_fourcc,
    )


def _frame_replay(settings, clock, secrets, resources):
    from navigator.adapters.camera.replay import ReplayFrameSource

    return ReplayFrameSource(clock=clock, session_dir=settings.session_dir)


def _frame_phone(settings, clock, secrets, resources):
    from navigator.adapters.phone.camera import PhoneFrameSource

    return PhoneFrameSource(clock=clock, link=resources.phone_link)


def _perception_scripted(settings, clock, secrets, resources):
    from navigator.adapters.perception.scripted import ScriptedScenePerception

    return ScriptedScenePerception(
        clock=clock,
        rows=settings.grid_rows,
        cols=settings.grid_cols,
        horizontal_fov_deg=settings.hfov_deg,
        start_m=settings.scripted_start_m,
        speed_mps=settings.scripted_speed_mps,
    )


def _perception_gpu(settings, clock, secrets, resources):
    from navigator.adapters.perception.gpu import GpuScenePerception

    return GpuScenePerception(
        clock=clock,
        model=settings.perception_model,
        input_long_side=settings.input_long_side,
        rows=settings.grid_rows,
        cols=settings.grid_cols,
        horizontal_fov_deg=settings.hfov_deg,
        scale=settings.scale,
        mount_height_m=settings.mount_height_m,
        pitch_deg=settings.pitch_deg,
    )


def _perception_replay(settings, clock, secrets, resources):
    from navigator.adapters.perception.replay import ReplayScenePerception

    return ReplayScenePerception(clock=clock, session_dir=settings.session_dir)


def _reasoner_scripted(settings, clock, secrets, resources):
    from navigator.adapters.reasoner.scripted import ScriptedSceneReasoner

    phrase = (
        PhraseId[settings.reasoner_phrase]
        if settings.reasoner_phrase
        else None
    )
    return ScriptedSceneReasoner(
        text=settings.reasoner_text,
        phrase=phrase,
        delay_s=settings.reasoner_delay_s,
        tags=clean_tags(settings.reasoner_tags.split(",")),
    )


def _reasoner_gemini(settings, clock, secrets, resources):
    from navigator.adapters.reasoner.gemini import GeminiSceneReasoner

    return GeminiSceneReasoner(
        api_key=secrets.require("GEMINI_API_KEY"),
        model=settings.gemini_model,
        max_output_tokens=settings.gemini_max_output_tokens,
    )


def _synth_tone(settings, clock, secrets, resources):
    from navigator.adapters.speech.tone import ToneSpeechSynthesizer

    return ToneSpeechSynthesizer(
        delay_s=settings.tone_delay_s,
        seconds_per_char=settings.tone_seconds_per_char,
    )


def _synth_elevenlabs(settings, clock, secrets, resources):
    from navigator.adapters.speech.elevenlabs import (
        ElevenLabsSpeechSynthesizer,
    )

    return ElevenLabsSpeechSynthesizer(
        api_key=secrets.require("ELEVENLABS_API_KEY"),
        voice_id=secrets.require("ELEVENLABS_VOICE_ID"),
        model=settings.elevenlabs_model,
    )


def _audio_recording(settings, clock, secrets, resources):
    from navigator.adapters.audio.recording import RecordingAudioSink

    return RecordingAudioSink(clock=clock)


def _audio_wav(settings, clock, secrets, resources):
    from navigator.adapters.audio.wav import WavFileAudioSink

    return WavFileAudioSink(path=settings.wav_path)


def _audio_device(settings, clock, secrets, resources):
    from navigator.adapters.audio.device import SoundDeviceAudioSink

    return SoundDeviceAudioSink(
        device=settings.audio_device,
        block_frames=settings.audio_block_frames,
    )


def _audio_phone(settings, clock, secrets, resources):
    from navigator.adapters.phone.audio import PhoneAudioSink

    return PhoneAudioSink(clock=clock, link=resources.phone_link)


def _events_collecting(settings, clock, secrets, resources):
    from navigator.adapters.ui.collecting import CollectingEventPublisher

    return CollectingEventPublisher()


def _events_log(settings, clock, secrets, resources):
    from navigator.adapters.ui.log import LogEventPublisher

    return LogEventPublisher(stream=sys.stdout)


def _events_web(settings, clock, secrets, resources):
    from navigator.adapters.ui.web import WebEventPublisher

    return WebEventPublisher(host=settings.web_host, port=settings.web_port)


REGISTRY: dict[str, dict[str, Builder]] = {
    "clock": {
        "system": _clock_system,
        "manual": _clock_manual,
    },
    "frame_source": {
        "synthetic": _frame_synthetic,
        "webcam": _frame_webcam,
        "replay": _frame_replay,
        "phone": _frame_phone,
    },
    "scene_perception": {
        "scripted": _perception_scripted,
        "gpu": _perception_gpu,
        "replay": _perception_replay,
    },
    "scene_reasoner": {
        "scripted": _reasoner_scripted,
        "gemini": _reasoner_gemini,
    },
    "speech_synthesizer": {
        "tone": _synth_tone,
        "elevenlabs": _synth_elevenlabs,
    },
    "audio_sink": {
        "recording": _audio_recording,
        "wav": _audio_wav,
        "device": _audio_device,
        "phone": _audio_phone,
    },
    "event_publisher": {
        "collecting": _events_collecting,
        "log": _events_log,
        "web": _events_web,
    },
}


class Resources:
    def __init__(self) -> None:
        self.phone_link = None


def build(
    port: str,
    settings: Settings,
    clock: Clock,
    secrets: Secrets,
    resources: Resources,
):
    name = settings.adapters[port]
    try:
        builder = REGISTRY[port][name]
    except KeyError:
        raise ValueError(f"unknown {port} adapter {name!r}")
    return builder(settings, clock, secrets, resources)
