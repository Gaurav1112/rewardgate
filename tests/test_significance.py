"""Tests for the significance calculations.

These pin the statistics against hand-computable values. A significance test that is itself
untested would be worse than reporting no p-value at all, because it carries more authority.
"""

from __future__ import annotations

import pytest

from rewardgate.schema import DEFECT_CLASSES, NOP_PASS, Audit
from rewardgate.significance import clopper_pearson, degenerate_baselines, mcnemar_exact, pair_up


# --- McNemar --------------------------------------------------------------------------

def test_no_discordant_pairs_gives_p_of_one():
    assert mcnemar_exact(0, 0) == 1.0


@pytest.mark.parametrize(
    "n,expected",
    [(1, 1.0), (2, 0.5), (3, 0.25), (4, 0.125), (5, 0.0625), (6, 0.03125), (7, 0.015625)],
)
def test_all_discordance_one_way_is_two_times_half_to_the_n(n, expected):
    """The exact one-sided-extreme case: p = 2 * 0.5**n. This is why n>=6 is needed for p<0.05."""
    assert mcnemar_exact(0, n) == pytest.approx(expected)


def test_five_discordant_pairs_do_not_reach_significance():
    """The design's actual situation. Recorded so the limitation cannot be quietly lost."""
    p = mcnemar_exact(0, 5)
    assert p == pytest.approx(0.0625)
    assert p > 0.05


def test_six_discordant_pairs_would_reach_significance():
    assert mcnemar_exact(0, 6) < 0.05


def test_the_test_is_symmetric():
    assert mcnemar_exact(2, 5) == mcnemar_exact(5, 2)


def test_evenly_split_discordance_is_not_significant():
    assert mcnemar_exact(4, 4) == pytest.approx(1.0)


# --- Clopper-Pearson ------------------------------------------------------------------

def test_interval_brackets_the_point_estimate():
    lo, hi = clopper_pearson(3, 10)
    assert lo < 0.3 < hi


def test_zero_successes_has_a_lower_bound_of_zero_and_a_wide_upper_bound():
    lo, hi = clopper_pearson(0, 6)
    assert lo == 0.0
    assert hi == pytest.approx(0.4593, abs=1e-3), "0/6 is compatible with a ~46% true rate"


def test_all_successes_has_an_upper_bound_of_one():
    lo, hi = clopper_pearson(5, 5)
    assert hi == 1.0
    assert lo < 1.0


def test_known_textbook_interval():
    """2/20 → approximately [0.0123, 0.3170]."""
    lo, hi = clopper_pearson(2, 20)
    assert lo == pytest.approx(0.0123, abs=2e-3)
    assert hi == pytest.approx(0.3170, abs=2e-3)


def test_more_trials_narrow_the_interval():
    narrow = clopper_pearson(50, 100)
    wide = clopper_pearson(5, 10)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_zero_trials_is_maximally_uncertain():
    assert clopper_pearson(0, 0) == (0.0, 1.0)


# --- pairing and floors ---------------------------------------------------------------

def _audit(bundle: str, *flagged: str) -> Audit:
    return Audit(bundle_id=bundle, defects={d: d in flagged for d in DEFECT_CLASSES})


def test_pairing_classifies_each_judgement():
    truth = {"a": [NOP_PASS], "b": []}
    baseline = [_audit("a"), _audit("b")]            # misses a, correct on b
    rewardgate = [_audit("a", NOP_PASS), _audit("b")]  # correct on both
    paired = pair_up(baseline, rewardgate, truth)
    assert paired.total == 2 * len(DEFECT_CLASSES)
    assert paired.only_rewardgate == 1
    assert paired.only_baseline == 0
    assert paired.p_value == pytest.approx(1.0)


def test_always_yes_floor_is_not_zero():
    """macro-F1 has a non-zero floor, so a reported 0.524 must be read against it."""
    truth = {f"b{i}": ([NOP_PASS] if i < 3 else []) for i in range(15)}
    floors = degenerate_baselines(truth)
    assert floors["always_no"] == 0.0
    assert floors["always_yes"] > 0.0
