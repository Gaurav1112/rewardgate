"""Unified-diff parsing shared by the checkers.

Task bundles arrive as diffs, not as source trees, so every checker needs the same small set of
operations: which files does this patch touch, and what lines does it add. Keeping them here means
one parser to get right rather than four.
"""

from __future__ import annotations

import re

_DIFF_HEADER = re.compile(r"^diff --git a/(\S+)", re.MULTILINE)
# `+++ b/path` and `--- a/path` are file markers, not content, despite starting with +/-.
_FILE_MARKER = re.compile(r"^(\+\+\+|---)\s")


def files_in_patch(patch: str | None) -> set[str]:
    """Return the set of repository paths a unified diff modifies."""
    return set(_DIFF_HEADER.findall(patch or ""))


def added_lines(patch: str | None) -> list[str]:
    """Return the content of every added line, with the leading `+` stripped.

    File markers (`+++ b/...`) are excluded so they cannot be mistaken for added source.
    """
    out: list[str] = []
    for line in (patch or "").splitlines():
        if line.startswith("+") and not _FILE_MARKER.match(line):
            out.append(line[1:])
    return out


def added_source(patch: str | None) -> str:
    """Added lines rejoined into a source block, for AST parsing."""
    return "\n".join(added_lines(patch))


def test_files_in_patch(patch: str | None) -> set[str]:
    """Paths that look like test files.

    Heuristic, and deliberately broad: a false positive here only means we analyse an extra file,
    whereas a false negative means we silently skip the file that matters.
    """
    return {
        p
        for p in files_in_patch(patch)
        if "test" in p.rsplit("/", 1)[-1].lower() or "/tests/" in f"/{p}"
    }
