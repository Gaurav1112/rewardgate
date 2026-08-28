"""Tests for the execution layer.

These exist because of a gap found by applying this project's own standard to itself. The pytest
count parser feeds every `summary` string quoted as evidence in an audit report, but nothing
asserted its output: `reward` is derived from the process exit code, so replacing the parser body
with `return 1, 0, 0` left the whole suite green while every count in every report became a lie.

That is a lazy assertion — the exact defect class this project flags in other people's
benchmarks. The tests below pin the parser's actual output.
"""

from __future__ import annotations

from rewardgate.execution import TestOutcome, _parse_pytest_counts


def test_parses_a_passing_summary():
    assert _parse_pytest_counts("11 passed in 0.12s") == (11, 0, 0)


def test_parses_a_mixed_summary():
    assert _parse_pytest_counts("=== 3 passed, 8 failed in 0.30s ===") == (3, 8, 0)


def test_parses_errors():
    assert _parse_pytest_counts("=== 1 error in 0.03s ===") == (0, 0, 1)


def test_parses_failures_and_errors_together():
    assert _parse_pytest_counts("2 passed, 1 failed, 1 error in 0.4s") == (2, 1, 1)


def test_singular_and_plural_forms_both_parse():
    assert _parse_pytest_counts("1 passed in 0.01s") == (1, 0, 0)
    assert _parse_pytest_counts("1 failed in 0.01s") == (0, 1, 0)


def test_output_with_no_summary_yields_zeros():
    assert _parse_pytest_counts("collecting ...\nno tests ran") == (0, 0, 0)
    assert _parse_pytest_counts("") == (0, 0, 0)


def test_reads_the_last_summary_line_not_an_earlier_mention():
    """Verbose output mentions counts before the real summary; the final one wins."""
    output = "some test failed earlier\n...\n=== 5 passed, 2 failed in 1.0s ==="
    assert _parse_pytest_counts(output) == (5, 2, 0)


# --- reward semantics -----------------------------------------------------------------


def test_green_suite_is_reward_one():
    outcome = TestOutcome(exit_code=0, passed=4, failed=0, errors=0, stdout="")
    assert outcome.all_passed
    assert outcome.reward == 1.0


def test_failing_suite_is_reward_zero():
    outcome = TestOutcome(exit_code=1, passed=3, failed=1, errors=0, stdout="")
    assert outcome.reward == 0.0


def test_exit_zero_with_no_collected_tests_is_not_a_pass():
    """An empty suite exits 0. Treating that as reward 1.0 would pass every no-op task."""
    outcome = TestOutcome(exit_code=0, passed=0, failed=0, errors=0, stdout="no tests ran")
    assert not outcome.all_passed
    assert outcome.reward == 0.0


def test_timeout_is_never_a_pass():
    outcome = TestOutcome(exit_code=0, passed=9, failed=0, errors=0, stdout="", timed_out=True)
    assert not outcome.all_passed
    assert outcome.reward == 0.0
    assert outcome.summary == "timed out"


def test_summary_reports_the_parsed_counts():
    """The summary string is quoted verbatim as evidence, so its contents are load-bearing."""
    outcome = TestOutcome(exit_code=1, passed=3, failed=8, errors=0, stdout="")
    assert outcome.summary == "exit=1 passed=3 failed=8 errors=0"
