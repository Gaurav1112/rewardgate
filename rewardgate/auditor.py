"""The full RewardGate pipeline.

Each defect class is settled by the cheapest mechanism that can actually prove it:

    NOP_PASS           reward gate            deterministic, no model, ~2s
    CONTAMINATION_GIT  git history scan       deterministic, no model, <1s
    REWARD_HACKABLE    adversarial agent      one agentic loop, ~$0.28

Only the last needs a model, because it is the only class that cannot be settled by reading or by
running the suite as-is — a reward-hackable task passes the reward gate. Spending an LLM call on
the other two would add cost, latency and non-determinism while producing weaker evidence than an
exit code.

Every field in the emitted audit is backed by an artefact: a test summary, a commit list, or an
exploit patch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rewardgate.checkers.contamination import detect_git_contamination
from rewardgate.exploit import ExploitResult, run_exploit_trial
from rewardgate.gates import RewardGateResult, read_patch, run_reward_gate
from rewardgate.schema import (
    ACCEPT,
    CONTAMINATION_GIT,
    NOP_PASS,
    REJECT,
    REVISE,
    REWARD_HACKABLE,
    Audit,
)


@dataclass(frozen=True)
class AuditTrace:
    """The full evidence trail behind one audit, retained for the report and the trajectory log."""

    gate: RewardGateResult
    contamination: object
    exploit: ExploitResult | None


def decide_verdict(defects: dict[str, bool]) -> str:
    """Map defects to a reviewer verdict.

    NOP_PASS and CONTAMINATION_GIT are disqualifying: the task cannot measure what it claims, and
    no amount of rewriting the instruction fixes that. REWARD_HACKABLE is repairable — adding
    test inputs is a normal revision — so it returns REVISE rather than REJECT.
    """
    if defects.get(NOP_PASS) or defects.get(CONTAMINATION_GIT):
        return REJECT
    if defects.get(REWARD_HACKABLE):
        return REVISE
    return ACCEPT


def audit_bundle(
    bundle_dir: Path,
    run_exploit: bool = True,
    model: str | None = None,
) -> tuple[Audit, AuditTrace]:
    """Audit one bundle. Returns the verdict and the evidence behind it.

    `run_exploit=False` runs the deterministic tiers only — free, offline, and the mode a judge
    can use without an API key.
    """
    bundle_id = bundle_dir.name

    gate = run_reward_gate(bundle_dir)
    contamination = detect_git_contamination(bundle_dir, read_patch(bundle_dir))

    exploit: ExploitResult | None = None
    if run_exploit:
        exploit = (
            run_exploit_trial(bundle_dir, model=model)
            if model
            else run_exploit_trial(bundle_dir)
        )

    defects = {
        NOP_PASS: gate.is_nop_pass_defect,
        CONTAMINATION_GIT: contamination.contaminated,
        REWARD_HACKABLE: bool(exploit and exploit.is_reward_hackable),
    }
    evidence = {
        NOP_PASS: gate.reason,
        CONTAMINATION_GIT: contamination.reason,
        REWARD_HACKABLE: exploit.reason if exploit else "exploit trial not run",
    }

    audit = Audit(
        bundle_id=bundle_id,
        defects=defects,
        evidence=evidence,
        verdict=decide_verdict(defects),
        cost_usd=exploit.cost_usd if exploit else 0.0,
        duration_ms=exploit.duration_ms if exploit else 0,
    )
    return audit, AuditTrace(gate=gate, contamination=contamination, exploit=exploit)
