import dataclasses
import enum
import math

from navigator.domain.events import Event, PreviewEvent, PreviewKind

_PREVIEW_BYTES = {PreviewKind.CAMERA: 1, PreviewKind.DEPTH: 2}


def event_to_json(event: Event) -> dict:
    if isinstance(event, PreviewEvent):
        return {
            "type": event.type,
            "kind": event.kind.value,
            "frame_id": event.frame_id,
            "jpeg_bytes": len(event.jpeg),
        }
    payload = {"type": event.type}
    for field in dataclasses.fields(event):
        payload[field.name] = _value(getattr(event, field.name))
    return payload


def event_to_preview_bytes(event: PreviewEvent) -> bytes:
    header = bytes([_PREVIEW_BYTES[event.kind]]) + event.frame_id.to_bytes(
        8, "big"
    )
    return header + event.jpeg


def _value(value):
    if isinstance(value, enum.IntEnum):
        return value.name.lower()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, float) and math.isinf(value):
        return None
    if isinstance(value, (tuple, list)):
        return [_value(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _value(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    return value
