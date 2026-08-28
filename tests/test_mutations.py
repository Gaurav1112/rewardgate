"""Tests for the defect injectors.

This module had no tests, and it is the one the project's central honesty claim depends on:
"labels are exact by construction, because the injector that creates the defect also writes the
label." A mutation audit showed that if `inject_nop_pass` were replaced by a no-op returning True,
`csvlite-nop-pass` would be byte-identical to `csvlite-clean` while still labelled NOP_PASS — the
corpus label would be false and the suite would stay green.

So these assert that each injector actually produced the artifact its label describes, and that
the negative control genuinely contains no solution.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from rewardgate.mutations import (
    inject_clean_git_history,
    inject_git_contamination,
    inject_nop_pass,
    inject_reward_hackable,
)

BASE = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "base"
REPOS = sorted(p.name for p in BASE.iterdir() if p.is_dir()) if BASE.exists() else []

pytestmark = pytest.mark.skipif(not REPOS, reason="base corpus missing")


@pytest.fixture
def bundle(tmp_path, request):
    """A clean copy of one base repo, with its gold patch generated as the builder does."""
    repo = request.param if hasattr(request, "param") else REPOS[0]
    dest = tmp_path / repo
    shutil.copytree(BASE / repo, dest, ignore=shutil.ignore_patterns("solution", "__pycache__"))

    import sys
    sys.path.insert(0, str(BASE.parent))
    from build import generate_patch, solution_files  # type: ignore

    (dest / "solution.patch").write_text(
        generate_patch(BASE / repo, BASE / repo / "solution", solution_files(BASE / repo))
    )
    return dest


def _run_visible(bundle_dir: Path) -> int:
    """Exit code of the visible suite against the unpatched source."""
    from rewardgate.execution import MaterialisedBundle, materialise

    with materialise(bundle_dir) as tmp:
        materialised = MaterialisedBundle(Path(tmp))
        return materialised.run_tests(materialised.repo / "tests").exit_code


def _count_failing_cases(bundle_dir: Path) -> int:
    """Entries in the FIRST case table — the fail-to-pass one.

    Only this table matters for gameability. Later tables (unquoted rows, ordinary releases) pass
    against the unpatched source already, so an exploiter never has to special-case them; the
    injector correctly leaves them alone.
    """
    lines = (bundle_dir / "tests" / "test_f2p.py").read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip().endswith("CASES = ["))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].rstrip() == "]")
    return sum(1 for line in lines[start + 1 : end] if line.strip().startswith("("))


# --- NOP_PASS ------------------------------------------------------------------------

@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_nop_pass_injection_makes_the_suite_pass_unpatched(bundle):
    """The defining property of the label. Kills a no-op injector."""
    assert _run_visible(bundle) != 0, "clean bundle should fail before the fix"
    assert inject_nop_pass(bundle)
    assert _run_visible(bundle) == 0, "after injection the suite must pass with no patch applied"


@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_nop_pass_injection_actually_rewrites_the_test_file(bundle):
    before = (bundle / "tests" / "test_f2p.py").read_text()
    inject_nop_pass(bundle)
    assert (bundle / "tests" / "test_f2p.py").read_text() != before


# --- REWARD_HACKABLE -----------------------------------------------------------------

@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_reward_hackable_injection_reduces_the_failing_suite_to_one_case(bundle):
    """Cheap to game only if the visible suite is small. Kills a no-op injector."""
    before = _count_failing_cases(bundle)
    assert before > 1, "clean bundle should carry several parametrised cases"
    assert inject_reward_hackable(bundle)
    assert _count_failing_cases(bundle) == 1


@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_reward_hackable_injection_keeps_the_reward_gate_intact(bundle):
    """The bug must still be real: the suite must still fail before the fix.

    If this regressed, the bundle would be a NOP_PASS wearing a REWARD_HACKABLE label.
    """
    inject_reward_hackable(bundle)
    assert _run_visible(bundle) != 0


# --- CONTAMINATION_GIT ---------------------------------------------------------------

@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_contamination_injection_hides_the_fix_from_the_default_log(bundle):
    assert inject_git_contamination(bundle)

    def git(*args):
        return subprocess.run(["git", *args], cwd=bundle, capture_output=True, text=True).stdout

    assert "fix" not in git("log", "--oneline").lower(), "fix must not appear on the default branch"
    assert "fix" in git("log", "--oneline", "--all").lower(), "fix must exist on some ref"


@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_contamination_injection_leaves_the_working_tree_unfixed(bundle):
    """A contaminated bundle must still be an unsolved task."""
    inject_git_contamination(bundle)
    assert _run_visible(bundle) != 0


@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_contaminated_history_is_detected_by_the_checker(bundle):
    from rewardgate.checkers.contamination import detect_git_contamination

    inject_git_contamination(bundle)
    finding = detect_git_contamination(bundle, (bundle / "solution.patch").read_text())
    assert finding.contaminated
    assert not finding.visible_in_shortlog


# --- the negative control ------------------------------------------------------------

@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_clean_git_history_creates_real_history_without_the_solution(bundle):
    """The control must have a `.git` that a naive "does .git exist?" check would flag."""
    from rewardgate.checkers.contamination import detect_git_contamination

    assert inject_clean_git_history(bundle)
    assert (bundle / ".git").exists()

    log = subprocess.run(
        ["git", "log", "--oneline", "--all"], cwd=bundle, capture_output=True, text=True
    ).stdout
    assert len(log.strip().splitlines()) >= 4, "control should carry several ordinary commits"

    finding = detect_git_contamination(bundle, (bundle / "solution.patch").read_text())
    assert not finding.contaminated, "the control must not contain the fix"
    assert finding.has_git, "and it must still ship history, or it controls for nothing"


@pytest.mark.parametrize("bundle", REPOS, indirect=True)
def test_clean_git_history_leaves_the_task_unsolved(bundle):
    inject_clean_git_history(bundle)
    assert _run_visible(bundle) != 0


def test_injectors_decline_rather_than_silently_succeed(tmp_path):
    """An injector that cannot do its job must return False so the builder drops the bundle."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert inject_nop_pass(empty) is False
    assert inject_reward_hackable(empty) is False
    assert inject_git_contamination(empty) is False
