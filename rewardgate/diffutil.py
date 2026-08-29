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


# `+++ b/path` is the authoritative statement of which file a hunk writes to, and every unified
# diff has one. `diff --git` does not: POSIX `diff -u`, `git diff --no-prefix` and hand-written
# patches omit it entirely.
_PLUS_MARKER = re.compile(r'^\+\+\+ (?:b/)?("(?:[^"\\]|\\.)*"|\S.*?)(?:\t.*)?$', re.MULTILINE)


def files_in_patch(patch: str | None) -> set[str]:
    r"""Repository paths a unified diff writes to.

    Reads `+++ b/...` rather than `diff --git a/...`. The old implementation matched only the git
    header with `\S+`, which meant: a POSIX `diff -u` patch returned the empty set, a path with a
    space returned its first word, and a rename returned the *old* path while the added lines live
    in the new one.

    That became load-bearing when contamination scoping started depending on it: an empty set means
    nothing is subtracted from the fingerprint, which resurrects the false-REJECT-on-a-clean-bundle
    regression the subtraction exists to prevent. A parser that silently returns nothing is worse
    than one that raises.
    """
    text = patch or ""
    found = {
        m.group(1)[1:-1].encode().decode("unicode_escape") if m.group(1).startswith('"')
        else m.group(1)
        for m in _PLUS_MARKER.finditer(text)
    }
    found.discard("/dev/null")
    # Fall back to the git header for diffs that declare files but add no lines (deletion-only).
    return {f.strip() for f in found if f.strip()} or set(_DIFF_HEADER.findall(text))


def added_lines_by_file(patch: str | None) -> dict[str, list[str]]:
    r"""Added lines, attributed to the file whose hunk added them.

    `added_lines` flattens a patch into one anonymous pool, which is fine for asking *what* a patch
    introduces and wrong for asking *where*. Contamination scoping needs the second question: a
    line only counts as "the gold patch merely restating existing source" if it already exists in
    **the file that hunk writes to**. Pooling the two lets any file named in the patch cancel
    fingerprint lines belonging to any other, which is a bundle-author-controlled fail-open.

    A `+++` marker is only honoured when the previous line was `---`. Unified diffs always emit the
    pair together, and without that guard an added line whose own content begins with `++` is read
    as a file header, silently reassigning every following line to a path built out of source code.
    """
    out: dict[str, list[str]] = {}
    current, previous = "", ""
    for line in (patch or "").splitlines():
        if line.startswith("diff --git"):
            current = ""
        elif previous.startswith("---") and (m := _PLUS_MARKER.match(line)):
            path = m.group(1)
            if path.startswith('"'):
                path = path[1:-1].encode().decode("unicode_escape")
            current = "" if path.strip() == "/dev/null" else path.strip()
        elif line.startswith("+") and current:
            out.setdefault(current, []).append(line[1:])
        previous = line
    return out


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
