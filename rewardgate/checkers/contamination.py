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
    on_current_branch: bool = False
    error: str = ""

    @property
    def indeterminate(self) -> bool:
        """History could not be read, so no verdict is claimed either way."""
        return bool(self.error)

    @property
    def contaminated(self) -> bool:
        return bool(self.disclosed_lines)

    @property
    def visible_in_shortlog(self) -> bool:
        """Whether a reviewer skimming the default `git log` would have seen the *fix*.

        This asks whether the disclosed content is reachable from the current branch, not whether
        any commit happens to be. An earlier version checked the latter and reported a
        side-branch fix as "visible in the short log" while simultaneously listing that commit as
        hidden — the report contradicted itself.
        """
        return self.on_current_branch

    @property
    def reason(self) -> str:
        if self.error:
            return f"INDETERMINATE — could not read git history: {self.error}"
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


class GitCommandError(RuntimeError):
    """A git invocation failed, so history could not be read.

    Raised rather than returning empty output. An earlier version discarded the return code, which
    made a broken repository indistinguishable from a clean one — the checker reported "contains no
    gold-patch lines" whenever git itself failed. That is precisely the silent failure this
    module's own docstring warns about.
    """


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=60
    )
    if result.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()[:200]}"
        )
    return result.stdout


def detect_git_contamination(bundle_dir: Path, solution_patch: str) -> ContaminationFinding:
    """Scan every ref in `bundle_dir` for lines the gold patch adds."""
    if not (bundle_dir / ".git").exists():
        return ContaminationFinding(has_git=False)

    solution_lines = _significant_solution_lines(solution_patch)
    if not solution_lines:
        # No fingerprint, so history cannot be searched — which is not the same as searching it
        # and finding nothing. This is reachable for real fixes: a deletion-only patch (removing a
        # stray `break`) adds no lines at all, and a missing `solution.patch` arrives here as the
        # empty string. Both used to report "contains no gold-patch lines" and clear the bundle.
        return ContaminationFinding(
            has_git=True,
            error="gold patch adds no line distinctive enough to fingerprint (deletion-only, or absent)",
        )

    def added_lines_in(args: list[str]) -> set[str]:
        return {
            _normalise(line[1:])
            for line in _git(args, bundle_dir).splitlines()
            if line.startswith("+") and not line.startswith("+++")
        }

    try:
        # --all walks every ref, which is what surfaces a fix parked on a side branch.
        disclosed = solution_lines & added_lines_in(["log", "-p", "--all"])
        # The current branch alone is what a reviewer sees by default.
        on_current = bool(solution_lines & added_lines_in(["log", "-p"]))

        commits: list[str] = []
        if disclosed:
            current_lines = set(_git(["log", "--oneline"], bundle_dir).splitlines())
            for line in _git(["log", "--oneline", "--all"], bundle_dir).splitlines():
                marker = "[shortlog]" if line in current_lines else "[hidden]"
                commits.append(f"{marker} {line}")
    except GitCommandError as exc:
        return ContaminationFinding(has_git=True, error=str(exc))

    return ContaminationFinding(
        disclosed_lines=frozenset(disclosed),
        total_solution_lines=len(solution_lines),
        commits=tuple(commits),
        has_git=True,
        on_current_branch=on_current,
    )
