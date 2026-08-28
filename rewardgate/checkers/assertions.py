"""Weak-assertion detection in fail-to-pass tests.

A fail-to-pass test is the reward signal of a benchmark task. If it fails before the patch and
passes after, but never actually checks the behaviour in question, the task rewards any change
that happens to clear an import error or a crash. The test looks rigorous and measures nothing.

The classic shapes:

* no assertion at all in the test body;
* `assert result is not None` as the only check — true for almost every non-crashing value;
* `assert True` / `assert 1`, which is vacuous;
* a bare `except: pass` that swallows the very failure the test should surface.

Detection is AST-based rather than regex-based because the distinction that matters is
*structural*: whether an assertion constrains the value, not whether the word "assert" appears.

Honest-failure policy
---------------------
A diff hunk starting mid-function is not parseable Python. When that happens this checker returns
`parse_ok=False` and declines to give a verdict, rather than defaulting to "clean". A tool that
audits benchmarks for silent failure must not itself fail silently.
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field

from rewardgate.diffutil import added_source

# Calls that assert existence but not value. Passing these tells you almost nothing.
_VACUOUS_CALLS = frozenset(
    {"assertIsNotNone", "assertIsNone", "assertTrue", "assertFalse", "assertIsInstance"}
)


def _is_vacuous_compare(node: ast.expr) -> bool:
    """True for `x is not None` / `x != None` and their negations."""
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return False
    if not isinstance(node.ops[0], (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)):
        return False
    return any(isinstance(c, ast.Constant) and c.value is None for c in node.comparators)


def _is_vacuous_constant(node: ast.expr) -> bool:
    """True for `assert True`, `assert 1`, `assert "text"` — always-true literals."""
    return isinstance(node, ast.Constant) and bool(node.value)


@dataclass(frozen=True)
class AssertionFinding:
    """Structural assessment of one test function."""

    test_name: str
    assertion_count: int = 0
    vacuous_count: int = 0
    swallows_exceptions: bool = False

    @property
    def substantive_count(self) -> int:
        """Assertions that actually constrain a value."""
        return self.assertion_count - self.vacuous_count

    @property
    def is_weak(self) -> bool:
        """A test is weak when nothing it does can distinguish right from wrong."""
        return self.substantive_count <= 0 or self.swallows_exceptions

    @property
    def reason(self) -> str:
        """Human-readable justification, for the audit report."""
        if self.assertion_count == 0:
            return "no assertion in test body"
        if self.substantive_count <= 0:
            return f"only vacuous assertions ({self.vacuous_count} of {self.assertion_count})"
        if self.swallows_exceptions:
            return "bare except swallows the failure the test should surface"
        return "substantive assertions present"


@dataclass(frozen=True)
class AssertionReport:
    """Result of analysing every test function added by a patch."""

    parse_ok: bool
    findings: tuple[AssertionFinding, ...] = field(default_factory=tuple)
    parse_error: str = ""

    @property
    def indeterminate(self) -> bool:
        """True when the diff could not be parsed, so no verdict is claimed."""
        return not self.parse_ok

    @property
    def weak_tests(self) -> tuple[AssertionFinding, ...]:
        return tuple(f for f in self.findings if f.is_weak)

    @property
    def has_weak_assertions(self) -> bool:
        return bool(self.weak_tests)


class _TestBodyVisitor(ast.NodeVisitor):
    """Counts assertions within a single test function, not descending into nested defs."""

    def __init__(self) -> None:
        self.assertions = 0
        self.vacuous = 0
        self.swallows = False

    def visit_Assert(self, node: ast.Assert) -> None:
        self.assertions += 1
        if _is_vacuous_compare(node.test) or _is_vacuous_constant(node.test):
            self.vacuous += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = node.func.attr if isinstance(node.func, ast.Attribute) else (
            node.func.id if isinstance(node.func, ast.Name) else ""
        )
        if name.startswith("assert"):
            self.assertions += 1
            if name in _VACUOUS_CALLS:
                self.vacuous += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Flag handlers that discard the failure the test exists to surface.

        Only inert bodies count: `pass`, `...`, or a bare docstring. An earlier version treated
        any `ast.Expr` as inert, which matched ordinary calls — so
        `except ValueError: self.fail("should not raise")` and `except X: print(...)` were graded
        as swallowing exceptions despite doing the opposite.
        """
        def inert(stmt: ast.stmt) -> bool:
            if isinstance(stmt, ast.Pass):
                return True
            return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)

        if node.body and all(inert(stmt) for stmt in node.body):
            self.swallows = True
        self.generic_visit(node)


_DEF_TEST = re.compile(r"^(\s*)(?:async\s+)?def\s+(test\w*)\s*\(")
_DECORATOR = re.compile(r"^\s*@")


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip())


def _extract_test_blocks(source: str) -> list[str]:
    """Recover individual `def test_*` blocks from a partial diff hunk.

    Most real `test_patch` hunks edit an existing file, so the added lines are a fragment rather
    than a module and will not parse as a whole. Each test function, however, is usually added
    intact. Pulling those out one at a time and dedenting them recovers the majority of cases that
    whole-source parsing loses.
    """
    lines = source.splitlines()
    blocks: list[str] = []

    for i, line in enumerate(lines):
        match = _DEF_TEST.match(line)
        if not match:
            continue
        indent = len(match.group(1))

        # Walk backwards over contiguous decorators at the same indentation.
        start = i
        while start > 0 and _DECORATOR.match(lines[start - 1]) and _indent_width(lines[start - 1]) == indent:
            start -= 1

        # Walk forwards while lines are blank or indented deeper than the `def`.
        end = i + 1
        while end < len(lines) and (not lines[end].strip() or _indent_width(lines[end]) > indent):
            end += 1

        block = textwrap.dedent("\n".join(lines[start:end]))
        if block.strip():
            blocks.append(block)

    return blocks


def _parse(source: str) -> tuple[ast.Module | None, str]:
    """Parse added lines, falling back to per-test-function block recovery.

    Order matters: whole-source parsing is tried first because it preserves module-level context
    (imports, helper definitions) that block extraction discards.
    """
    error = "unknown parse failure"
    for candidate in (source, textwrap.dedent(source)):
        try:
            return ast.parse(candidate), ""
        except SyntaxError as exc:
            error = f"{exc.msg} (line {exc.lineno})"

    # Fallback: stitch together whichever individual test blocks do parse.
    recovered: list[ast.stmt] = []
    for block in _extract_test_blocks(source):
        try:
            recovered.extend(ast.parse(block).body)
        except SyntaxError:
            continue

    if recovered:
        return ast.Module(body=recovered, type_ignores=[]), ""
    return None, error


def analyze_test_assertions(test_patch: str | None) -> AssertionReport:
    """Analyse every `test_*` function added by `test_patch`."""
    source = added_source(test_patch)
    if not source.strip():
        return AssertionReport(parse_ok=False, parse_error="patch adds no lines")

    tree, error = _parse(source)
    if tree is None:
        return AssertionReport(parse_ok=False, parse_error=error)

    findings: list[AssertionFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        visitor = _TestBodyVisitor()
        for stmt in node.body:
            visitor.visit(stmt)
        findings.append(
            AssertionFinding(
                test_name=node.name,
                assertion_count=visitor.assertions,
                vacuous_count=visitor.vacuous,
                swallows_exceptions=visitor.swallows,
            )
        )

    if not findings:
        return AssertionReport(parse_ok=False, parse_error="no test functions found in added lines")

    return AssertionReport(parse_ok=True, findings=tuple(findings))
