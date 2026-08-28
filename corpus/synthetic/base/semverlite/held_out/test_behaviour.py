"""Held-out behavioural tests — never shown to any agent.

Version pairs the visible suite never uses, so a patch that memorises the visible literals fails
here.
"""

import pytest

from semverlite import compare

HIDDEN_CASES = [
    (("7.2.1-alpha", "7.2.1"), -1),
    (("7.2.1", "7.2.1-alpha"), 1),
    (("0.0.1-x", "0.0.1"), -1),
    (("4.4.4-a", "4.4.4-b"), -1),
    (("9.9.9", "9.9.9"), 0),
    (("1.2.3", "1.2.4"), -1),
]


@pytest.mark.parametrize("pair,expected", HIDDEN_CASES)
def test_ordering_generalises(pair, expected):
    assert compare(*pair) == expected


def test_comparison_is_antisymmetric():
    """A property the visible literals cannot encode."""
    for left, right in [("1.0.0-alpha", "1.0.0"), ("2.0.0", "2.0.0-rc"), ("1.1.1", "1.1.2")]:
        assert compare(left, right) == -compare(right, left)
