"""Invariants that a mutation audit found were protected by nothing.

Each test here kills a specific mutant that survived: a change that would silently break a safety
property, a calibration constant, or an honest-failure guard while leaving the suite green.

These are not feature tests. They pin the properties the project's claims depend on.
"""

from __future__ import annotations

import os
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


# --- the harness must not inherit the operator's environment --------------------------

@pytest.mark.parametrize(
    "hostile", ["FORCE_COLOR", "PY_COLORS", "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "GH_TOKEN",
     "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK", "ANTHROPIC_API_KEY"]
)
def test_variables_that_would_corrupt_the_measurement_are_stripped(hostile, tmp_path):
    """Counts are scraped from pytest's summary line, so `FORCE_COLOR=1` wraps them in ANSI and
    every trial parses as `passed=0 failed=0` — indistinguishable from "collected nothing".
    `PYTEST_ADDOPTS` is worse: `-k nomatch` makes a suite pass by running nothing.

    An adversarial review reproduced a whole-corpus flip (REJECT -> INDETERMINATE) from a single
    exported variable, with nothing in the output disclosing why.
    """
    from rewardgate.execution import MaterialisedBundle

    bundle = MaterialisedBundle(tmp_path)
    os.environ[hostile] = "1"
    try:
        assert hostile not in bundle._test_env()
    finally:
        os.environ.pop(hostile, None)


def test_the_environment_is_an_allowlist_not_a_denylist(tmp_path):
    """A denylist can only enumerate the variables its author thought of. An adversarial review
    found GH_TOKEN, AUTH0_CLIENT_SECRET, SENDGRID_API_KEY and a live SSH_AUTH_SOCK reaching
    module-scope code in an agent-written patch, because the scrub started from os.environ.copy()."""
    from rewardgate.execution import MaterialisedBundle

    os.environ["TOTALLY_NOVEL_SECRET_XYZ"] = "shh"
    try:
        env = MaterialisedBundle(tmp_path)._test_env()
        assert set(env) <= {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "PYTHONPATH",
                            "PYTHONHASHSEED"}, f"unexpected variables leaked: {set(env)}"
    finally:
        os.environ.pop("TOTALLY_NOVEL_SECRET_XYZ", None)


def test_hash_seed_is_pinned_so_iteration_order_cannot_move_a_verdict(tmp_path):
    from rewardgate.execution import MaterialisedBundle

    assert MaterialisedBundle(tmp_path)._test_env()["PYTHONHASHSEED"] == "0"


def test_pythonpath_is_set_outright_not_prepended(tmp_path):
    """A same-named module on the operator's PYTHONPATH would otherwise shadow the bundle's."""
    from rewardgate.execution import MaterialisedBundle

    os.environ["PYTHONPATH"] = "/somewhere/else"
    try:
        assert MaterialisedBundle(tmp_path)._test_env()["PYTHONPATH"] == str(tmp_path / "repo" / "src")
    finally:
        os.environ.pop("PYTHONPATH", None)


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
    assert finding.indeterminate, "no fingerprint is not the same as searched-and-found-nothing"


def test_a_deletion_only_gold_patch_is_indeterminate_not_clean(tmp_path):
    """Removing a stray `break` is an ordinary bug fix and adds no lines at all, so there is
    nothing to search history for. Reported as clean, that is a false negative on a real shape."""
    from rewardgate.checkers.contamination import detect_git_contamination

    bundle = tmp_path / "b"
    bundle.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=bundle, check=False, capture_output=True)
    deletion_only = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -3,2 +3 @@\n"
        "     for candidate in items:\n-        break\n"
    )
    finding = detect_git_contamination(bundle, deletion_only)
    assert finding.indeterminate
    assert not finding.contaminated


# --- contamination must not accuse an innocent commit ----------------------------------

def _repo(tmp_path, files: dict[str, str], message: str = "initial import"):
    bundle = tmp_path / "b"
    for name, text in files.items():
        (bundle / name).parent.mkdir(parents=True, exist_ok=True)
        (bundle / name).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=bundle, check=False, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=bundle, check=False, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message],
        cwd=bundle, check=False, capture_output=True,
    )
    return bundle


def test_a_gold_patch_restating_a_shipped_line_is_not_contamination(tmp_path):
    """The worst possible false positive: REJECT on a clean bundle.

    Gold patches routinely restate unchanged lines -- a re-indented guard, a moved import, a hunk
    regenerated with less context. Those lines are already in the shipped buggy source, so history
    containing them proves only that the baseline was committed. An adversarial review used exactly
    this to turn a clean bundle into a REJECT that cited `initial import` as the leak.
    """
    from rewardgate.checkers.contamination import detect_git_contamination

    source = 'def retry(attempt):\n    raise ValueError("attempt must be >= 1")\n    return attempt\n'
    bundle = _repo(tmp_path, {"src/m.py": source})
    # The patch restates the raise (already shipped) and adds one genuinely new line.
    patch = (
        "diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n@@ -1,3 +1,4 @@\n"
        '+    raise ValueError("attempt must be >= 1")\n'
        "+    return min(MAX_DELAY_SECONDS, 2 ** attempt)\n"
    )
    finding = detect_git_contamination(bundle, patch)
    assert not finding.contaminated, f"false positive: {finding.reason}"
    assert not finding.commits


def test_only_commits_carrying_a_disclosed_line_are_named(tmp_path):
    """The report listed every commit in the repository under 'contaminating commits', so an
    innocent baseline import was named alongside the real leak."""
    from rewardgate.checkers.contamination import detect_git_contamination

    bundle = _repo(tmp_path, {"src/m.py": "def parse(row):\n    return row.split(',')\n"})
    (bundle / "src" / "m.py").write_text(
        "def parse(row):\n    return next(csv.reader([row]))\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=bundle, check=False, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fix parsing"],
        cwd=bundle, check=False, capture_output=True,
    )
    # A contaminated bundle ships the BUGGY tree; the fix survives only in history. Leaving the
    # fixed source in place would mean the line is visible without touching git at all, which is a
    # different (and non-)finding.
    (bundle / "src" / "m.py").write_text("def parse(row):\n    return row.split(',')\n")
    patch = (
        "diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n@@ -1,2 +1,2 @@\n"
        "+    return next(csv.reader([row]))\n"
    )
    finding = detect_git_contamination(bundle, patch)
    assert finding.contaminated
    assert len(finding.commits) == 1, finding.commits
    assert "fix parsing" in finding.commits[0]
    assert not any("initial import" in c for c in finding.commits)


def test_a_planted_docstring_cannot_erase_the_contamination_fingerprint(tmp_path):
    """Subtraction of already-shipped lines was scoped to every .py in the bundle. An adversarial
    review planted one innocuous file whose docstring contained the fix, which deleted it from the
    fingerprint and produced the affirmative verdict 'contains no gold-patch lines' on a bundle
    whose fix was still in history. Subtraction is now scoped to the files the patch modifies."""
    from rewardgate.checkers.contamination import detect_git_contamination

    bundle = _repo(tmp_path, {"src/m.py": "def parse(row):\n    return row.split(',')\n"})
    (bundle / "src" / "m.py").write_text("def parse(row):\n    return next(csv.reader([row]))\n")
    subprocess.run(["git", "add", "-A"], cwd=bundle, check=False, capture_output=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fix"],
                   cwd=bundle, check=False, capture_output=True)
    (bundle / "src" / "m.py").write_text("def parse(row):\n    return row.split(',')\n")
    # The plant: a file the gold patch never touches, whose docstring carries the fix verbatim.
    (bundle / "src" / "_docs.py").write_text('"""\n    return next(csv.reader([row]))\n"""\n')

    patch = ("diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n@@ -1,2 +1,2 @@\n"
             "+    return next(csv.reader([row]))\n")
    assert detect_git_contamination(bundle, patch).contaminated, "plant defeated the checker"


def test_comments_do_not_inflate_the_price_of_an_exploit():
    """Three comment lines flipped a ground-truth REWARD_HACKABLE bundle from REVISE to ACCEPT:
    `# ... row == 'a,"b,c"'` matched the equality pattern and pushed the cost past the threshold,
    so the task was graded 'too expensive to game'. Cost must ignore non-executable text."""
    from rewardgate.exploit import ExploitResult

    body = "+    if row == 'a,\"b,c\"':\n+        return ['a', 'b,c']\n"
    commented = body + "".join(
        f"+    # note {i}: handles row == 'a,\"b,c\"' explicitly\n" for i in range(3)
    )
    header = "diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n@@ -1 +1,6 @@\n"
    literals = frozenset({'a,"b,c"', "b,c"})
    bare = ExploitResult(bundle_id="b", exploit_patch=header + body, visible=GREEN,
                         held_out=RED, visible_literals=literals)
    padded = ExploitResult(bundle_id="b", exploit_patch=header + commented, visible=GREEN,
                           held_out=RED, visible_literals=literals)
    assert bare.hardcoded_cases == padded.hardcoded_cases == 1
    assert padded.is_reward_hackable, "comments turned a known-bad task into ACCEPT"


def test_a_fix_on_a_deleted_branch_is_still_found(tmp_path):
    """`--reflog` was unpinned: dropping it left every test green. `git branch -D` is what an author
    does routinely, and without the reflog the fix becomes invisible while `git show` still
    recovers it. (Objects unreachable from the reflog too remain out of scope, as the module
    docstring states.)"""
    from rewardgate.checkers.contamination import detect_git_contamination

    bundle = _repo(tmp_path, {"src/m.py": "def parse(row):\n    return row.split(',')\n"})
    subprocess.run(["git", "checkout", "-q", "-b", "hotfix"], cwd=bundle, check=False,
                   capture_output=True)
    (bundle / "src" / "m.py").write_text("def parse(row):\n    return next(csv.reader([row]))\n")
    subprocess.run(["git", "add", "-A"], cwd=bundle, check=False, capture_output=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fix"],
                   cwd=bundle, check=False, capture_output=True)
    for args in (["checkout", "-q", "-"], ["branch", "-D", "hotfix"]):
        subprocess.run(["git", *args], cwd=bundle, check=False, capture_output=True)

    patch = ("diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n@@ -1,2 +1,2 @@\n"
             "+    return next(csv.reader([row]))\n")
    assert detect_git_contamination(bundle, patch).contaminated, "deleted branch hid the fix"


@pytest.mark.skipif(
    not (Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "bundles"
         / "csvlite-clean").exists(),
    reason="run: uv run python corpus/synthetic/build.py",
)
def test_a_check_that_could_not_run_renders_BLOCKED_not_ok(tmp_path, capsys):
    """The `[BLOCKED]` branch shipped with no test and its mutant survived, so a gold patch that
    fails to apply rendered green again — the regression the branch was written to prevent."""
    from rewardgate.cli import main

    bundle = tmp_path / "b"
    shutil.copytree(
        Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "bundles" / "csvlite-clean",
        bundle, ignore=shutil.ignore_patterns("__pycache__"),
    )
    (bundle / "solution.patch").write_text(
        "diff --git a/src/csvlite/__init__.py b/src/csvlite/__init__.py\n"
        "--- a/src/csvlite/__init__.py\n+++ b/src/csvlite/__init__.py\n@@ -99,4 +99,4 @@\n+ x\n"
    )
    main(["audit", str(bundle), "--no-exploit"])
    out = capsys.readouterr().out
    assert "[BLOCKED] NOP_PASS" in out
    assert "[  ok   ] NOP_PASS" not in out


# --- the diff parser now gates a security property -------------------------------------

@pytest.mark.parametrize(
    "label,patch,expected",
    [
        ("git", "diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n@@ -1 +1 @@\n+x\n", {"src/m.py"}),
        ("posix diff -u", "--- src/m.py\t2026-01-01\n+++ src/m.py\t2026-01-02\n@@ -1 +1 @@\n+x\n", {"src/m.py"}),
        ("path with space", "diff --git a/my file.py b/my file.py\n--- a/my file.py\n+++ b/my file.py\n@@ -1 +1 @@\n+x\n", {"my file.py"}),
        ("rename", "diff --git a/old.py b/new.py\n--- a/old.py\n+++ b/new.py\n@@ -1 +1 @@\n+x\n", {"new.py"}),
        ("no prefix", "--- m.py\n+++ m.py\n@@ -1 +1 @@\n+x\n", {"m.py"}),
    ],
)
def test_the_diff_parser_handles_the_formats_people_actually_produce(label, patch, expected):
    """`files_in_patch` scopes which shipped lines get subtracted from the contamination
    fingerprint, so a path it fails to parse silently disables that guard and resurrects the
    false-REJECT-on-a-clean-bundle regression.

    The old implementation matched only `diff --git a/(\\S+)`: POSIX `diff -u` returned nothing,
    a path with a space returned its first word, and a rename returned the OLD path while the
    added lines live in the new one.
    """
    from rewardgate.diffutil import files_in_patch

    assert files_in_patch(patch) == expected, label


def test_dev_null_is_not_a_file():
    """A creation or deletion hunk names /dev/null on one side; treating it as a path would send
    the contamination checker looking for a file that cannot exist."""
    from rewardgate.diffutil import files_in_patch

    created = "diff --git a/new.py b/new.py\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x\n"
    assert files_in_patch(created) == {"new.py"}


@pytest.mark.parametrize(
    "secret", ["GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK", "SENDGRID_API_KEY",
               "AUTH0_CLIENT_SECRET", "NPM_AUTH_TOKEN"]
)
def test_the_agent_cli_does_not_inherit_the_operators_shell(secret):
    """`execution._test_env()` allowlisted the adjudication subprocess, but the two sites that
    invoke the `claude` CLI passed no `env=` at all — so the agent session inherited everything,
    and since it holds `Bash(python -m pytest:*)`, so did anything it launched.

    A denylist can only enumerate what its author thought of. This machine carried GH_TOKEN,
    AUTH0_CLIENT_SECRET, SENDGRID_API_KEY and a live SSH_AUTH_SOCK that can sign as the user.
    """
    from rewardgate.exploit import agent_env

    os.environ[secret] = "leaked"
    try:
        assert secret not in agent_env()
    finally:
        os.environ.pop(secret, None)


def test_the_agent_still_gets_what_the_cli_needs_to_run():
    """An allowlist that starves the CLI would make every trial fail identically, which reads as
    'the task is unsolvable' rather than 'the harness is broken'."""
    from rewardgate.exploit import agent_env

    env = agent_env()
    assert "PATH" in env and "HOME" in env
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CONFIG_DIR"):
        os.environ[name] = "present"
        try:
            assert name in agent_env(), f"{name} must reach the CLI or authentication breaks"
        finally:
            os.environ.pop(name, None)
