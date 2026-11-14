import pytest

from navigator.adapters.clock.manual import ManualClock
from navigator.adapters.clock.system import SystemClock

FACTORIES = [SystemClock, ManualClock]


@pytest.mark.parametrize("factory", FACTORIES)
def test_now_ns_returns_int(factory):
    clock = factory()
    assert isinstance(clock.now_ns(), int)


@pytest.mark.parametrize("factory", FACTORIES)
def test_now_ns_monotonic(factory):
    clock = factory()
    if isinstance(clock, ManualClock):
        clock.advance(5)
    first = clock.now_ns()
    second = clock.now_ns()
    assert second >= first
