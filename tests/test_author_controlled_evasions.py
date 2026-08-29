"""Evasions available to the person who assembles the bundle.

Every other test in this suite asks whether a checker is *correct*. These ask whether it is
**correct against an adversary who supplies its input**, which is the situation this tool is
actually in: a benchmark author submits the tree, the history and the gold patch, and the audit
reads all three. Anything the author can shape, the author can shape to suppress the audit.

The two defects below were found by adversarial review, disclosed in SUBMISSION.md rather than
patched at the time, and are fixed here. Both fail *open* — the bundle is certified clean — which
is the only failure direction that matters for a gate.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from rewardgate.checkers.contamination import detect_git_contamination
from rewardgate.exploit import _prepare_sandbox, capture_exploit_patch

FIX = "        return round(total / count, 2)"
BUG = "        return total / count"


def _git(args: list[str], cwd: Path) -> None:
    identity = ["-c", "user.name=t", "-c", "user.email=t@localhost"]
    subprocess.run(["git", *identity, *args], cwd=cwd, capture_output=True, check=True)


# --- a shipped `.gitignore` that hides the only directory the agent may edit -----------------


def _sandbox_with(tmp_path: Path, gitignore: str | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "calc.py").write_text("def mean(xs):\n" + BUG + "\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text("def test_ok():\n    assert True\n")
    if gitignore is not None:
        (repo / ".gitignore").write_text(gitignore)
    _prepare_sandbox(repo)
    return repo


def test_a_gitignored_src_directory_does_not_swallow_the_exploit(tmp_path):
    """`src/` in the bundle's own `.gitignore` used to make every captured diff empty.

    The agent would write a working exploit, the harness would record no patch, and the verdict
    would read `RESISTED (no exploit found)` — a bundle certifying itself clean by shipping one
    line of config. `git add -f` overrides every ignore source, the shipped file included.
    """
    repo = _sandbox_with(tmp_path, gitignore="src/\n")
    (repo / "src" / "calc.py").write_text("def mean(xs):\n" + FIX + "\n")

    patch, error = capture_exploit_patch(repo)
    assert not error
    assert FIX.strip() in patch, "the agent's edit to an ignored path must still be captured"


def test_the_same_holds_for_an_exploit_written_into_a_new_ignored_file(tmp_path):
    """The `Write`-a-new-module evasion and the `.gitignore` evasion compose."""
    repo = _sandbox_with(tmp_path, gitignore="src/\n*.py\n")
    (repo / "src" / "lookup.py").write_text("TABLE = {'a,\"b,c\"': ['a', 'b,c']}\n")

    patch, error = capture_exploit_patch(repo)
    assert not error
    assert "lookup.py" in patch


def test_bytecode_left_by_the_agents_own_pytest_run_is_not_a_dirty_tree(tmp_path):
    """`add` excluded `__pycache__` while `status` did not, so the two disagreed.

    A trial where the agent changed nothing then reported the harness error 'agent modified the
    tree but no diff could be captured' instead of the real finding, that no exploit was found.
    """
    repo = _sandbox_with(tmp_path)
    (repo / "src" / "__pycache__").mkdir()
    (repo / "src" / "__pycache__" / "calc.pyc").write_bytes(b"\x00stale")

    assert capture_exploit_patch(repo) == ("", "")


def test_a_real_edit_is_still_reported_when_bytecode_is_also_present(tmp_path):
    """The exclusion must not be so broad that it hides the finding along with the noise."""
    repo = _sandbox_with(tmp_path)
    (repo / "src" / "__pycache__").mkdir()
    (repo / "src" / "__pycache__" / "calc.pyc").write_bytes(b"\x00stale")
    (repo / "src" / "calc.py").write_text("def mean(xs):\n" + FIX + "\n")

    patch, error = capture_exploit_patch(repo)
    assert not error and FIX.strip() in patch


# --- a decoy file that erases the contamination fingerprint ----------------------------------


def _contaminated_bundle(tmp_path: Path, decoy: bool) -> tuple[Path, str]:
    """A bundle whose fix sits on an abandoned side branch, optionally with a decoy file.

    The decoy is the evasion: `src/notes.py` contains the fix line as ordinary source, and the gold
    patch is written to touch `notes.py` as well as `calc.py`. The subtraction that stops a gold
    patch being fingerprinted by lines it merely restates then cancels the *real* fingerprint,
    because the file supplying the cancelling text is chosen by the same person who writes the
    patch.
    """
    bundle = tmp_path / "bundle"
    (bundle / "src").mkdir(parents=True)
    (bundle / "src" / "calc.py").write_text("def mean(xs):\n" + BUG + "\n")
    if decoy:
        (bundle / "src" / "notes.py").write_text("def _unused():\n" + FIX + "\n")

    _git(["init", "-q"], bundle)
    _git(["add", "-A"], bundle)
    _git(["commit", "-q", "-m", "initial import"], bundle)

    _git(["checkout", "-q", "-b", "wip"], bundle)
    (bundle / "src" / "calc.py").write_text("def mean(xs):\n" + FIX + "\n")
    _git(["commit", "-qam", "wip: rounding"], bundle)
    _git(["checkout", "-q", "-"], bundle)  # the fix is now unreachable from the default log

    patch = (
        "--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1,2 +1,2 @@\n"
        " def mean(xs):\n" + f"-{BUG}\n+{FIX}\n"
    )
    if decoy:
        patch += (
            "--- a/src/notes.py\n+++ b/src/notes.py\n@@ -1,2 +1,3 @@\n"
            " def _unused():\n" + f" {FIX}\n+    return None\n"
        )
    return bundle, patch


def test_the_side_branch_fix_is_detected_without_a_decoy(tmp_path):
    """Control: the fixture is a genuine contamination that the checker already catches."""
    bundle, patch = _contaminated_bundle(tmp_path, decoy=False)
    finding = detect_git_contamination(bundle, patch)
    assert finding.contaminated and not finding.visible_in_shortlog


def test_a_decoy_file_named_in_the_gold_patch_cannot_erase_the_fingerprint(tmp_path):
    """The evasion, and the reason the subtraction is now per-file.

    `notes.py` may cancel lines the patch adds *to notes.py*. It must not cancel the line the patch
    adds to `calc.py`, which is the one sitting in the abandoned branch.
    """
    bundle, patch = _contaminated_bundle(tmp_path, decoy=True)
    finding = detect_git_contamination(bundle, patch)
    assert not finding.indeterminate, finding.reason
    assert finding.contaminated, finding.reason
    assert any(c.startswith("[hidden]") for c in finding.commits)


def test_a_gold_patch_restating_its_own_files_lines_is_still_not_a_fingerprint(tmp_path):
    """The regression the subtraction exists to prevent, re-pinned at the narrower scope.

    A hunk regenerated with less context restates unchanged lines of the file it patches. Those
    appear in the innocent baseline commit, and counting them accused a clean bundle of leaking.
    """
    bundle = tmp_path / "clean"
    (bundle / "src").mkdir(parents=True)
    (bundle / "src" / "calc.py").write_text("def mean(xs):\n    count = len(xs)\n" + BUG + "\n")
    _git(["init", "-q"], bundle)
    _git(["add", "-A"], bundle)
    _git(["commit", "-q", "-m", "initial import"], bundle)

    # Every added line is already in the shipped file: a no-op re-statement, not a fix.
    patch = (
        "--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1,3 +1,3 @@\n"
        " def mean(xs):\n+    count = len(xs)\n" + f" {BUG}\n"
    )
    assert not detect_git_contamination(bundle, patch).contaminated
