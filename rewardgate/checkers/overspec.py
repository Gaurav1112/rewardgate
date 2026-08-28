"""Over-specification detection.

Solution leakage names the *file*. Over-specification goes further and names the *symbol* — the
function or class the gold patch changes. Once an issue says "fix `_parse_quoted` in the CSV
reader", localisation and diagnosis are both gone, and the task measures only whether the model
can edit a named function.

This is the defect most often introduced with good intentions: an author trying to write a clear
issue writes a specification instead. It is also the one reviewers most often wave through,
because a precise issue *reads* like a high-quality issue.

Symbols are gathered from two places:

* git hunk headers — `@@ -1,4 +1,6 @@ def _parse_quoted(` — where git records the enclosing
  definition, giving the symbol even when the `def` line itself is untouched;
* `def` / `class` statements on changed lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rewardgate.diffutil import files_in_patch

# `@@ -a,b +c,d @@ <enclosing context>` — git's function-context suffix.
_HUNK_CONTEXT = re.compile(r"^@@ [^@]* @@\s*(.+)$", re.MULTILINE)
# A `def`/`class` on any changed or context line of the diff.
_DEFINITION = re.compile(r"^[+\- ]?\s*(?:async\s+)?(?:def|class)\s+(\w+)", re.MULTILINE)
_NAME_IN_CONTEXT = re.compile(r"(?:async\s+)?(?:def|class)\s+(\w+)")

# Identifiers too generic to count as disclosure — naming these reveals nothing specific.
_GENERIC = frozenset(
    {
        "setUp", "tearDown", "main", "run", "test", "wrapper", "inner", "__init__",
        "__str__", "__repr__", "__eq__", "__call__", "get", "set", "add", "remove",
        "update", "value", "data", "result", "self",
    }
)


def symbols_in_patch(patch: str | None) -> set[str]:
    """Return the function and class names a patch defines or sits inside."""
    text = patch or ""
    names = set(_DEFINITION.findall(text))
    for context in _HUNK_CONTEXT.findall(text):
        names.update(_NAME_IN_CONTEXT.findall(context))
    return {n for n in names if n not in _GENERIC and len(n) > 2}


def _mentions(statement: str, symbol: str) -> bool:
    """Whole-word match, so `parse` does not match inside `parser` or `reparse`."""
    return re.search(rf"\b{re.escape(symbol)}\b", statement) is not None


@dataclass(frozen=True)
class OverSpecFinding:
    """Evidence that an issue names the symbols its own fix modifies.

    Symbol visibility is the discriminator, and getting this wrong inflates the defect rate by
    roughly five-fold. A reporter naming a *public* symbol is describing what they called —
    "``Table.write`` drops the ``formats`` argument" is a good issue, not a leaked solution. A
    reporter naming a *private* symbol such as ``_format_float`` is naming an internal the fix
    must touch, which they could not have known without reading the patch.

    Measured on SWE-bench Verified: counting any named symbol flags 229/500 (45.8%); counting
    only private symbols flags 42/500 (8.4%). The public-only remainder is dominated by ordinary
    API references, so only the private signal is treated as a defect.
    """

    named_symbols: frozenset[str] = field(default_factory=frozenset)
    total_symbols: int = 0
    names_a_file: bool = False

    @property
    def private_symbols(self) -> frozenset[str]:
        """Named symbols that are module-internal by convention."""
        return frozenset(s for s in self.named_symbols if s.startswith("_"))

    @property
    def public_symbols(self) -> frozenset[str]:
        """Named symbols that form part of the public API — informational, not a defect."""
        return frozenset(s for s in self.named_symbols if not s.startswith("_"))

    @property
    def over_specified(self) -> bool:
        """True only when the issue names an internal symbol the fix modifies."""
        return bool(self.private_symbols)

    @property
    def severity(self) -> str:
        """`high` when a non-dunder internal *and* the target file are both named."""
        private = self.private_symbols
        if not private:
            return "none"
        non_dunder = {s for s in private if not s.startswith("__")}
        if non_dunder and self.names_a_file:
            return "high"
        return "medium" if non_dunder else "low"

    @property
    def reason(self) -> str:
        if not self.over_specified:
            if self.public_symbols:
                return (
                    "issue names only public API symbols "
                    f"({', '.join(sorted(self.public_symbols))}) — normal for a bug report"
                )
            return "issue does not name any modified symbol"
        named = ", ".join(sorted(self.private_symbols))
        scope = "the target file and " if self.names_a_file else ""
        return f"issue names {scope}internal symbol(s) the fix modifies: {named}"


def detect_over_specification(
    problem_statement: str | None, patch: str | None
) -> OverSpecFinding:
    """Detect whether `problem_statement` names symbols that `patch` modifies."""
    statement = problem_statement or ""
    if not statement:
        return OverSpecFinding()

    symbols = symbols_in_patch(patch)
    named = {s for s in symbols if _mentions(statement, s)}
    names_file = any(f in statement for f in files_in_patch(patch))

    return OverSpecFinding(
        named_symbols=frozenset(named),
        total_symbols=len(symbols),
        names_a_file=names_file,
    )
