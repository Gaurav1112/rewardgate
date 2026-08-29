"""Solution-leakage detection.

A benchmark task leaks its solution when the issue text hands the agent the answer. The most
common form is naming the file the gold patch modifies: the agent no longer has to localise the
bug, which is the skill the task claims to measure.

This checker is deterministic — no model call, no cost. That matters twice over: it is free to
run on every instance, and its output is a fact a reviewer can re-derive rather than an opinion
they must trust.

Validation
----------
"The SWE-bench Illusion" (arXiv:2506.12286) reports 135 of 500 SWE-bench Verified instances
leaking the gold file. This detector measures 133/500 (107 on a full path, 26 more on a bare
basename).

**Those are not the same measurement.** The paper's heuristic, per its §4.2, also fires on import
statements and is never specified precisely enough to reimplement; mine fires on the basename.
Two independently written heuristics landing in the same place is corroboration that the leakage
is real and roughly this common. It is not a reproduction of their figure, and an earlier version
of this docstring called it "a two-instance difference", which claimed more than the comparison
supports.

What the third-party corpus does establish is narrower and still worth having: the detector is
exercised against a defect set the author did not create and could not tune against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rewardgate.diffutil import files_in_patch

__all__ = [
    "LeakageFinding",
    "detect_solution_leakage",
    "files_in_patch",
    "named_only_in_traceback",
]

_FRAME = re.compile(r'^\s*File "[^"]+", line \d+')
_EXCEPTION = re.compile(r"^\w*(Error|Exception|Warning)\b")


def _traceback_lines(statement: str) -> set[int]:
    """Indices of lines belonging to a pasted Python traceback."""
    inside, marked = False, set()
    for i, line in enumerate(statement.splitlines()):
        if "Traceback (most recent call last)" in line:
            inside = True
        if _FRAME.match(line):
            inside, _ = True, marked.add(i)
            continue
        if inside:
            if not line.strip() or re.match(r"\s", line) or _EXCEPTION.match(line.strip()):
                marked.add(i)
            else:
                inside = False
    return marked


def named_only_in_traceback(problem_statement: str | None, finding: "LeakageFinding") -> bool:
    """Whether every mention of the gold file sits inside a pasted traceback.

    This is the checker's weakest case and it is worth separating rather than defending. A stack
    trace naming the file is ordinary bug-report content — the reporter pasted what their console
    printed, they did not point at the fix. Counting it as "the issue text discloses the solution"
    conflates a reporting convention with an authoring error.

    It is not simply a false positive either, which is why the strict figure is reported alongside
    the headline rather than replacing it: an agent reading that traceback *does* learn which file
    to open, and localisation is exactly the skill the task claims to measure. Both readings are
    defensible, so both numbers are published and the reader picks.
    """
    if not finding.leaked:
        return False
    statement = problem_statement or ""
    needles = tuple(finding.leaked_paths) + tuple(finding.leaked_basenames)
    marked = _traceback_lines(statement)
    return not any(
        i not in marked and any(n in line for n in needles)
        for i, line in enumerate(statement.splitlines())
    )


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
