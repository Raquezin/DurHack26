import time


class SystemClock:
    def now_ns(self) -> int:
        return time.monotonic_ns()
