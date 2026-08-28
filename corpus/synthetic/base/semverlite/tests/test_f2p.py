"""Fail-to-pass tests for pre-release ordering.

Many distinct version pairs, so passing requires implementing the ordering rule rather than
memorising a literal.
"""

import pytest

from semverlite import compare

PRERELEASE_CASES = [
    (("1.0.0-alpha", "1.0.0"), -1),
    (("1.0.0", "1.0.0-alpha"), 1),
    (("2.3.4-rc1", "2.3.4"), -1),
    (("2.3.4", "2.3.4-rc1"), 1),
    (("1.0.0-alpha", "1.0.0-beta"), -1),
    (("1.0.0-beta", "1.0.0-alpha"), 1),
    (("0.1.0-dev", "0.1.0"), -1),
    (("5.0.0-rc2", "5.0.0-rc1"), 1),
]


@pytest.mark.parametrize("pair,expected", PRERELEASE_CASES)
def test_prerelease_sorts_before_its_release(pair, expected):
    assert compare(*pair) == expected


RELEASE_CASES = [
    (("1.0.0", "1.0.1"), -1),
    (("2.0.0", "1.9.9"), 1),
    (("3.1.4", "3.1.4"), 0),
]


@pytest.mark.parametrize("pair,expected", RELEASE_CASES)
def test_ordinary_releases_are_unaffected(pair, expected):
    assert compare(*pair) == expected
