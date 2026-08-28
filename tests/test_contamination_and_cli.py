"""Tests for git-contamination detection and the CLI.

The side-branch case is the important one. It is the corpus's designated challenging case, and an
earlier implementation modelled it wrongly — the fix commit was left plainly visible in
`git log --oneline`, so the bundle did not exercise the reviewer failure mode it claimed to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rewardgate.checkers.contamination import detect_git_contamination
from rewardgate.cli import (
    DEFAULT_BUNDLES,
    EXIT_ACCEPT,
    EXIT_DEFECT,
    EXIT_INDETERMINATE,
    EXIT_USAGE,
    main,
    missing_artifacts,
)
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


def test_a_clean_bundle_is_not_certified_on_two_of_three_checks(capsys):
    """`--no-exploit` used to print `[  ok   ] REWARD_HACKABLE / exploit trial not run` and return
    ACCEPT with exit 0. The report was byte-identical for a clean bundle and a known
    reward-hackable one apart from test counts, on the free path a judge is most likely to run.

    Certifying a task while the one class the reward gate is blind to went unexamined is the exact
    fail-open this project exists to catch, committed by its own CLI.
    """
    assert main(["audit", "csvlite-clean", "--no-exploit"]) == EXIT_INDETERMINATE
    output = capsys.readouterr().out
    assert "VERDICT: INDETERMINATE" in output
    assert "2 of 3 classes checked" in output
    assert "[skipped] REWARD_HACKABLE" in output
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
    assert "patch -p1 < solution.patch" in output


def test_cli_unknown_bundle_exits_with_an_error(capsys):
    assert main(["audit", "does-not-exist", "--no-exploit"]) == 2
    assert "no such bundle" in capsys.readouterr().err


# --- the bundle contract --------------------------------------------------------------


def test_a_directory_that_is_not_a_bundle_is_refused_by_name(tmp_path, capsys):
    """Before this check, auditing an arbitrary directory printed a full report of exit-4 trials
    and blamed the no-op gate. The actual cause — no test suite, no gold patch — appeared nowhere.
    """
    (tmp_path / "src").mkdir()
    assert main(["audit", str(tmp_path), "--no-exploit"]) == EXIT_INDETERMINATE
    err = capsys.readouterr().err
    assert "tests" in err and "solution.patch" in err
    assert "No verdict is claimed" in err


def test_held_out_is_required_only_when_the_exploit_trial_will_run(tmp_path):
    """`--no-exploit` is the offline mode a judge runs without an API key, so demanding the
    adjudicating suite there would refuse bundles the deterministic tiers can audit fine."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "solution.patch").write_text("")
    assert missing_artifacts(tmp_path, need_exploit=False) == {}
    assert set(missing_artifacts(tmp_path, need_exploit=True)) == {"held_out"}


def test_every_corpus_bundle_satisfies_the_documented_contract():
    """The contract is only worth documenting if the shipped corpus actually meets it."""
    for bundle in sorted(p for p in DEFAULT_BUNDLES.iterdir() if p.is_dir()):
        assert missing_artifacts(bundle) == {}, bundle.name


def test_indeterminate_and_reject_do_not_share_an_exit_code():
    """A CI job gating on 'not zero' would otherwise treat 'this task is broken' and 'I could not
    check this task' identically, though they call for opposite responses."""
    assert EXIT_INDETERMINATE not in (EXIT_ACCEPT, EXIT_DEFECT, EXIT_USAGE)
