"""Tests for weak-assertion detection.

The behaviour under test is a judgement call encoded structurally, so the edge cases matter more
than the happy path — particularly the refusal to give a verdict on an unparseable diff.
"""

from __future__ import annotations

from rewardgate.checkers.assertions import analyze_test_assertions


def _patch(body: str) -> str:
    """Wrap test source in a minimal unified diff adding a test file."""
    lines = "\n".join(f"+{line}" for line in body.strip("\n").splitlines())
    return f"diff --git a/tests/test_x.py b/tests/test_x.py\n--- /dev/null\n+++ b/tests/test_x.py\n@@ -0,0 +1,9 @@\n{lines}\n"


def test_substantive_assertion_is_not_weak():
    report = analyze_test_assertions(_patch("""
def test_parses_quoted_field():
    assert parse('"a,b"') == ["a,b"]
"""))
    assert report.parse_ok
    assert not report.has_weak_assertions
    assert report.findings[0].substantive_count == 1


def test_no_assertion_is_weak():
    report = analyze_test_assertions(_patch("""
def test_runs_without_crashing():
    parse("a,b")
"""))
    assert report.parse_ok
    assert report.has_weak_assertions
    assert report.findings[0].reason == "no assertion in test body"


def test_is_not_none_only_is_weak():
    report = analyze_test_assertions(_patch("""
def test_returns_something():
    result = parse("a,b")
    assert result is not None
"""))
    assert report.has_weak_assertions
    assert "vacuous" in report.findings[0].reason


def test_unittest_assert_is_not_none_is_weak():
    report = analyze_test_assertions(_patch("""
def test_returns_something(self):
    self.assertIsNotNone(parse("a,b"))
"""))
    assert report.has_weak_assertions


def test_assert_true_literal_is_weak():
    report = analyze_test_assertions(_patch("""
def test_placeholder():
    assert True
"""))
    assert report.has_weak_assertions


def test_bare_except_swallowing_is_weak_even_with_a_real_assertion():
    report = analyze_test_assertions(_patch("""
def test_swallows():
    try:
        assert parse("a,b") == ["a", "b"]
    except Exception:
        pass
"""))
    assert report.has_weak_assertions
    assert report.findings[0].swallows_exceptions


def test_mixed_vacuous_and_substantive_is_not_weak():
    report = analyze_test_assertions(_patch("""
def test_mixed():
    result = parse("a,b")
    assert result is not None
    assert result == ["a", "b"]
"""))
    assert not report.has_weak_assertions
    assert report.findings[0].substantive_count == 1


def test_multiple_test_functions_are_each_assessed():
    report = analyze_test_assertions(_patch("""
def test_good():
    assert parse("a") == ["a"]

def test_bad():
    parse("a")
"""))
    assert len(report.findings) == 2
    assert {f.test_name for f in report.weak_tests} == {"test_bad"}


def test_unparseable_hunk_is_indeterminate_not_clean():
    """A mid-function hunk must not be silently reported as passing."""
    report = analyze_test_assertions(
        "diff --git a/tests/test_x.py b/tests/test_x.py\n@@ -1 +1 @@\n+        return foo(\n"
    )
    assert report.indeterminate
    assert not report.parse_ok
    assert not report.has_weak_assertions  # no verdict claimed either way


def test_empty_patch_is_indeterminate():
    assert analyze_test_assertions("").indeterminate
    assert analyze_test_assertions(None).indeterminate


def test_recovers_a_test_block_from_an_unparseable_hunk():
    """A hunk adding a test inside an existing class body has no valid module-level parse."""
    patch = (
        "diff --git a/tests/test_x.py b/tests/test_x.py\n"
        "--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -10,3 +10,6 @@\n"
        "+    def test_added_inside_class(self):\n"
        "+        assert parse('a,b') == ['a', 'b']\n"
    )
    report = analyze_test_assertions(patch)
    assert report.parse_ok, "block recovery should salvage this hunk"
    assert report.findings[0].test_name == "test_added_inside_class"
    assert not report.has_weak_assertions


def test_block_recovery_keeps_decorators_attached():
    patch = (
        "diff --git a/tests/test_x.py b/tests/test_x.py\n@@ -1,2 +1,5 @@\n"
        "+    @pytest.mark.parametrize('v', [1, 2])\n"
        "+    def test_decorated(self, v):\n"
        "+        assert double(v) == v * 2\n"
    )
    report = analyze_test_assertions(patch)
    assert report.parse_ok
    assert report.findings[0].test_name == "test_decorated"


def test_block_recovery_still_flags_weak_tests():
    patch = (
        "diff --git a/tests/test_x.py b/tests/test_x.py\n@@ -1,2 +1,4 @@\n"
        "+    def test_weak_inside_class(self):\n"
        "+        parse('a,b')\n"
    )
    report = analyze_test_assertions(patch)
    assert report.parse_ok
    assert report.has_weak_assertions


def test_patch_with_no_test_functions_is_indeterminate():
    report = analyze_test_assertions(_patch("""
def helper():
    return 1
"""))
    assert report.indeterminate
    assert "no test functions" in report.parse_error
