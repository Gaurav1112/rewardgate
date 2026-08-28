"""Significance and uncertainty for the headline comparison.

A percentage improvement computed from 45 paired judgements over 3 base repositories is not, on
its own, evidence. This module computes the things that decide whether the difference is real:

* **McNemar's exact test** on the paired correctness vectors — the right test for two systems
  scored on the same cases.
* **Clopper-Pearson intervals** for the rates, which are exact rather than normal-approximate and
  so stay honest at n=3.
* **Degenerate baselines** — always-yes, always-no — because macro-F1's floor is not zero, and a
  reader who does not know that will over-read 0.600.
* **Drop-one-class analysis** — which class actually carries the headline.

Everything is stdlib. Nothing here depends on the result coming out favourably.

Run: uv run python -m rewardgate.significance
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import comb
from pathlib import Path

from rewardgate.evaluate import _audit_from_dict, load_truth
from rewardgate.schema import DEFECT_CLASSES, Audit
from rewardgate.scoring import score_audits

RESULTS = Path(__file__).resolve().parent.parent / "results"


def clopper_pearson(successes: int, trials: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial confidence interval, computed by bisection on the binomial tail.

    Exact rather than Wald because at n=3 a normal approximation produces intervals that extend
    past 0 and 1 and understate the true uncertainty.
    """
    if trials == 0:
        return (0.0, 1.0)

    def tail_at_least(p: float, k: int) -> float:
        return sum(comb(trials, i) * p**i * (1 - p) ** (trials - i) for i in range(k, trials + 1))

    def tail_at_most(p: float, k: int) -> float:
        return sum(comb(trials, i) * p**i * (1 - p) ** (trials - i) for i in range(0, k + 1))

    # Lower bound: P(X >= k | p) is increasing in p; find where it equals alpha/2.
    lower = 0.0
    if successes > 0:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if tail_at_least(mid, successes) < alpha / 2:
                lo = mid
            else:
                hi = mid
        lower = (lo + hi) / 2

    # Upper bound: P(X <= k | p) is decreasing in p; find where it equals alpha/2.
    upper = 1.0
    if successes < trials:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if tail_at_most(mid, successes) > alpha / 2:
                lo = mid
            else:
                hi = mid
        upper = (lo + hi) / 2

    return (round(lower, 4), round(upper, 4))


def mcnemar_exact(only_a_correct: int, only_b_correct: int) -> float:
    """Two-sided exact McNemar p-value over the discordant pairs.

    Concordant pairs carry no information about which system is better, so only the discordant
    counts enter. With all discordance in one direction the p-value is 2 * 0.5**n, which needs
    n >= 6 to clear 0.05 — worth knowing before designing a 45-judgement experiment.
    """
    n = only_a_correct + only_b_correct
    if n == 0:
        return 1.0
    k = min(only_a_correct, only_b_correct)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2**n)
    return min(1.0, 2 * tail)


@dataclass(frozen=True)
class PairedResult:
    """Paired outcome over every (bundle, defect class) judgement."""

    both_correct: int
    only_baseline: int
    only_rewardgate: int
    both_wrong: int

    @property
    def total(self) -> int:
        return self.both_correct + self.only_baseline + self.only_rewardgate + self.both_wrong

    @property
    def p_value(self) -> float:
        return mcnemar_exact(self.only_baseline, self.only_rewardgate)

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05


def pair_up(baseline: list[Audit], rewardgate: list[Audit], truth: dict[str, list[str]]) -> PairedResult:
    by_id = {a.bundle_id: a for a in rewardgate}
    counts = {"bb": 0, "b": 0, "r": 0, "nn": 0}
    for base in baseline:
        other = by_id.get(base.bundle_id)
        if other is None:
            continue
        actual = set(truth.get(base.bundle_id, []))
        for defect in DEFECT_CLASSES:
            present = defect in actual
            b_ok = base.flags(defect) == present
            r_ok = other.flags(defect) == present
            counts["bb" if b_ok and r_ok else "b" if b_ok else "r" if r_ok else "nn"] += 1
    return PairedResult(counts["bb"], counts["b"], counts["r"], counts["nn"])


def degenerate_baselines(truth: dict[str, list[str]]) -> dict[str, float]:
    """macro-F1 for always-yes and always-no, so 0.600 is read against the right floor."""
    always_yes = [
        Audit(bundle_id=b, defects={d: True for d in DEFECT_CLASSES}) for b in truth
    ]
    always_no = [
        Audit(bundle_id=b, defects={d: False for d in DEFECT_CLASSES}) for b in truth
    ]
    return {
        "always_yes": round(score_audits("yes", always_yes, truth).macro_f1, 4),
        "always_no": round(score_audits("no", always_no, truth).macro_f1, 4),
    }


def drop_one_class(audits: list[Audit], truth: dict[str, list[str]]) -> dict[str, float]:
    """macro-F1 with each class removed, exposing which class carries the headline."""
    out = {}
    for dropped in DEFECT_CLASSES:
        kept = [d for d in DEFECT_CLASSES if d != dropped]
        scored = score_audits("x", audits, truth)
        per = {c.defect: c.f1 for c in scored.per_class}
        out[f"without_{dropped}"] = round(sum(per[c] for c in kept) / len(kept), 4)
    return out


def main() -> None:
    truth = load_truth()
    baseline = [_audit_from_dict(x) for x in json.loads((RESULTS / "baseline_audits.json").read_text())]
    rewardgate = [_audit_from_dict(x) for x in json.loads((RESULTS / "rewardgate_audits.json").read_text())]

    paired = pair_up(baseline, rewardgate, truth)
    b_score = score_audits("baseline", baseline, truth)
    r_score = score_audits("rewardgate", rewardgate, truth)

    clean = [b for b, defects in truth.items() if not defects]
    def false_alarms(audits):
        by_id = {a.bundle_id: a for a in audits}
        return sum(1 for b in clean if by_id[b].any_defect)

    report = {
        "judgements_per_system": paired.total,
        "independent_base_repos": len({b.rsplit("-", 1)[0].split("-")[0] for b in truth}),
        "mcnemar": {
            "both_correct": paired.both_correct,
            "only_baseline_correct": paired.only_baseline,
            "only_rewardgate_correct": paired.only_rewardgate,
            "both_wrong": paired.both_wrong,
            "p_value": round(paired.p_value, 4),
            "significant_at_0.05": paired.significant,
        },
        "paired_accuracy_ci": {
            "baseline": clopper_pearson(paired.both_correct + paired.only_baseline, paired.total),
            "rewardgate": clopper_pearson(paired.both_correct + paired.only_rewardgate, paired.total),
        },
        "false_alarms_on_clean_bundles": {
            "clean_bundles": len(clean),
            "baseline": false_alarms(baseline),
            "rewardgate": false_alarms(rewardgate),
            "rewardgate_rate_ci": clopper_pearson(false_alarms(rewardgate), len(clean)),
        },
        "macro_f1": {"baseline": round(b_score.macro_f1, 4), "rewardgate": round(r_score.macro_f1, 4)},
        "degenerate_baselines": degenerate_baselines(truth),
        "drop_one_class_rewardgate": drop_one_class(rewardgate, truth),
        "drop_one_class_baseline": drop_one_class(baseline, truth),
    }

    print(json.dumps(report, indent=2))
    (RESULTS / "significance.json").write_text(json.dumps(report, indent=2))
    print(f"\nsaved -> {RESULTS / 'significance.json'}")

    verdict = "SIGNIFICANT" if paired.significant else "NOT significant at alpha=0.05"
    print(f"\nMcNemar exact p = {paired.p_value:.4f} — {verdict}")
    print(f"discordant pairs: {paired.only_rewardgate} favour RewardGate, "
          f"{paired.only_baseline} favour baseline")


if __name__ == "__main__":
    main()
