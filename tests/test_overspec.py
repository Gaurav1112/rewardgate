"""Tests for over-specification and hint-contamination detection."""

from __future__ import annotations

from rewardgate.checkers.hints import detect_hint_contamination
from rewardgate.checkers.overspec import detect_over_specification, symbols_in_patch

PATCH = """diff --git a/csvlite/reader.py b/csvlite/reader.py
--- a/csvlite/reader.py
+++ b/csvlite/reader.py
@@ -10,7 +10,7 @@ def _parse_quoted(row):
-    return row.split(",")
+    return _split_respecting_quotes(row)
"""

PATCH_WITH_NEW_DEF = """diff --git a/csvlite/reader.py b/csvlite/reader.py
--- a/csvlite/reader.py
+++ b/csvlite/reader.py
@@ -1,3 +1,6 @@
+def _split_respecting_quotes(row):
+    return next(csv.reader([row]))
"""


def test_symbols_come_from_the_hunk_context_header():
    """git records the enclosing definition even when the def line is unchanged."""
    assert "_parse_quoted" in symbols_in_patch(PATCH)


def test_symbols_come_from_added_definitions():
    assert "_split_respecting_quotes" in symbols_in_patch(PATCH_WITH_NEW_DEF)


def test_generic_names_are_not_treated_as_disclosure():
    patch = "@@ -1,2 +1,3 @@ def setUp(self):\n+    pass\n"
    assert symbols_in_patch(patch) == set()


def test_issue_naming_the_modified_symbol_is_over_specified():
    finding = detect_over_specification(
        "The _parse_quoted helper mishandles embedded commas.", PATCH
    )
    assert finding.over_specified
    assert "_parse_quoted" in finding.named_symbols


def test_naming_symbol_and_file_is_high_severity():
    finding = detect_over_specification(
        "Bug in csvlite/reader.py: _parse_quoted mishandles commas.", PATCH
    )
    assert finding.severity == "high"


def test_naming_only_the_symbol_is_medium_severity():
    finding = detect_over_specification("_parse_quoted mishandles commas.", PATCH)
    assert finding.severity == "medium"


def test_behavioural_issue_is_not_over_specified():
    finding = detect_over_specification(
        'Reading the row \'a,"b,c"\' returns three fields instead of two.', PATCH
    )
    assert not finding.over_specified
    assert finding.severity == "none"


def test_substring_match_does_not_count_as_naming_a_symbol():
    """`_parse_quoted` must not be matched by the unrelated word `unparse_quotedstring`."""
    finding = detect_over_specification("See unparse_quotedstring elsewhere.", PATCH)
    assert not finding.over_specified


PUBLIC_PATCH = """diff --git a/tbl/io.py b/tbl/io.py
--- a/tbl/io.py
+++ b/tbl/io.py
@@ -10,7 +10,7 @@ def write(table, fmt):
-    return render(table)
+    return render(table, fmt)
"""


def test_naming_a_public_api_symbol_is_not_a_defect():
    """A reporter naming the function they called is describing the bug, not leaking the fix."""
    finding = detect_over_specification(
        "Table.write drops the supplied formats argument.", PUBLIC_PATCH
    )
    assert "write" in finding.named_symbols
    assert finding.public_symbols == frozenset({"write"})
    assert not finding.over_specified
    assert finding.severity == "none"
    assert "normal for a bug report" in finding.reason


def test_private_and_public_symbols_are_separated():
    patch = PATCH + PUBLIC_PATCH
    finding = detect_over_specification("_parse_quoted is called by write()", patch)
    assert finding.private_symbols == frozenset({"_parse_quoted"})
    assert "write" in finding.public_symbols
    assert finding.over_specified


def test_dunder_only_is_low_severity():
    """Protocol methods are legitimately named by sophisticated reporters."""
    patch = "@@ -1,2 +1,3 @@ def __array_ufunc__(self):\n+    return NotImplemented\n"
    finding = detect_over_specification(
        "Quantity.__array_ufunc__ should return NotImplemented.", patch
    )
    assert finding.over_specified
    assert finding.severity == "low"


def test_empty_statement_is_not_over_specified():
    assert not detect_over_specification("", PATCH).over_specified
    assert not detect_over_specification(None, PATCH).over_specified


# --- hint contamination ---------------------------------------------------------------


def test_hints_reproducing_a_patch_line_is_contamination():
    finding = detect_hint_contamination(
        "A maintainer suggested: return _split_respecting_quotes(row)", PATCH
    )
    assert finding.contaminated
    assert finding.disclosure_ratio == 1.0


def test_hints_are_matched_despite_whitespace_differences():
    finding = detect_hint_contamination(
        "try    return   _split_respecting_quotes(row)   here", PATCH
    )
    assert finding.contaminated


def test_discussion_without_the_fix_is_not_contamination():
    finding = detect_hint_contamination(
        "I can reproduce this on Windows too. Seems locale related.", PATCH
    )
    assert not finding.contaminated
    assert finding.hints_present
    assert "discloses no patch lines" in finding.reason


def test_absent_hints_are_reported_as_absent_not_clean():
    finding = detect_hint_contamination("", PATCH)
    assert not finding.hints_present
    assert not finding.contaminated
    assert finding.reason == "no hint text on this instance"


def test_trivial_short_lines_cannot_manufacture_a_match():
    """A patch adding only `return x` must not match any hint containing those words."""
    trivial = "diff --git a/a.py b/a.py\n@@ -1 +1,2 @@\n+    return x\n"
    finding = detect_hint_contamination("you should just return x", trivial)
    assert not finding.contaminated
