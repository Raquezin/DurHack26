import json
import threading

from navigator.adapters.ui.serialize import event_to_json
from navigator.domain.events import Event


class LogEventPublisher:
    def __init__(self, stream) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def publish(self, event: Event) -> None:
        try:
            line = json.dumps(event_to_json(event))
        except (TypeError, ValueError):
            return
        try:
            with self._lock:
                self._stream.write(line + "\n")
                self._stream.flush()
        except (OSError, ValueError):
            pass
