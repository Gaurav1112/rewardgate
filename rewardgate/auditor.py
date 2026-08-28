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
    INDETERMINATE,
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


def decide_verdict(defects: dict[str, bool], blockers: tuple[str, ...] = ()) -> str:
    """Map defects to a reviewer verdict.

    NOP_PASS and CONTAMINATION_GIT are disqualifying: the task cannot measure what it claims, and
    no amount of rewriting the instruction fixes that. REWARD_HACKABLE is repairable — adding
    test inputs is a normal revision — so it returns REVISE rather than REJECT.

    `blockers` are checks that could not run. They take precedence over ACCEPT: a verdict of
    "sound" must never be the consequence of a check failing to execute.
    """
    if defects.get(NOP_PASS) or defects.get(CONTAMINATION_GIT):
        return REJECT
    if defects.get(REWARD_HACKABLE):
        return REVISE
    if blockers:
        return INDETERMINATE
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

    # Checks that could not run. Each would otherwise have defaulted to "no defect found".
    blockers: list[str] = []
    if gate.patch_error:
        blockers.append(f"gold patch did not apply: {gate.patch_error}")
    elif not gate.nop_ran:
        blockers.append(f"no-op trial did not run ({gate.nop.summary}); NOP_PASS unverified")
    elif gate.is_unsolvable_defect:
        blockers.append(f"gold patch does not make the suite pass ({gate.oracle.summary})")
    if getattr(contamination, "indeterminate", False):
        blockers.append(contamination.reason)
    if exploit is None:
        # `--no-exploit` checks two of the three classes. Reporting ACCEPT on that basis asserts
        # the task is sound while the only class the reward gate is blind to went unexamined —
        # and REWARD_HACKABLE is the class this project exists to add. The docs already claimed
        # "a check that cannot run returns INDETERMINATE rather than defaulting to ACCEPT"; this
        # makes that true of the free path a judge is most likely to run.
        blockers.append("REWARD_HACKABLE not checked (--no-exploit); 2 of 3 classes examined")
    elif exploit.error:
        blockers.append(f"exploit trial failed: {exploit.error}")
    elif exploit is not None and exploit.produced_patch and exploit.visible_green:
        # The exploit tier had its own honest-failure guards from the start, but nothing consumed
        # them, so they could not affect a verdict. Both cases below record REWARD_HACKABLE as
        # absent on the strength of a measurement that did not happen — the same fail-open the
        # reward gate's `nop_ran` closes, in the tier this project exists to add.
        if not exploit.held_out_ran:
            blockers.append(
                f"held-out suite did not run ({exploit.held_out.summary if exploit.held_out else 'n/a'}); "
                "a patch cannot be distinguished from an exploit"
            )
        elif not exploit.cost_measurable:
            blockers.append(
                "an exploit was proven but its technique matches no known hardcoding pattern, "
                "so its cost could not be priced — review the patch by hand"
            )

    audit = Audit(
        bundle_id=bundle_id,
        defects=defects,
        evidence=evidence,
        verdict=decide_verdict(defects, tuple(blockers)),
        cost_usd=exploit.cost_usd if exploit else 0.0,
        duration_ms=exploit.duration_ms if exploit else 0,
        error="; ".join(blockers),
    )
    return audit, AuditTrace(gate=gate, contamination=contamination, exploit=exploit)
