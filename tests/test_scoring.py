"""Tests for the scorer.

This module computes the headline metric and had no tests at all. A mutation audit showed that
`f1` could be replaced by `precision`, `macro_f1` by `max` instead of the mean, `recall` by
`precision`, and every false positive counted as a true positive — and the suite stayed green at
116/116 in every case.

A metric nothing verifies is a number nobody should trust, including its author.
"""

from __future__ import annotations

import pytest

from rewardgate.schema import CONTAMINATION_GIT, DEFECT_CLASSES, NOP_PASS, REWARD_HACKABLE, Audit
from rewardgate.scoring import ClassScore, format_comparison, score_audits


def _audit(bundle_id: str, *flagged: str) -> Audit:
    return Audit(bundle_id=bundle_id, defects={d: d in flagged for d in DEFECT_CLASSES})


# --- ClassScore arithmetic ------------------------------------------------------------

def test_precision_recall_f1_on_a_known_confusion_matrix():
    """TP=3 FP=1 FN=2 → P=0.75, R=0.60, F1=0.6667. Hand-computed, not derived from the code."""
    score = ClassScore(NOP_PASS, true_positives=3, false_positives=1, false_negatives=2)
    assert score.precision == pytest.approx(0.75)
    assert score.recall == pytest.approx(0.60)
    assert score.f1 == pytest.approx(2 * 0.75 * 0.60 / (0.75 + 0.60))
    assert score.f1 == pytest.approx(0.666667, abs=1e-5)


def test_f1_is_the_harmonic_mean_not_the_precision():
    """Kills the mutant where f1 returns precision. These differ whenever P != R."""
    score = ClassScore(NOP_PASS, true_positives=1, false_positives=0, false_negatives=3)
    assert score.precision == 1.0
    assert score.recall == 0.25
    assert score.f1 == pytest.approx(0.4)
    assert score.f1 != score.precision


def test_recall_is_not_precision():
    score = ClassScore(NOP_PASS, true_positives=2, false_positives=6, false_negatives=0)
    assert score.recall == 1.0
    assert score.precision == 0.25
    assert score.recall != score.precision


def test_perfect_and_empty_scores():
    perfect = ClassScore(NOP_PASS, true_positives=4)
    assert (perfect.precision, perfect.recall, perfect.f1) == (1.0, 1.0, 1.0)
    empty = ClassScore(NOP_PASS)
    assert (empty.precision, empty.recall, empty.f1, empty.support) == (0.0, 0.0, 0.0, 0)


def test_f1_is_zero_when_either_component_is_zero():
    assert ClassScore(NOP_PASS, true_positives=0, false_positives=5).f1 == 0.0
    assert ClassScore(NOP_PASS, true_positives=0, false_negatives=5).f1 == 0.0


# --- score_audits ---------------------------------------------------------------------

def test_counts_tp_fp_fn_tn_correctly():
    truth = {"a": [NOP_PASS], "b": [], "c": [NOP_PASS]}
    audits = [_audit("a", NOP_PASS), _audit("b", NOP_PASS), _audit("c")]
    nop = next(c for c in score_audits("s", audits, truth).per_class if c.defect == NOP_PASS)
    assert (nop.true_positives, nop.false_positives, nop.false_negatives) == (1, 1, 1)
    assert nop.support == 2


def test_a_false_positive_is_not_credited_as_a_true_positive():
    """Kills the mutant that counts every prediction as correct."""
    truth = {"a": []}
    nop = next(
        c for c in score_audits("s", [_audit("a", NOP_PASS)], truth).per_class
        if c.defect == NOP_PASS
    )
    assert nop.true_positives == 0
    assert nop.false_positives == 1


def test_macro_f1_is_the_mean_not_the_max():
    """Kills the mutant where macro_f1 returns max(). Requires classes to differ."""
    truth = {"a": [NOP_PASS, REWARD_HACKABLE], "b": [NOP_PASS, REWARD_HACKABLE]}
    # NOP_PASS perfect (F1 1.0); REWARD_HACKABLE missed entirely (F1 0.0); CONTAMINATION n/a (0.0)
    audits = [_audit("a", NOP_PASS), _audit("b", NOP_PASS)]
    score = score_audits("s", audits, truth)
    by_class = {c.defect: c.f1 for c in score.per_class}
    assert by_class[NOP_PASS] == 1.0
    assert by_class[REWARD_HACKABLE] == 0.0
    assert score.macro_f1 == pytest.approx(1.0 / 3)
    assert score.macro_f1 != max(by_class.values())


def test_exact_match_requires_every_class_to_be_right():
    truth = {"a": [NOP_PASS], "b": [NOP_PASS]}
    audits = [_audit("a", NOP_PASS), _audit("b", NOP_PASS, CONTAMINATION_GIT)]
    score = score_audits("s", audits, truth)
    assert score.exact_match == 1
    assert score.exact_match_rate == pytest.approx(0.5)


def test_a_perfect_system_scores_one_and_a_silent_one_scores_zero():
    truth = {"a": [NOP_PASS], "b": [CONTAMINATION_GIT], "c": [REWARD_HACKABLE]}
    perfect = [_audit("a", NOP_PASS), _audit("b", CONTAMINATION_GIT), _audit("c", REWARD_HACKABLE)]
    assert score_audits("s", perfect, truth).macro_f1 == 1.0
    silent = [_audit("a"), _audit("b"), _audit("c")]
    assert score_audits("s", silent, truth).macro_f1 == 0.0


def test_always_yes_predictor_scores_the_documented_floor():
    """macro-F1's floor is not zero. Reported so 0.524 is read against the right baseline."""
    truth = {f"b{i}": ([NOP_PASS] if i < 3 else []) for i in range(15)}
    always_yes = [_audit(b, *DEFECT_CLASSES) for b in truth]
    score = score_audits("always-yes", always_yes, truth)
    assert score.macro_f1 == pytest.approx(0.1111, abs=1e-3)
    assert score.exact_match == 0


def test_cost_and_errors_are_aggregated():
    audits = [
        Audit(bundle_id="a", defects={d: False for d in DEFECT_CLASSES}, cost_usd=0.10),
        Audit(bundle_id="b", defects={d: False for d in DEFECT_CLASSES}, cost_usd=0.20, error="boom"),
    ]
    score = score_audits("s", audits, {"a": [], "b": []})
    assert score.total_cost_usd == pytest.approx(0.30)
    assert score.cost_per_bundle == pytest.approx(0.15)
    assert score.errors == 1


def test_empty_audit_list_does_not_divide_by_zero():
    score = score_audits("s", [], {})
    assert (score.macro_f1, score.exact_match_rate, score.cost_per_bundle) == (0.0, 0.0, 0.0)


def test_format_comparison_handles_a_zero_baseline_without_crashing():
    truth = {"a": [NOP_PASS]}
    zero = score_audits("baseline", [_audit("a")], truth)
    perfect = score_audits("rewardgate", [_audit("a", NOP_PASS)], truth)
    rendered = format_comparison(zero, perfect)
    assert "macro-F1 (primary)" in rendered
    assert "NOP_PASS" in rendered
