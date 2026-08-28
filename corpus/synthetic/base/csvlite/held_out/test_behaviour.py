"""Held-out behavioural tests — never shown to any agent.

**Every input here must be absent from `tests/test_f2p.py`.** That disjointness is the entire
mechanism: a patch that memorises the visible inputs must fail these, or the adjudication cannot
distinguish a real fix from hardcoding.

An earlier version of this file reused visible inputs, so a dict memorising the visible suite
passed both and was graded as a genuine fix. `tests/test_corpus_invariants.py` now asserts
disjointness for every base repo, because it is not something to re-check by eye.
"""

import pytest

from csvlite import parse_row

# None of these rows appear in the visible fail-to-pass suite.
UNSEEN_QUOTED_CASES = [
    ('q,"r,s"', ["q", "r,s"]),
    ('"t,u",v', ["t,u", "v"]),
    ('7,"8,9",10', ["7", "8,9", "10"]),
    ('zeta,"eta,theta"', ["zeta", "eta,theta"]),
    ('"kappa,lambda","mu,nu"', ["kappa,lambda", "mu,nu"]),
    ('front,"mid,dle",back', ["front", "mid,dle", "back"]),
]


@pytest.mark.parametrize("row,expected", UNSEEN_QUOTED_CASES)
def test_quoted_parsing_generalises_to_unseen_rows(row, expected):
    assert parse_row(row) == expected


UNSEEN_PLAIN_CASES = [
    ("d,e,f", ["d", "e", "f"]),
    ("single", ["single"]),
    ("g,,h", ["g", "", "h"]),
]


@pytest.mark.parametrize("row,expected", UNSEEN_PLAIN_CASES)
def test_unquoted_rows_still_split_normally(row, expected):
    assert parse_row(row) == expected


def test_quote_stripping_is_general():
    """A property no table of literals can satisfy by memorisation."""
    for inner in ("alpha", "one,two", "x,y,z"):
        assert parse_row(f'"{inner}"') == [inner]
