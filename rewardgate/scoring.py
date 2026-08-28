"""Scoring audits against ground truth.

The primary metric is **macro-F1 over (bundle x defect class)** binary judgements.

Macro rather than micro, because the defect classes are unbalanced and micro-averaging would let
strong performance on the common class hide total failure on a rare one. F1 rather than accuracy,
because most (bundle, class) pairs are negatives — a system that flags nothing would score well on
accuracy while being useless.

Precision is reported alongside recall and never collapsed into the headline alone. The cost of a
false positive here is an author being told to rewrite a task that was fine.
"""

from __future__ import annotations

from dataclasses import dataclass

from rewardgate.schema import DEFECT_CLASSES, Audit


@dataclass(frozen=True)
class ClassScore:
    """Confusion counts and derived rates for one defect class."""

    defect: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        if not (self.precision and self.recall):
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    @property
    def support(self) -> int:
        """Number of bundles that genuinely carry this defect."""
        return self.true_positives + self.false_negatives


@dataclass(frozen=True)
class Score:
    """Aggregate result for one system over one corpus."""

    system: str
    per_class: tuple[ClassScore, ...]
    bundles: int
    exact_match: int
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    errors: int = 0

    @property
    def macro_f1(self) -> float:
        """Unweighted mean F1 across defect classes — the primary metric."""
        return sum(c.f1 for c in self.per_class) / len(self.per_class) if self.per_class else 0.0

    @property
    def macro_precision(self) -> float:
        return sum(c.precision for c in self.per_class) / len(self.per_class) if self.per_class else 0.0

    @property
    def macro_recall(self) -> float:
        return sum(c.recall for c in self.per_class) / len(self.per_class) if self.per_class else 0.0

    @property
    def exact_match_rate(self) -> float:
        """Fraction of bundles where every class was judged correctly."""
        return self.exact_match / self.bundles if self.bundles else 0.0

    @property
    def cost_per_bundle(self) -> float:
        return self.total_cost_usd / self.bundles if self.bundles else 0.0


def score_audits(system: str, audits: list[Audit], truth: dict[str, list[str]]) -> Score:
    """Score `audits` against `truth`, a mapping of bundle id to its actual defect classes."""
    counts = {d: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for d in DEFECT_CLASSES}
    exact = 0

    for audit in audits:
        actual = set(truth.get(audit.bundle_id, []))
        correct_everywhere = True
        for defect in DEFECT_CLASSES:
            predicted = audit.flags(defect)
            present = defect in actual
            if predicted and present:
                counts[defect]["tp"] += 1
            elif predicted and not present:
                counts[defect]["fp"] += 1
                correct_everywhere = False
            elif not predicted and present:
                counts[defect]["fn"] += 1
                correct_everywhere = False
            else:
                counts[defect]["tn"] += 1
        exact += int(correct_everywhere)

    return Score(
        system=system,
        per_class=tuple(
            ClassScore(
                defect=d,
                true_positives=counts[d]["tp"],
                false_positives=counts[d]["fp"],
                false_negatives=counts[d]["fn"],
                true_negatives=counts[d]["tn"],
            )
            for d in DEFECT_CLASSES
        ),
        bundles=len(audits),
        exact_match=exact,
        total_cost_usd=sum(a.cost_usd for a in audits),
        total_duration_ms=sum(a.duration_ms for a in audits),
        errors=sum(1 for a in audits if a.error),
    )


def format_comparison(baseline: Score, advanced: Score) -> str:
    """Render the baseline-vs-final table the brief asks for."""

    def change(before: float, after: float) -> str:
        # Absolute, not percentage. Percentage change off a near-zero denominator manufactures
        # magnitude -- this printed "+55.6%" for a 0.333 macro-F1 difference, and kept printing it
        # after the README had retracted that comparison as measured against an unfair baseline.
        # The tool must not advertise a number its own documentation withdraws.
        return f"{after - before:+.4f}"

    lines = [
        f"{'METRIC':<28}{'BASELINE':>12}{'REWARDGATE':>14}{'CHANGE':>12}",
        "=" * 66,
        f"{'macro-F1 (primary)':<28}{baseline.macro_f1:>12.3f}{advanced.macro_f1:>14.3f}"
        f"{change(baseline.macro_f1, advanced.macro_f1):>12}",
        f"{'macro precision':<28}{baseline.macro_precision:>12.3f}{advanced.macro_precision:>14.3f}"
        f"{change(baseline.macro_precision, advanced.macro_precision):>12}",
        f"{'macro recall':<28}{baseline.macro_recall:>12.3f}{advanced.macro_recall:>14.3f}"
        f"{change(baseline.macro_recall, advanced.macro_recall):>12}",
        f"{'exact-match bundles':<28}{baseline.exact_match_rate:>12.3f}{advanced.exact_match_rate:>14.3f}"
        f"{change(baseline.exact_match_rate, advanced.exact_match_rate):>12}",
        f"{'cost per bundle (USD)':<28}{baseline.cost_per_bundle:>12.4f}{advanced.cost_per_bundle:>14.4f}"
        f"{change(baseline.cost_per_bundle, advanced.cost_per_bundle):>12}",
        "",
        f"{'PER-CLASS F1':<28}{'BASELINE':>12}{'REWARDGATE':>14}{'SUPPORT':>12}",
        "-" * 66,
    ]
    for before, after in zip(baseline.per_class, advanced.per_class):
        lines.append(
            f"{after.defect:<28}{before.f1:>12.3f}{after.f1:>14.3f}{after.support:>12}"
        )
    return "\n".join(lines)
