import dataclasses
import enum
import json
import math
import threading

from navigator.domain.events import Event, PreviewEvent


class LogEventPublisher:
    def __init__(self, stream) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def publish(self, event: Event) -> None:
        line = json.dumps(self._to_json(event))
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def _to_json(self, event: Event) -> dict:
        if isinstance(event, PreviewEvent):
            return {
                "type": event.type,
                "kind": event.kind.value,
                "frame_id": event.frame_id,
                "jpeg_bytes": len(event.jpeg),
            }
        payload = {"type": event.type}
        for field in dataclasses.fields(event):
            payload[field.name] = self._value(getattr(event, field.name))
        return payload

    def _value(self, value):
        if isinstance(value, enum.Enum):
            return value.value
        if isinstance(value, float) and math.isinf(value):
            return None
        if isinstance(value, (tuple, list)):
            return [self._value(v) for v in value]
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                f.name: self._value(getattr(value, f.name))
                for f in dataclasses.fields(value)
            }
        return value
