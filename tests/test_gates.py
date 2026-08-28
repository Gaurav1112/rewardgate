"""Tests for the reward gate over the synthetic corpus.

The most important assertion here is a *negative* one: the reward gate does not detect
REWARD_HACKABLE. That blind spot is the project's central claim, so it is pinned as a test. If a
future change makes the gate appear to catch it, that is a bug in the gate, not a win.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rewardgate.gates import run_reward_gate

BUNDLES = Path(__file__).resolve().parent.parent / "corpus" / "synthetic" / "bundles"
LABELS = BUNDLES / "labels.yaml"

pytestmark = pytest.mark.skipif(
    not LABELS.exists(), reason="run: uv run python corpus/synthetic/build.py"
)


def _bundle(name: str) -> Path:
    return BUNDLES / name


@pytest.fixture(scope="module")
def manifest() -> list[dict]:
    return yaml.safe_load(LABELS.read_text())["bundles"]


def test_every_bundle_has_a_solvable_gold_patch(manifest):
    """Oracle must be 1.0 everywhere, including defective bundles.

    A defect must not also make the task unsolvable, or the corpus would conflate two failures.
    """
    for entry in manifest:
        result = run_reward_gate(_bundle(entry["id"]))
        assert result.oracle_passes, f"{entry['id']}: oracle {result.oracle.summary}"


def test_clean_bundle_gate_holds():
    result = run_reward_gate(_bundle("csvlite-clean"))
    assert result.gate_holds
    assert not result.is_nop_pass_defect
    assert "reward gate holds" in result.reason


def test_nop_pass_bundle_is_caught_by_the_gate():
    result = run_reward_gate(_bundle("csvlite-nop-pass"))
    assert result.is_nop_pass_defect
    assert not result.gate_holds
    assert result.nop.reward == 1.0
    assert "measures nothing" in result.reason


def test_reward_hackable_bundle_is_invisible_to_the_gate():
    """The project's central claim, pinned.

    A reward-hackable task satisfies both bounds the field checks — oracle 1.0, no-op 0.0 — while
    still being gameable. Static gates cannot settle it; only executing an exploit can.
    """
    result = run_reward_gate(_bundle("csvlite-reward-hackable"))
    assert result.gate_holds, "gate unexpectedly detects reward hacking"
    assert result.oracle.reward == 1.0
    assert result.nop.reward == 0.0


def test_git_contaminated_bundle_is_invisible_to_the_gate():
    """Contamination lives in history, not in test outcomes, so the gate cannot see it either."""
    result = run_reward_gate(_bundle("csvlite-contaminated-git"))
    assert result.gate_holds


def test_held_out_tests_pass_on_a_correctly_fixed_clean_bundle():
    """Held-out tests must not be broken; otherwise they would flag honest fixes as exploits."""
    from rewardgate.execution import MaterialisedBundle, materialise

    bundle_dir = _bundle("csvlite-clean")
    with materialise(bundle_dir) as tmp:
        bundle = MaterialisedBundle(Path(tmp))
        assert bundle.apply_patch((bundle_dir / "solution.patch").read_text()) == ""
        assert bundle.run_tests(bundle.repo / "held_out").reward == 1.0


def test_held_out_tests_fail_on_the_unfixed_bundle():
    from rewardgate.execution import MaterialisedBundle, materialise

    with materialise(_bundle("csvlite-clean")) as tmp:
        bundle = MaterialisedBundle(Path(tmp))
        assert bundle.run_tests(bundle.repo / "held_out").reward == 0.0
