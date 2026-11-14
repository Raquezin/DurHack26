from navigator.domain.policies.arbitration import is_stale, preempts
from navigator.domain.speech import Priority, Utterance


def utt(priority=Priority.GUIDANCE, deadline=1_000):
    return Utterance(
        priority=priority,
        phrase=None,
        text="x",
        frame_id=0,
        t_capture_ns=0,
        deadline_ns=deadline,
    )


def test_stale_after_deadline():
    assert is_stale(utt(deadline=100), 101)
    assert not is_stale(utt(deadline=100), 100)


def test_hazard_preempts_guidance():
    assert preempts(Priority.HAZARD, Priority.GUIDANCE)
    assert not preempts(Priority.GUIDANCE, Priority.HAZARD)
    assert not preempts(Priority.GUIDANCE, Priority.GUIDANCE)
