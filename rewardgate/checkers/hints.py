"""Hint-channel contamination detection.

SWE-bench instances carry a `hints_text` field holding comments made on the issue before the fix
landed. It is metadata, not part of the task — but harnesses routinely concatenate it into the
prompt, and when a maintainer replied with the patch, the agent is handed the answer.

This checker asks a narrow, mechanical question: does the hint channel already contain lines the
gold patch adds? If so, an agent reading hints retrieves rather than reasons, and any score the
task produces is measuring recall of the issue thread.

Comparison is on normalised code lines. Whitespace is collapsed so reformatting does not hide a
match, and trivial lines are ignored so that `return` or `)` cannot manufacture a false positive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rewardgate.diffutil import added_lines

_MIN_SIGNIFICANT_LENGTH = 12
_COMMENT = re.compile(r"^\s*(#|//|\*|/\*)")


def _normalise(line: str) -> str:
    """Collapse whitespace so formatting differences do not mask a match."""
    return re.sub(r"\s+", " ", line).strip()


def _significant_added_lines(patch: str | None) -> set[str]:
    """Added code lines substantial enough that appearing verbatim in a hint is meaningful."""
    out = set()
    for raw in added_lines(patch):
        if _COMMENT.match(raw):
            continue
        norm = _normalise(raw)
        if len(norm) >= _MIN_SIGNIFICANT_LENGTH:
            out.add(norm)
    return out


@dataclass(frozen=True)
class HintFinding:
    """Evidence that the hint channel discloses part of the gold patch."""

    disclosed_lines: frozenset[str] = field(default_factory=frozenset)
    total_significant_lines: int = 0
    hints_present: bool = False

    @property
    def contaminated(self) -> bool:
        return bool(self.disclosed_lines)

    @property
    def disclosure_ratio(self) -> float:
        """Fraction of the gold patch's significant lines that appear in the hints."""
        if not self.total_significant_lines:
            return 0.0
        return len(self.disclosed_lines) / self.total_significant_lines

    @property
    def reason(self) -> str:
        if not self.hints_present:
            return "no hint text on this instance"
        if not self.contaminated:
            return "hint text present but discloses no patch lines"
        return (
            f"hint text contains {len(self.disclosed_lines)} of "
            f"{self.total_significant_lines} gold-patch lines "
            f"({self.disclosure_ratio:.0%})"
        )


def detect_hint_contamination(hints_text: str | None, patch: str | None) -> HintFinding:
    """Detect whether `hints_text` reproduces lines added by `patch`."""
    hints = hints_text or ""
    if not hints.strip():
        return HintFinding(hints_present=False)

    normalised_hints = _normalise(hints)
    significant = _significant_added_lines(patch)
    disclosed = {line for line in significant if line in normalised_hints}

    return HintFinding(
        disclosed_lines=frozenset(disclosed),
        total_significant_lines=len(significant),
        hints_present=True,
    )
