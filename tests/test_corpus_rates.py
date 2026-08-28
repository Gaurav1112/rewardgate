"""Corpus-level regression tests.

These pin measured rates across the real 500-instance corpus. They exist because every headline
number in the README is produced by this code: if a refactor quietly degrades coverage, the
submission's claims stop being true. A unit test on a fixture would not catch that.
"""

from __future__ import annotations

import pytest

from rewardgate.checkers.assertions import analyze_test_assertions
from rewardgate.checkers.leakage import detect_solution_leakage
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
    assert weak == 49, f"weak-assertion count changed: {weak} (expected 49)"


def test_leakage_rate_matches_published_measurement(bundles):
    leaked = sum(1 for b in bundles if detect_solution_leakage(b.problem_statement, b.patch).leaked)
    assert leaked == 133
