from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...
