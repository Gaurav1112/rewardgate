"""The held-out corpus, and the claim that makes it worth having.

The 42% figure is measured on SWE-bench Verified, a corpus this project did not build — that is
what makes it non-circular. But one corpus cannot distinguish "42% of SWE-bench Verified" from
"42% of agentic coding benchmarks", and the four checkers were written while looking at Verified.

SWE-Gym is the held-out set. These tests pin the one property the comparison depends on — that the
two corpora share no instances — because "independent corpus" is exactly the kind of claim that is
assumed rather than checked. SWE-bench Lite was rejected for this role: 93 of its 300 instances are
also in Verified, so calling it independent would have been false.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VERIFIED = ROOT / "corpus" / "real" / "raw" / "swebench_verified.parquet"
HOLDOUT = ROOT / "corpus" / "real" / "raw" / "swegym_train.parquet"
FINDINGS = ROOT / "results" / "holdout_corpus_findings.json"

pytestmark = pytest.mark.skipif(
    not (VERIFIED.exists() and HOLDOUT.exists()),
    reason="run: ./scripts/fetch_real_corpus.sh && ./scripts/fetch_holdout_corpus.sh",
)


def _ids(path: Path) -> set[str]:
    from rewardgate.corpus import load_real_corpus

    return {b.instance_id for b in load_real_corpus(path)}


def test_the_two_corpora_share_no_instances():
    """The load-bearing claim. If they overlapped, the replication would be partly self-comparison
    and the out-of-sample argument would collapse."""
    overlap = _ids(VERIFIED) & _ids(HOLDOUT)
    assert not overlap, f"{len(overlap)} shared instances: {sorted(overlap)[:5]}"


def test_the_holdout_is_substantially_larger_than_the_original():
    """The replication is on more data, not less — 2438 against 500."""
    assert len(_ids(HOLDOUT)) > 4 * len(_ids(VERIFIED))


@pytest.mark.skipif(not FINDINGS.exists(), reason="run: report_real --holdout")
def test_the_holdout_defect_rate_is_pinned():
    """Documented as replicating Verified's 42.0% at 43.5%. Pinned so the claim cannot drift."""
    d = json.loads(FINDINGS.read_text())
    assert d["instances"] == 2438
    assert d["solution_leakage"] == 663
    assert d["at_least_one_defect"] == 1061
    assert abs(d["at_least_one_defect"] / d["instances"] - 0.435) < 0.002
