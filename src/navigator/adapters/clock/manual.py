class ManualClock:
    def __init__(self, start_ns: int = 0) -> None:
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    def advance(self, ns: int) -> None:
        self._now += ns
