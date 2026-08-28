"""Held-out behavioural tests — never shown to any agent.

Attempt numbers the visible suite never uses, plus a monotonicity property that no table of
literals can satisfy by memorisation.
"""

import pytest

from retrylite import MAX_DELAY_SECONDS, backoff_delay

HIDDEN_CASES = [
    (10, 60.0),
    (11, 60.0),
    (15, 60.0),
    (26, 60.0),
    (41, 60.0),
    (4, 8.0),
    (5, 16.0),
]


@pytest.mark.parametrize("attempt,expected", HIDDEN_CASES)
def test_cap_generalises_to_unseen_attempts(attempt, expected):
    assert backoff_delay(attempt) == expected


def test_delay_never_decreases():
    delays = [backoff_delay(n) for n in range(1, 30)]
    assert all(b >= a for a, b in zip(delays, delays[1:]))


def test_bound_holds_across_a_wide_range():
    assert all(backoff_delay(n) <= MAX_DELAY_SECONDS for n in range(1, 200))


def test_invalid_attempt_still_raises():
    with pytest.raises(ValueError):
        backoff_delay(0)
