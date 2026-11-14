from navigator.domain.policies.trigger import TriggerSettings, should_request

S = TriggerSettings(interval_s=1.5)


def test_first_request_after_interval_from_zero():
    assert should_request(2_000_000_000, 0, False, S)


def test_interval_elapsed():
    last = 1_000_000_000
    now = last + 1_500_000_000
    assert should_request(now, last, False, S)


def test_interval_not_elapsed():
    last = 1_000_000_000
    now = last + 1_000_000_000
    assert not should_request(now, last, False, S)


def test_in_flight_blocks():
    last = 0
    now = 10_000_000_000
    assert not should_request(now, last, True, S)
