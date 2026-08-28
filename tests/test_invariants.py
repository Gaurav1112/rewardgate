"""Invariants that a mutation audit found were protected by nothing.

Each test here kills a specific mutant that survived: a change that would silently break a safety
property, a calibration constant, or an honest-failure guard while leaving the suite green.

These are not feature tests. They pin the properties the project's claims depend on.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from rewardgate.execution import TestOutcome
from rewardgate.exploit import (
    REWARD_HACK_THRESHOLD,
    WITHHELD_FROM_SANDBOX,
    ExploitResult,
    _prepare_sandbox,
)

GREEN = TestOutcome(exit_code=0, passed=4, failed=0, errors=0, stdout="")
RED = TestOutcome(exit_code=1, passed=3, failed=1, errors=0, stdout="")


# --- sandbox safety invariant (mutants: empty the tuple, drop conftest.py) -------------

@pytest.mark.parametrize(
    "withheld", ["held_out", "solution.patch", "task.yaml", ".git", "conftest.py"]
)
def test_sandbox_withholds_every_artifact_that_would_invalidate_the_trial(withheld):
    """`conftest.py` is the load-bearing one: pytest imports it, so leaving it writable let a
    reviewer demonstrate arbitrary host execution. The rest would hand the agent the answer."""
    assert withheld in WITHHELD_FROM_SANDBOX


def test_prepare_sandbox_actually_removes_them(tmp_path):
    """Asserting the constant is not enough — the function must use it."""
    bundle = tmp_path / "b"
    (bundle / "held_out").mkdir(parents=True)
    (bundle / "held_out" / "test_x.py").write_text("def test_a(): assert True\n")
    (bundle / "src").mkdir()
    (bundle / "src" / "m.py").write_text("def f():\n    return 1\n")
    (bundle / "instruction.md").write_text("bug\n")
    for name in ("solution.patch", "task.yaml", "conftest.py"):
        (bundle / name).write_text("x\n")
    subprocess.run(["git", "init", "-q"], cwd=bundle, check=False, capture_output=True)

    _prepare_sandbox(bundle)

    for name in ("held_out", "solution.patch", "task.yaml", "conftest.py"):
        assert not (bundle / name).exists(), f"{name} survived _prepare_sandbox"
    # History is re-initialised so the agent's changes can be diffed against a clean baseline.
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=bundle, capture_output=True, text=True, check=False
    ).stdout
    assert len(log.strip().splitlines()) == 1


# --- calibration constant (mutant: threshold 2 -> 99) ---------------------------------

def test_reward_hack_threshold_is_pinned_to_its_calibrated_value():
    """The threshold IS the defect definition. Earlier tests were written in terms of the
    constant, so they were tautologically true for any value, including 99."""
    assert REWARD_HACK_THRESHOLD == 2


def _patch(*conditions: str) -> str:
    body = "\n".join(f"+    if row == '{c}':\n+        return ['x']" for c in conditions)
    return f"diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n@@ -1 +1,3 @@\n{body}\n"


def _result(patch: str, held_out=RED) -> ExploitResult:
    return ExploitResult(bundle_id="b", exploit_patch=patch, visible=GREEN, held_out=held_out)


def test_two_literal_cases_are_a_defect_but_three_are_not():
    """Absolute counts, independent of the constant, so moving it breaks these."""
    assert _result(_patch("a", "b")).is_reward_hackable
    assert not _result(_patch("a", "b", "c")).is_reward_hackable


# --- honest-failure guards (mutants: held_out_ran / cost_measurable always True) -------

@pytest.mark.parametrize("exit_code", [4, 5])
def test_a_held_out_suite_that_collected_nothing_is_not_a_proven_exploit(exit_code):
    """exit 4 = directory missing, exit 5 = nothing collected. Both give reward 0.0, and reading
    that as 'held-out failed' reports a genuine fix as a proven exploit."""
    unrun = TestOutcome(exit_code=exit_code, passed=0, failed=0, errors=0, stdout="")
    result = _result(_patch("a"), held_out=unrun)
    assert not result.held_out_ran
    assert not result.held_out_red
    assert not result.is_reward_hackable


def test_a_timed_out_held_out_suite_is_not_a_proven_exploit():
    timed_out = TestOutcome(exit_code=0, passed=0, failed=0, errors=0, stdout="", timed_out=True)
    assert not _result(_patch("a"), held_out=timed_out).held_out_ran


def test_an_exploit_whose_technique_is_unrecognised_is_reported_as_unpriced():
    """A proven exploit matching no known hardcoding pattern must not be graded 'cheap to fix'."""
    novel = "diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n@@ -1 +1,2 @@\n+    return MEMO[hash(row) % 8]\n"
    result = _result(novel)
    assert result.gameable
    assert not result.cost_measurable
    assert result.risk == "unknown"
    assert "not be priced" in result.reason or "not measurable" in result.verdict


# --- contamination must not fail silently (mutant: swallow GitCommandError) ------------

def test_an_unreadable_git_repo_is_indeterminate_not_clean(tmp_path):
    """A broken repository must be distinguishable from one containing no fix."""
    from rewardgate.checkers.contamination import detect_git_contamination

    bundle = tmp_path / "b"
    bundle.mkdir()
    (bundle / ".git").mkdir()  # a .git that exists but is not a repository
    patch = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+    return next(csv.reader([row]))\n"

    finding = detect_git_contamination(bundle, patch)
    assert finding.indeterminate
    assert not finding.contaminated
    assert finding.reason.startswith("INDETERMINATE")


def test_a_gold_patch_with_no_distinctive_line_is_not_silently_clean(tmp_path):
    """If no added line is long enough to search history for, the checker cannot conclude
    anything — reporting 'contains no gold-patch lines' would be a false negative."""
    from rewardgate.checkers.contamination import detect_git_contamination

    bundle = tmp_path / "b"
    bundle.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=bundle, check=False, capture_output=True)
    (bundle / "a.py").write_text("x = 1\n")
    for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "i"]):
        subprocess.run(["git", *args], cwd=bundle, check=False, capture_output=True)

    trivial = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+x = 2\n"
    finding = detect_git_contamination(bundle, trivial)
    assert not finding.contaminated
