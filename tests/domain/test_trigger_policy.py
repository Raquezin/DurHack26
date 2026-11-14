from navigator.adapters.clock.manual import ManualClock
from navigator.domain.policies.trigger import TriggerSettings, should_request

S = TriggerSettings(interval_s=1.5)


def test_first_request_fires_immediately():
    assert should_request(ManualClock().now_ns(), None, S)


def test_interval_elapsed():
    clock = ManualClock(start_ns=1_000_000_000)
    last = clock.now_ns()
    clock.advance(1_500_000_000)
    assert should_request(clock.now_ns(), last, S)


def test_interval_not_elapsed():
    clock = ManualClock(start_ns=1_000_000_000)
    last = clock.now_ns()
    clock.advance(1_499_999_999)
    assert not should_request(clock.now_ns(), last, S)


def test_fixed_cadence_over_time():
    clock = ManualClock()
    last = None
    fired = []
    for _ in range(40):
        if should_request(clock.now_ns(), last, S):
            last = clock.now_ns()
            fired.append(last)
        clock.advance(100_000_000)
    assert fired == [0, 1_500_000_000, 3_000_000_000]


def test_abandon_defaults_to_one_second():
    assert TriggerSettings().abandon_s == 1.0
