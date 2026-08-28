"""Tests for solution-leakage detection.

The corpus-level test is the important one. It asserts that this detector reproduces a published
third-party measurement, which is the evidence that the detector was not tuned to defects the
author planted.
"""

from __future__ import annotations

import pytest

from rewardgate.checkers.leakage import detect_solution_leakage, files_in_patch
from rewardgate.corpus import REAL_CORPUS_PATH, load_real_corpus

PATCH_TWO_FILES = """diff --git a/astropy/wcs/wcsapi/wrappers.py b/astropy/wcs/wcsapi/wrappers.py
--- a/astropy/wcs/wcsapi/wrappers.py
+++ b/astropy/wcs/wcsapi/wrappers.py
@@ -1 +1 @@
-old
+new
diff --git a/docs/changes/1234.bugfix b/docs/changes/1234.bugfix
--- /dev/null
+++ b/docs/changes/1234.bugfix
@@ -0,0 +1 @@
+fixed
"""


def test_files_in_patch_extracts_every_modified_path():
    assert files_in_patch(PATCH_TWO_FILES) == {
        "astropy/wcs/wcsapi/wrappers.py",
        "docs/changes/1234.bugfix",
    }


def test_files_in_patch_tolerates_empty_input():
    assert files_in_patch("") == set()
    assert files_in_patch(None) == set()


def test_full_path_in_issue_is_high_confidence_leakage():
    finding = detect_solution_leakage(
        "Slicing breaks in astropy/wcs/wcsapi/wrappers.py when the axis is dropped.",
        PATCH_TWO_FILES,
    )
    assert finding.leaked
    assert finding.confidence == "high"
    assert "astropy/wcs/wcsapi/wrappers.py" in finding.leaked_paths


def test_basename_only_is_medium_confidence():
    finding = detect_solution_leakage("The bug is in wrappers.py somewhere.", PATCH_TWO_FILES)
    assert finding.leaked
    assert finding.confidence == "medium"
    assert finding.leaked_basenames == frozenset({"wrappers.py"})


def test_a_file_matched_by_full_path_is_not_also_counted_as_a_basename():
    """Guards against double-counting one file as two pieces of evidence."""
    finding = detect_solution_leakage(
        "See astropy/wcs/wcsapi/wrappers.py", PATCH_TWO_FILES
    )
    assert "wrappers.py" not in finding.leaked_basenames


def test_issue_that_names_no_modified_file_is_clean():
    finding = detect_solution_leakage(
        "Coordinate transforms return the wrong shape for 1D inputs.", PATCH_TWO_FILES
    )
    assert not finding.leaked
    assert finding.confidence == "none"


def test_empty_problem_statement_is_clean():
    assert not detect_solution_leakage("", PATCH_TWO_FILES).leaked
    assert not detect_solution_leakage(None, PATCH_TWO_FILES).leaked


@pytest.mark.skipif(
    not REAL_CORPUS_PATH.exists(), reason="run scripts/fetch_real_corpus.sh first"
)
def test_reproduces_published_leakage_rate_on_swebench_verified():
    """Cross-validation against an independent research group.

    "The SWE-bench Illusion" (arXiv:2506.12286) reports 135/500 Verified instances embed the gold
    file path in the issue text. We measure 133. The tolerance is deliberately tight: a wide band
    would let the detector drift while still "agreeing" with the paper.
    """
    bundles = load_real_corpus()
    assert len(bundles) == 500

    leaked = sum(
        1
        for b in bundles
        if detect_solution_leakage(b.problem_statement, b.patch).leaked
    )
    assert leaked == 133, f"expected 133 leaking instances, measured {leaked}"
    assert abs(leaked - 135) <= 5, "drifted materially from the published figure of 135/500"
