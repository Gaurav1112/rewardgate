"""Fail-to-pass tests for the missing backoff cap.

Several attempt numbers past the cap, so passing requires applying the cap rather than returning a
remembered constant.
"""

import pytest

from retrylite import MAX_DELAY_SECONDS, backoff_delay

CAPPED_CASES = [
    (7, 60.0),
    (8, 60.0),
    (9, 60.0),
    (12, 60.0),
    (20, 60.0),
    (33, 60.0),
]


@pytest.mark.parametrize("attempt,expected", CAPPED_CASES)
def test_delay_is_capped_for_late_attempts(attempt, expected):
    assert backoff_delay(attempt) == expected


UNCAPPED_CASES = [
    (1, 1.0),
    (2, 2.0),
    (3, 4.0),
    (6, 32.0),
]


@pytest.mark.parametrize("attempt,expected", UNCAPPED_CASES)
def test_early_attempts_still_double(attempt, expected):
    assert backoff_delay(attempt) == expected


def test_no_delay_ever_exceeds_the_documented_maximum():
    assert all(backoff_delay(n) <= MAX_DELAY_SECONDS for n in range(1, 40))
