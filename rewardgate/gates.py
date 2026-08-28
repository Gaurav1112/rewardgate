"""The reward gate: oracle and no-op trials.

Two bounds define whether a task measures anything, and they are independent:

* **Oracle** — apply the gold patch. The fail-to-pass suite must go green (reward 1.0). If it does
  not, the task is unsolvable even by its own author's answer.
* **No-op (NOP)** — apply nothing. The suite must stay red (reward 0.0). If it goes green, every
  agent "solves" the task without doing anything, and the task is a false-positive generator.

The second check is the one reviewers skip and the one that matters most. A task failing it is
invalid regardless of how good it otherwise looks.

Both trials are executions, so their evidence is an exit code rather than an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rewardgate.execution import MaterialisedBundle, TestOutcome, materialise


@dataclass(frozen=True)
class RewardGateResult:
    """Outcome of the oracle and no-op trials for one bundle."""

    oracle: TestOutcome
    nop: TestOutcome
    patch_error: str = ""

    @property
    def oracle_passes(self) -> bool:
        """The gold patch makes the suite green, as it must."""
        return self.oracle.reward == 1.0

    @property
    def nop_passes(self) -> bool:
        """The suite is green with no patch applied — the defect."""
        return self.nop.reward == 1.0

    @property
    def is_nop_pass_defect(self) -> bool:
        return self.nop_passes

    @property
    def is_unsolvable_defect(self) -> bool:
        """Gold patch applied and the suite still fails: nothing can score on this task."""
        return not self.oracle_passes

    @property
    def gate_holds(self) -> bool:
        """The task measures something: oracle 1.0 and no-op 0.0."""
        return self.oracle_passes and not self.nop_passes

    @property
    def reason(self) -> str:
        if self.patch_error:
            return f"gold patch failed to apply: {self.patch_error}"
        if self.is_nop_pass_defect:
            return (
                "fail-to-pass suite passes with an empty patch "
                f"(nop {self.nop.summary}) — task measures nothing"
            )
        if self.is_unsolvable_defect:
            return f"gold patch does not make the suite pass (oracle {self.oracle.summary})"
        return f"reward gate holds (oracle {self.oracle.summary}; nop {self.nop.summary})"


def read_patch(bundle_dir: Path) -> str:
    patch = bundle_dir / "solution.patch"
    return patch.read_text() if patch.exists() else ""


def run_reward_gate(bundle_dir: Path, tests_subdir: str = "tests") -> RewardGateResult:
    """Run the no-op then oracle trial for `bundle_dir`.

    Each trial gets its own materialised copy so the oracle's applied patch cannot leak into the
    no-op measurement.
    """
    patch_text = read_patch(bundle_dir)

    with materialise(bundle_dir) as tmp:
        bundle = MaterialisedBundle(Path(tmp))
        nop_outcome = bundle.run_tests(bundle.repo / tests_subdir)

    with materialise(bundle_dir) as tmp:
        bundle = MaterialisedBundle(Path(tmp))
        error = bundle.apply_patch(patch_text)
        oracle_outcome = (
            bundle.run_tests(bundle.repo / tests_subdir)
            if not error
            else TestOutcome(exit_code=-1, passed=0, failed=0, errors=0, stdout=error)
        )

    return RewardGateResult(oracle=oracle_outcome, nop=nop_outcome, patch_error=error)
