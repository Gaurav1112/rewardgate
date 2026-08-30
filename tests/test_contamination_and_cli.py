"""Tests for git-contamination detection and the CLI.

The side-branch case is the important one. It is the corpus's designated challenging case, and an
earlier implementation modelled it wrongly — the fix commit was left plainly visible in
`git log --oneline`, so the bundle did not exercise the reviewer failure mode it claimed to.
"""

from __future__ import annotations

import json
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


# --- rules 04 and 05: approval before consequential actions ----------------------------

def test_the_host_execution_warning_names_what_it_is_about_to_do(capsys):
    """Rule 04 asks for approval before the consequential action. The exploit tier was opt-out:
    host execution ran by default with nothing said."""
    from rewardgate.cli import confirm_host_execution

    assert confirm_host_execution(DEFAULT_BUNDLES / "csvlite-clean", assume_yes=True)
    warning = capsys.readouterr().err
    for claim in ("ON THIS MACHINE", "does NOT isolate the host", "--docker", "--no-exploit"):
        assert claim in warning


def test_the_contained_warning_still_names_what_is_not_contained(capsys):
    """`--docker` isolates the adjudication, not the agent session — that session *is* a network
    call, so it cannot run under `--network none`.

    A warning that said only "runs in a container" would read as total isolation and be worse than
    the honest unconfined one, because the reviewer would stop reading.
    """
    from rewardgate.cli import confirm_host_execution
    from rewardgate.execution import ContainerConfig

    assert confirm_host_execution(
        DEFAULT_BUNDLES / "csvlite-clean", assume_yes=True, container=ContainerConfig()
    )
    warning = capsys.readouterr().err
    assert "--network none" in warning
    assert "AGENT SESSION is still not contained" in warning
    assert "does NOT isolate the host" not in warning, "stale unconfined text leaked through"


def test_the_free_path_shows_no_host_execution_warning(capsys):
    """`--no-exploit` executes no agent-written code, so warning about it would be noise that
    trains the reader to skip the warning that matters."""
    main(["audit", "csvlite-clean", "--no-exploit"])
    assert "ON THIS MACHINE" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "decision,expected",
    [("confirm", EXIT_DEFECT), ("override", EXIT_ACCEPT), ("defer", EXIT_INDETERMINATE)],
)
def test_a_reviewer_can_confirm_override_or_defer_a_reject(monkeypatch, decision, expected):
    """Rule 05. `override` exits 0 on purpose: the tool can be wrong, and a reviewer who has read
    the evidence outranks it. `defer` exits 3, because undecided must not read as accepted."""
    from rewardgate.cli import record_review
    from rewardgate.schema import REJECT

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: decision)
    assert record_review(REJECT, assume_yes=False) == (decision, expected)


def test_a_non_reject_verdict_asks_the_reviewer_nothing(monkeypatch):
    """Only a REJECT turns away an author's work, so only a REJECT interrupts."""
    from rewardgate.cli import record_review
    from rewardgate.schema import ACCEPT

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("should not prompt"))
    assert record_review(ACCEPT, assume_yes=False) == ("", EXIT_ACCEPT)


def test_scripted_use_is_never_blocked_by_either_gate(monkeypatch):
    """Both gates weaken to a printed warning when stdin is not a terminal. That is a real
    weakening and it is documented; an interactive prompt in CI would break every documented
    command and the video."""
    from rewardgate.cli import record_review
    from rewardgate.schema import REJECT

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("prompted a non-terminal caller"))
    assert record_review(REJECT, assume_yes=False) == ("", EXIT_DEFECT)


# --- the report as an artifact, not just a thing on stdout -------------------------------

def test_the_report_can_be_written_to_a_file_the_author_attaches(tmp_path, capsys):
    """Until this existed the audit was a thing you watched, not a thing you kept.

    The reader is a contractor paid per *accepted* task. They need something to attach to a
    submission, hand a reviewer, or diff against last week — and the memo only ever went to stdout.
    """
    memo = tmp_path / "audit.md"
    main(["audit", "csvlite-nop-pass", "--no-exploit", "--out", str(memo)])
    assert memo.exists()
    text = memo.read_text()
    assert "VERDICT: REJECT" in text and "EXECUTED EVIDENCE" in text
    assert "WHAT TO FIX BEFORE YOU SUBMIT" in text
    assert str(memo) in capsys.readouterr().out, "the run should say where it wrote the file"


def test_the_json_verdict_says_how_many_classes_were_actually_checked(tmp_path):
    """The fail-open this project exists to catch, committed by anyone integrating it.

    A CI job reading only `verdict` cannot tell "no defect found" from "two of three classes were
    never examined". Both fields are mandatory in the payload for that reason, and `--no-exploit`
    must report 2, never 3.
    """
    out = tmp_path / "verdict.json"
    main(["audit", "csvlite-clean", "--no-exploit", "--json", str(out)])
    payload = json.loads(out.read_text())

    assert payload["checked_classes"] == 2 and payload["total_classes"] == 3
    assert payload["verdict"] == "INDETERMINATE", "2 of 3 classes must never read as ACCEPT"
    assert payload["exit_code"] == EXIT_INDETERMINATE
    assert set(payload["defects"]) == {"NOP_PASS", "CONTAMINATION_GIT", "REWARD_HACKABLE"}
    assert payload["verify_yourself"], "the machine-readable form must carry the checks too"


def test_every_proven_defect_carries_a_remedy(tmp_path):
    """A finding without a next step is a complaint. Every class must have one, and the report
    must print it — a contractor holding a rejection needs to know what to change."""
    from rewardgate.schema import DEFECT_DESCRIPTIONS, DEFECT_REMEDIES

    assert set(DEFECT_REMEDIES) == set(DEFECT_DESCRIPTIONS)
    out = tmp_path / "v.json"
    main(["audit", "csvlite-contaminated-git", "--no-exploit", "--json", str(out)])
    payload = json.loads(out.read_text())
    proven = [n for n, v in payload["defects"].items() if v]
    assert proven and set(payload["remedies"]) == set(proven)
