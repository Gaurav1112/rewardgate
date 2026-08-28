"""Tests for git-contamination detection and the CLI.

The side-branch case is the important one. It is the corpus's designated challenging case, and an
earlier implementation modelled it wrongly — the fix commit was left plainly visible in
`git log --oneline`, so the bundle did not exercise the reviewer failure mode it claimed to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rewardgate.checkers.contamination import detect_git_contamination
from rewardgate.cli import main
from rewardgate.gates import read_patch

BUNDLES = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "bundles"

pytestmark = pytest.mark.skipif(
    not (BUNDLES / "labels.yaml").exists(),
    reason="run: uv run python corpus/synthetic/build.py",
)


def _finding(name: str):
    bundle = BUNDLES / name
    return detect_git_contamination(bundle, read_patch(bundle))


def test_bundle_without_history_is_reported_as_absent_not_clean():
    finding = _finding("csvlite-clean")
    assert not finding.has_git
    assert not finding.contaminated
    assert finding.reason == "no git history shipped with the bundle"


def test_side_branch_fix_is_detected():
    finding = _finding("csvlite-contaminated-git")
    assert finding.has_git
    assert finding.contaminated
    assert finding.disclosed_lines


def test_side_branch_fix_is_reported_as_hidden_from_the_default_log():
    """The challenging case: the default log is innocent, `--all` is not."""
    finding = _finding("csvlite-contaminated-git")
    assert not finding.visible_in_shortlog
    assert not finding.on_current_branch
    assert "only reachable via `git log -p --all`" in finding.reason


def test_the_hidden_commit_is_named_in_the_evidence():
    finding = _finding("csvlite-contaminated-git")
    hidden = [c for c in finding.commits if c.startswith("[hidden]")]
    assert hidden, "the contaminating commit should be listed and marked hidden"


def test_reason_does_not_contradict_the_commit_listing():
    """Regression: the reason once said 'visible in the short log' while listing it as hidden."""
    finding = _finding("csvlite-contaminated-git")
    says_visible = "visible in the short log" in finding.reason
    has_hidden_commit = any(c.startswith("[hidden]") for c in finding.commits)
    assert not (says_visible and has_hidden_commit)


def test_empty_solution_patch_yields_no_finding(tmp_path):
    assert not detect_git_contamination(tmp_path, "").contaminated


# --- CLI ------------------------------------------------------------------------------


def test_cli_list_exits_zero(capsys):
    assert main(["list"]) == 0
    assert "csvlite-clean" in capsys.readouterr().out


def test_cli_audit_of_a_clean_bundle_accepts(capsys):
    """Exit 0 on ACCEPT so the command can gate a pipeline."""
    assert main(["audit", "csvlite-clean", "--no-exploit"]) == 0
    output = capsys.readouterr().out
    assert "VERDICT: ACCEPT" in output
    assert "EXECUTED EVIDENCE" in output


def test_cli_audit_of_a_contaminated_bundle_rejects_and_exits_nonzero(capsys):
    assert main(["audit", "csvlite-contaminated-git", "--no-exploit"]) == 1
    output = capsys.readouterr().out
    assert "VERDICT: REJECT" in output
    assert "HUMAN CHECKPOINT REQUIRED" in output


def test_cli_report_cites_verifiable_commands(capsys):
    """Every report must tell the reader how to check the claim themselves."""
    main(["audit", "csvlite-clean", "--no-exploit"])
    output = capsys.readouterr().out
    assert "VERIFY THIS YOURSELF" in output
    assert "git apply solution.patch" in output


def test_cli_unknown_bundle_exits_with_an_error(capsys):
    assert main(["audit", "does-not-exist", "--no-exploit"]) == 2
    assert "no such bundle" in capsys.readouterr().err
