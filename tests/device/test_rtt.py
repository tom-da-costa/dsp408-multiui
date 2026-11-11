"""Adaptive command timeout."""

import pytest

from tracks_dsp_controller.device.rtt import RttEstimator


def test_starts_at_the_floor_and_stays_there_on_a_fast_link() -> None:
    rtt = RttEstimator(0.5, 5.0)
    assert rtt.timeout == 0.5
    for _ in range(20):
        rtt.sample(0.01)
    assert rtt.timeout == 0.5


def test_follows_a_slow_link_up_to_the_ceiling() -> None:
    rtt = RttEstimator(0.5, 5.0)
    for _ in range(20):
        rtt.sample(0.8)
    assert 0.8 < rtt.timeout < 1.5
    for _ in range(20):
        rtt.sample(30.0)
    assert rtt.timeout == 5.0


def test_a_timeout_doubles_it_until_the_next_answer() -> None:
    rtt = RttEstimator(0.5, 5.0)
    rtt.timed_out()
    assert rtt.timeout == 1.0
    rtt.timed_out()
    assert rtt.timeout == 2.0
    for _ in range(5):
        rtt.timed_out()
    assert rtt.timeout == 5.0
    rtt.sample(0.01)
    assert rtt.timeout == 0.5


def test_jitter_widens_it() -> None:
    steady, jittery = RttEstimator(0.1, 5.0), RttEstimator(0.1, 5.0)
    for i in range(40):
        steady.sample(0.3)
        jittery.sample(0.1 if i % 2 else 0.5)
    assert jittery.timeout > steady.timeout


def test_bounds_are_checked() -> None:
    with pytest.raises(ValueError, match="floor"):
        RttEstimator(0.0, 1.0)
    with pytest.raises(ValueError, match="floor"):
        RttEstimator(2.0, 1.0)
