"""Git-history contamination detection.

A task is contaminated when the fix is recoverable from the repository shipped with it. The
working tree can be correctly unfixed and `git log --oneline` can look entirely innocent while the
solution still sits in a reverted commit, an abandoned branch, or a dangling object.

This is why the reviewing rule is *inspect `.git` by content, not by presence*. Checking whether a
`.git` directory exists tells you nothing: a squashed baseline reveals no more than no history at
all, whereas a history containing the fix is disqualifying.

`git log -p --all` covers every ref rather than just the current branch, which is what catches the
reverted-commit case.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from rewardgate.diffutil import added_lines

_MIN_SIGNIFICANT_LENGTH = 12
_COMMENT = re.compile(r"^\s*(#|//|\*)")


def _normalise(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _significant_solution_lines(patch: str) -> set[str]:
    """Lines the gold patch adds that are distinctive enough to identify it."""
    return {
        norm
        for raw in added_lines(patch)
        if not _COMMENT.match(raw) and len(norm := _normalise(raw)) >= _MIN_SIGNIFICANT_LENGTH
    }


@dataclass(frozen=True)
class ContaminationFinding:
    """Evidence that the shipped history discloses the fix."""

    disclosed_lines: frozenset[str] = field(default_factory=frozenset)
    total_solution_lines: int = 0
    commits: tuple[str, ...] = field(default_factory=tuple)
    has_git: bool = False

    @property
    def contaminated(self) -> bool:
        return bool(self.disclosed_lines)

    @property
    def visible_in_shortlog(self) -> bool:
        """Whether a reviewer skimming `git log --oneline` would have seen it."""
        return any("[shortlog]" in c for c in self.commits)

    @property
    def reason(self) -> str:
        if not self.has_git:
            return "no git history shipped with the bundle"
        if not self.contaminated:
            return "git history present and contains no gold-patch lines"
        where = "visible in the short log" if self.visible_in_shortlog else (
            "hidden from `git log --oneline`; only reachable via `git log -p --all`"
        )
        return (
            f"git history discloses {len(self.disclosed_lines)} of "
            f"{self.total_solution_lines} gold-patch lines — {where}"
        )


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=60
    )
    return result.stdout


def detect_git_contamination(bundle_dir: Path, solution_patch: str) -> ContaminationFinding:
    """Scan every ref in `bundle_dir` for lines the gold patch adds."""
    if not (bundle_dir / ".git").exists():
        return ContaminationFinding(has_git=False)

    solution_lines = _significant_solution_lines(solution_patch)
    if not solution_lines:
        return ContaminationFinding(has_git=True)

    # --all covers every ref, which is what surfaces a fix that was committed then reverted.
    history = _git(["log", "-p", "--all"], bundle_dir)
    added_in_history = {
        _normalise(line[1:])
        for line in history.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    }
    disclosed = solution_lines & added_in_history

    commits: list[str] = []
    if disclosed:
        shortlog = _git(["log", "--oneline", "--all"], bundle_dir)
        current = _git(["log", "--oneline"], bundle_dir)
        for line in shortlog.splitlines():
            marker = "[shortlog]" if line in current.splitlines() else "[hidden]"
            commits.append(f"{marker} {line}")

    return ContaminationFinding(
        disclosed_lines=frozenset(disclosed),
        total_solution_lines=len(solution_lines),
        commits=tuple(commits),
        has_git=True,
    )
