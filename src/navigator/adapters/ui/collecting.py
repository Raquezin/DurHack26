import threading

from navigator.domain.events import Event


class CollectingEventPublisher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[Event] = []

    def publish(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)

    @property
    def events(self) -> list[Event]:
        with self._lock:
            return list(self._events)
