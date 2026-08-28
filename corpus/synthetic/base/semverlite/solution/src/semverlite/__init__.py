"""Semantic-version comparison.

The bug is a genuine specification subtlety rather than a typo: SemVer says a pre-release version
sorts *before* its own release, so `1.0.0-alpha` precedes `1.0.0`. Comparing the numeric triple
alone makes them equal, which is wrong in a way that ordinary version strings never reveal.
"""

from __future__ import annotations

__all__ = ["compare"]


def _numeric_parts(version: str) -> tuple[int, ...]:
    core = version.split("-", 1)[0]
    return tuple(int(part) for part in core.split("."))


def _prerelease(version: str) -> str | None:
    return version.split("-", 1)[1] if "-" in version else None


def compare(left: str, right: str) -> int:
    """Return -1, 0 or 1 as `left` sorts before, with, or after `right`."""
    a, b = _numeric_parts(left), _numeric_parts(right)
    if a < b:
        return -1
    if a > b:
        return 1

    # Equal cores: absence of a pre-release sorts after its presence.
    pre_a, pre_b = _prerelease(left), _prerelease(right)
    if pre_a == pre_b:
        return 0
    if pre_a is None:
        return 1
    if pre_b is None:
        return -1
    if pre_a < pre_b:
        return -1
    return 1
