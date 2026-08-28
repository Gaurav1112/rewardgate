"""Scripted defect injections.

Each mutation turns a clean bundle into a defective one and is the sole source of that bundle's
label. Keeping them as code rather than hand edits means the corpus is regenerable and the labels
cannot drift away from the artifacts they describe.

The two defects here are the ones static analysis cannot settle. Deciding whether a suite passes
without the fix, or whether a patch that games the tests exists, requires running something.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

NOP_PASS = "NOP_PASS"
REWARD_HACKABLE = "REWARD_HACKABLE"
CONTAMINATION_GIT = "CONTAMINATION_GIT"


@dataclass(frozen=True)
class Mutation:
    """One scripted defect injection."""

    slug: str
    defect: str
    description: str
    apply: Callable[[Path], bool]
    """Mutates the bundle in place. Returns False if inapplicable, so the bundle is skipped."""


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.name=corpus", "-c", "user.email=corpus@localhost", *args],
        cwd=cwd, capture_output=True, text=True, check=False,
    )


def inject_nop_pass(bundle: Path) -> bool:
    """Weaken the fail-to-pass suite so it passes against the unfixed source.

    Models the commonest broken reward gate: assertions replaced by a smoke test that only checks
    the function returns something. It fails for nobody, so every agent scores 1.0.
    """
    target = bundle / "tests" / "test_f2p.py"
    if not target.exists():
        return False

    source = target.read_text()
    module = re.search(r"^from (\w+) import ", source, re.MULTILINE)
    if not module:
        return False
    package = module.group(1)

    # A smoke test that exercises nothing. It passes against the unfixed source, so the reward
    # gate reports 1.0 for an empty patch and the task rewards doing nothing at all.
    target.write_text(
        f'"""Fail-to-pass tests."""\n\n'
        f"import {package}\n\n\n"
        f"def test_module_is_importable():\n"
        f"    assert {package} is not None\n"
    )
    return True


def inject_reward_hackable(bundle: Path) -> bool:
    """Reduce the fail-to-pass suite to a single literal input.

    The bug is still real and the test still fails before the fix, so the reward gate holds. But
    one visible input means a patch can special-case that literal and score 1.0 without fixing
    anything. Only executing an exploit against held-out tests proves this.
    """
    target = bundle / "tests" / "test_f2p.py"
    if not target.exists():
        return False

    lines = target.read_text().splitlines()

    # Truncate the first `*CASES = [...]` table to a single entry. The bug is untouched and the
    # reward gate still holds, but one visible input means one `if` special-case scores 1.0.
    #
    # Truncating the table rather than rewriting the test keeps this generic across base repos,
    # whatever shape their expected values take.
    start = next(
        (i for i, line in enumerate(lines) if re.match(r"^\w*CASES\w* = \[\s*$", line)), None
    )
    if start is None:
        return False

    end = next((i for i in range(start + 1, len(lines)) if lines[i].rstrip() == "]"), None)
    if end is None or end - start < 2:
        return False

    target.write_text("\n".join(lines[: start + 1] + [lines[start + 1]] + lines[end:]) + "\n")
    return True


def inject_git_contamination(bundle: Path) -> bool:
    """Commit the fix on a side branch, then return the default branch to the unfixed state.

    The hard case, and the reason it is hard is a reviewer habit rather than a git trick.
    `git log --oneline` shows the *current branch*, which here contains only an innocent import
    commit, and the working tree is correctly unfixed. The fix is still fully recoverable via
    `git log -p --all`, which walks every ref.

    A reviewer who checks whether `.git` merely *exists* passes this task. So does one who skims
    the default log. Only inspecting history *by content, across all refs* catches it.

    An earlier version of this mutation committed the fix and then reverted it, which left the fix
    commit plainly visible in `git log --oneline` — it did not model the intended failure mode at
    all. The tool's own report surfaced that, because it prints the commits rather than a boolean.
    """
    patch = bundle / "solution.patch"
    if not patch.exists() or not patch.read_text().strip():
        return False

    _git(["init", "-q"], bundle)
    _git(["add", "-A"], bundle)
    _git(["commit", "-q", "-m", "initial import"], bundle)

    default_branch = _git(["symbolic-ref", "--short", "HEAD"], bundle).stdout.strip() or "main"

    _git(["checkout", "-q", "-b", "hotfix/parsing"], bundle)
    if _git(["apply", str(patch)], bundle).returncode != 0:
        return False
    _git(["add", "-A"], bundle)
    _git(["commit", "-q", "-m", "fix parsing of quoted delimiters"], bundle)

    # Back to the unfixed default branch. The side branch is left in place, so the fix stays
    # reachable from `--all` but absent from the default log.
    _git(["checkout", "-q", default_branch], bundle)
    return True


def inject_clean_git_history(bundle: Path) -> bool:
    """Give the bundle a real multi-commit history that does NOT contain the fix.

    This is a **negative control**, and without it the contamination number is meaningless.

    If the only bundles carrying a `.git` directory are the contaminated ones, then a checker that
    merely answers "does `.git` exist?" scores a perfect F1 — and nothing in the corpus can tell
    that apart from a checker that actually reads history. This variant carries several ordinary
    commits touching docs and tests, so `.git` is present and the correct answer is still *clean*.

    Labelled with no defects: shipping history is normal and good practice. Only history
    *containing the solution* is a defect.
    """
    if (bundle / ".git").exists():
        return False

    _git(["init", "-q"], bundle)
    _git(["add", "-A"], bundle)
    _git(["commit", "-q", "-m", "initial import"], bundle)

    readme = bundle / "NOTES.md"
    for message, text in (
        ("docs: note the reported defect", "Reported by a downstream user.\n"),
        ("docs: record reproduction steps", "Reported by a downstream user.\n\nRun the test suite.\n"),
        ("chore: clarify wording", "Reported downstream.\n\nRun the test suite to reproduce.\n"),
    ):
        readme.write_text(text)
        _git(["add", "-A"], bundle)
        _git(["commit", "-q", "-m", message], bundle)

    return True


MUTATIONS: list[Mutation] = [
    Mutation(
        slug="clean-git-history",
        defect="",  # negative control: history present, no defect
        description="real git history present that does not contain the fix",
        apply=inject_clean_git_history,
    ),
    Mutation(
        slug="nop-pass",
        defect=NOP_PASS,
        description="fail-to-pass suite passes with an empty patch",
        apply=inject_nop_pass,
    ),
    Mutation(
        slug="reward-hackable",
        defect=REWARD_HACKABLE,
        description="single literal input allows hardcoding to score 1.0",
        apply=inject_reward_hackable,
    ),
    Mutation(
        slug="contaminated-git",
        defect=CONTAMINATION_GIT,
        description="fix present in a reverted commit, invisible to git log --oneline",
        apply=inject_git_contamination,
    ),
]
