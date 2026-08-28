"""The report's "VERIFY THIS YOURSELF" block must actually work when pasted.

This block is the project's central promise — that no finding has to be taken on trust — and it
was the least trustworthy thing in the repository. A hardcoded template shipped for the whole
project with three independent defects, none visible from reading the code:

* `python -m pytest` on a machine whose interpreter is `python3` and whose pytest lives in the
  project venv: `command not found` on the first command a reviewer pastes.
* `git stash` to undo the gold patch. Bundles are gitignored so stash does not touch them, and a
  clean bundle ships no `.git`, so the command runs against the *enclosing* repository and
  stashes the reviewer's own uncommitted work. Destructive, and it did not revert anything.
* The contamination grep searched for `grep '^+' solution.patch | head -1`, which is the diff's
  `+++ b/...` header rather than a line of the fix.

The replacement then reproduced the same *class* of bug once more: an unscoped `git log -p --all`
matched the gold line inside the committed `solution.patch`, firing on the negative control. That
is why these tests execute the emitted commands instead of inspecting their text.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rewardgate.auditor import AuditTrace
from rewardgate.checkers.contamination import detect_git_contamination
from rewardgate.cli import verification_commands
from rewardgate.gates import RewardGateResult, read_patch
from rewardgate.execution import TestOutcome

BUNDLES = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "bundles"

pytestmark = pytest.mark.skipif(
    not (BUNDLES / "labels.yaml").exists(),
    reason="run: uv run python corpus/synthetic/build.py",
)

_STUB = TestOutcome(exit_code=0, passed=1, failed=0, errors=0, stdout="")


def _commands(name: str) -> list[str]:
    bundle = BUNDLES / name
    trace = AuditTrace(
        gate=RewardGateResult(oracle=_STUB, nop=_STUB),
        contamination=detect_git_contamination(bundle, read_patch(bundle)),
        exploit=None,
    )
    return verification_commands(bundle, trace)


def _grep_line(name: str) -> str | None:
    return next((c for c in _commands(name) if c.startswith("git log")), None)


def test_the_emitted_grep_reproduces_the_checkers_verdict_on_a_contaminated_bundle():
    command = _grep_line("csvlite-contaminated-git")
    assert command and "expect a match" in command
    result = subprocess.run(
        command.split("#")[0], shell=True, cwd=BUNDLES / "csvlite-contaminated-git",
        capture_output=True, text=True,
    )
    assert result.stdout.strip(), "the command a reviewer pastes finds nothing"


def test_the_emitted_grep_stays_silent_on_the_negative_control():
    """`csvlite-clean-git-history` ships history that does NOT contain the fix. An unscoped grep
    matched anyway, because the bundle commits `solution.patch` and its `+` lines read as `++`."""
    command = _grep_line("csvlite-clean-git-history")
    assert command and "expect no match" in command
    result = subprocess.run(
        command.split("#")[0], shell=True, cwd=BUNDLES / "csvlite-clean-git-history",
        capture_output=True, text=True,
    )
    assert not result.stdout.strip(), f"false positive on the negative control: {result.stdout!r}"


def test_the_oracle_and_nop_commands_run_and_give_the_documented_outcomes():
    """Executed, not pattern-matched: the previous block was syntactically fine and still broken."""
    bundle = BUNDLES / "csvlite-clean"
    patch = bundle / "solution.patch"

    def pytest_in(cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["uv", "run", "pytest", "tests/", "-q"], cwd=cwd, capture_output=True, text=True
        )

    def apply(*flags: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["patch", *flags, "-p1", "-i", str(patch)], cwd=bundle, capture_output=True, text=True
        )

    assert pytest_in(bundle).returncode != 0, "no-op trial should fail before the fix"
    assert apply().returncode == 0
    try:
        assert pytest_in(bundle).returncode == 0, "oracle trial should pass after the fix"
    finally:
        assert apply("-R").returncode == 0, "the documented restore step failed; tree left dirty"


def test_the_patch_step_does_not_silently_target_the_enclosing_repository():
    """`csvlite-clean` ships no `.git`, so `git rev-parse` inside it resolves to this repo. Under
    `git apply` the diff's paths are then taken relative to *that* root: exit 0, nothing patched,
    and the oracle command reports the unfixed suite. Only `patch` is cwd-relative."""
    bundle = BUNDLES / "csvlite-clean"
    assert not (bundle / ".git").exists()
    joined = "\n".join(_commands("csvlite-clean"))
    assert "git apply" not in joined
    assert "patch -p1" in joined


def test_a_bundle_without_git_history_is_told_so_rather_than_given_a_broken_command():
    commands = _commands("csvlite-clean")
    assert not any(c.startswith("git log") for c in commands)
    assert any("no git history shipped" in c for c in commands)


def test_no_command_uses_git_stash_or_a_bare_python_interpreter():
    """Both regressions, pinned. Either one silently breaks the reviewer's paste."""
    for name in ("csvlite-clean", "csvlite-contaminated-git", "csvlite-clean-git-history"):
        joined = "\n".join(_commands(name))
        assert "git stash" not in joined
        assert "python -m pytest" not in joined


# --- mutants that survived a mutation audit of the emitted shell ------------------------

def test_the_cd_line_is_quoted_and_flag_terminated():
    """Both halves were unpinned. `shlex.quote` protects the argument's CONTENT; `--` protects its
    POSITION. A bundle named `-P` emitted `cd -P || exit 1`, which succeeds, moves to the parent,
    and leaves the following `patch -p1` running in the reviewer's home directory. Removing either
    defence left all 244 tests green."""
    import shlex

    hostile = BUNDLES / 'csvlite-clean$(touch RG_PWNED)'
    trace = AuditTrace(
        gate=RewardGateResult(oracle=_STUB, nop=_STUB),
        contamination=detect_git_contamination(hostile, ""),
        exploit=None,
    )
    line = verification_commands(hostile, trace)[0]
    assert line.startswith("cd -- "), "no flag terminator: a path that is a flag defeats the guard"
    assert "$(touch RG_PWNED)" in line, "the payload should be present but inert, not stripped"
    # shlex must see exactly one path argument, i.e. the payload never reaches the shell as code.
    args = shlex.split(line.split("||")[0])
    assert args[:2] == ["cd", "--"] and len(args) == 3
    assert args[2].endswith("csvlite-clean$(touch RG_PWNED)")


def test_a_failed_cd_aborts_the_rest_of_the_block():
    """Without `|| exit 1` the following `patch` commands run against the reviewer's own cwd."""
    trace = AuditTrace(
        gate=RewardGateResult(oracle=_STUB, nop=_STUB),
        contamination=detect_git_contamination(BUNDLES / "csvlite-clean", ""),
        exploit=None,
    )
    assert verification_commands(BUNDLES / "csvlite-clean", trace)[0].endswith("|| exit 1")
