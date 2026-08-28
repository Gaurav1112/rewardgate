"""Solution-leakage detection.

A benchmark task leaks its solution when the issue text hands the agent the answer. The most
common form is naming the file the gold patch modifies: the agent no longer has to localise the
bug, which is the skill the task claims to measure.

This checker is deterministic — no model call, no cost. That matters twice over: it is free to
run on every instance, and its output is a fact a reviewer can re-derive rather than an opinion
they must trust.

Validation
----------
"The SWE-bench Illusion" (arXiv:2506.12286) reports that 135 of the 500 SWE-bench Verified
instances embed the gold file path in the issue text. Running `basename` matching over the public
dataset reproduces 133/500 — a two-instance difference from an independent research group.

That agreement is the point. The detector is checked against a defect set the author did not
create and could not tune against.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rewardgate.diffutil import files_in_patch

__all__ = ["LeakageFinding", "detect_solution_leakage", "files_in_patch"]


@dataclass(frozen=True)
class LeakageFinding:
    """Evidence that an issue text discloses part of its own solution.

    `leaked_paths` and `leaked_basenames` are kept separate because they carry different weight:
    a full path is unambiguous disclosure, while a basename may coincide with ordinary prose (a
    module named `compat.py` discussed by name). Reporting both lets a reviewer judge borderline
    cases instead of trusting a single collapsed boolean.
    """

    leaked_paths: frozenset[str] = field(default_factory=frozenset)
    leaked_basenames: frozenset[str] = field(default_factory=frozenset)

    @property
    def leaked(self) -> bool:
        """True when the issue names a modified file by path or by basename."""
        return bool(self.leaked_paths or self.leaked_basenames)

    @property
    def confidence(self) -> str:
        """`high` for a full-path match, `medium` for basename only, `none` otherwise."""
        if self.leaked_paths:
            return "high"
        return "medium" if self.leaked_basenames else "none"


def detect_solution_leakage(problem_statement: str | None, patch: str | None) -> LeakageFinding:
    """Detect whether `problem_statement` names any file that `patch` modifies."""
    statement = problem_statement or ""
    if not statement:
        return LeakageFinding()

    paths = files_in_patch(patch)
    leaked_paths = {p for p in paths if p in statement}

    # Only consider basenames for paths that did not already match in full, so a single file
    # cannot be counted as evidence twice.
    leaked_basenames = {
        p.rsplit("/", 1)[-1]
        for p in paths - leaked_paths
        if p.rsplit("/", 1)[-1] in statement
    }

    return LeakageFinding(
        leaked_paths=frozenset(leaked_paths),
        leaked_basenames=frozenset(leaked_basenames),
    )
