"""Corpus-level regression tests.

These pin measured rates across the real 500-instance corpus. They exist because every headline
number in the README is produced by this code: if a refactor quietly degrades coverage, the
submission's claims stop being true. A unit test on a fixture would not catch that.
"""

from __future__ import annotations

import pytest

from rewardgate.checkers.assertions import analyze_test_assertions
from rewardgate.checkers.hints import detect_hint_contamination
from rewardgate.checkers.leakage import detect_solution_leakage
from rewardgate.checkers.overspec import detect_over_specification
from rewardgate.corpus import REAL_CORPUS_PATH, load_real_corpus

pytestmark = pytest.mark.skipif(
    not REAL_CORPUS_PATH.exists(), reason="run scripts/fetch_real_corpus.sh first"
)


@pytest.fixture(scope="module")
def bundles():
    return load_real_corpus()


def test_corpus_is_the_expected_size(bundles):
    assert len(bundles) == 500


def test_assertion_parse_coverage_does_not_regress(bundles):
    """Block-level recovery raised coverage from 231/500 to 350/500. Hold that line."""
    parsed = sum(1 for b in bundles if analyze_test_assertions(b.test_patch).parse_ok)
    assert parsed == 350, f"parse coverage changed: {parsed}/500 (expected 350)"


def test_unparseable_instances_never_claim_a_verdict(bundles):
    """Indeterminate must mean silent, not 'clean'. This is the project's own honesty guarantee."""
    for b in bundles:
        report = analyze_test_assertions(b.test_patch)
        if report.indeterminate:
            assert not report.has_weak_assertions
            assert report.findings == ()


def test_weak_assertion_rate_is_stable(bundles):
    reports = [analyze_test_assertions(b.test_patch) for b in bundles]
    weak = sum(1 for r in reports if r.has_weak_assertions)
    assert weak == 48, f"weak-assertion count changed: {weak} (expected 48)"


def test_leakage_rate_matches_published_measurement(bundles):
    leaked = sum(1 for b in bundles if detect_solution_leakage(b.problem_statement, b.patch).leaked)
    assert leaked == 133


def test_over_specification_counts_only_internal_symbols(bundles):
    """Counting public API mentions inflated this 5x (229 vs 42). Hold the corrected figure."""
    findings = [detect_over_specification(b.problem_statement, b.patch) for b in bundles]
    assert sum(f.over_specified for f in findings) == 42
    assert sum(bool(f.named_symbols) for f in findings) == 229, "raw match count changed"


def test_hint_contamination_rate_is_stable(bundles):
    findings = [detect_hint_contamination(b.hints_text, b.patch) for b in bundles]
    assert sum(f.hints_present for f in findings) == 335
    assert sum(f.contaminated for f in findings) == 54


def test_headline_defect_rate_is_stable(bundles):
    """The single number the README leads with. It must not drift silently."""
    flagged = 0
    for b in bundles:
        if (
            detect_solution_leakage(b.problem_statement, b.patch).leaked
            or detect_over_specification(b.problem_statement, b.patch).over_specified
            or detect_hint_contamination(b.hints_text, b.patch).contaminated
            or analyze_test_assertions(b.test_patch).has_weak_assertions
        ):
            flagged += 1
    assert flagged == 210, f"headline defect count changed: {flagged}/500 (expected 210)"
