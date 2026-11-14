from typing import Protocol

from navigator.domain.events import Event


class EventPublisher(Protocol):
    def publish(self, event: Event) -> None: ...
