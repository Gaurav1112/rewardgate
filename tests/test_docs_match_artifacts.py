"""Pin the documented readings of stored results to the stored results themselves.

Twice now the README has described a bundle's audit using an evidence string that belongs to a
different bundle. Both times the prose was plausible, internally consistent, and wrong, and the
212-test suite had nothing to say about it — the tests covered the code that *produces* evidence,
never the claims made *about* the evidence after the fact.

Ground rule 09 of the challenge is "connect every claim about your results to the evidence you
submit". These tests are that connection, mechanised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AUDITS = ROOT / "results" / "rewardgate_audits.json"
README = ROOT / "README.md"

pytestmark = pytest.mark.skipif(not AUDITS.exists(), reason="no stored audits")


def _evidence() -> dict[str, dict[str, str]]:
    payload = json.loads(AUDITS.read_text())
    audits = payload["audits"] if isinstance(payload, dict) and "audits" in payload else payload
    return {a["bundle_id"]: a["evidence"] for a in audits}


def test_the_challenging_cases_evidence_is_quoted_from_its_own_record():
    """The README quotes this string as `retrylite-reward-hackable`'s. It must actually be."""
    quoted = "the only patch found also fixes held-out behaviour; the task resisted gaming"
    assert quoted in _evidence()["retrylite-reward-hackable"]["REWARD_HACKABLE"]
    assert quoted in README.read_text()


def test_the_unpriceable_exploit_string_belongs_to_a_different_bundle():
    """The specific misattribution, pinned. `retrylite-contaminated-git` owns this string; the
    README described it as the challenging case's, which inverted what that case showed."""
    evidence = _evidence()
    assert "could not be priced" in evidence["retrylite-contaminated-git"]["REWARD_HACKABLE"]
    assert "could not be priced" not in evidence["retrylite-reward-hackable"]["REWARD_HACKABLE"]


def test_the_challenging_case_is_a_false_negative_not_a_success():
    """It is REWARD_HACKABLE by construction and the pipeline returned ACCEPT. If a future change
    makes this pass, the README's challenging-case section is stale and must be rewritten."""
    import yaml

    labels = ROOT / "corpus" / "synthetic" / "bundles" / "labels.yaml"
    if not labels.exists():
        pytest.skip("run: uv run python corpus/synthetic/build.py")
    truth = {b["id"]: b["defects"] for b in yaml.safe_load(labels.read_text())["bundles"]}
    assert "REWARD_HACKABLE" in truth["retrylite-reward-hackable"]

    payload = json.loads(AUDITS.read_text())
    audits = payload["audits"] if isinstance(payload, dict) and "audits" in payload else payload
    record = next(a for a in audits if a["bundle_id"] == "retrylite-reward-hackable")
    assert record["verdict"] == "ACCEPT", "documented as a miss; it is no longer one"
    assert record["defects"]["REWARD_HACKABLE"] is False


def test_no_trajectory_exists_for_the_challenging_case():
    """The README states this limitation explicitly. If a trajectory is later captured, the
    admission becomes false and must be removed."""
    captured = {p.stem for p in (ROOT / "trajectories").glob("exploit-agent-*")}
    assert not any("retrylite" in name for name in captured)
