"""Report the deterministic findings across the real third-party corpus.

This is the anti-circularity evidence. The defects measured here were not authored by this
project: SWE-bench Verified is a public dataset assembled by other people, and the leakage rate
this reports is cross-checked against a figure published by an independent research group.

Runs in under a second, makes no model calls, and costs nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from rewardgate.checkers.assertions import analyze_test_assertions
from rewardgate.checkers.hints import detect_hint_contamination
from rewardgate.checkers.leakage import detect_solution_leakage
from rewardgate.checkers.overspec import detect_over_specification
from rewardgate.corpus import load_real_corpus

# "The SWE-bench Illusion" (arXiv:2506.12286) reports 135/500 instances embed the gold file path
# in the issue text. Reproducing that figure independently is the point of citing it.
PUBLISHED_LEAKAGE = 135


def main() -> None:
    bundles = load_real_corpus()
    total = len(bundles)

    leakage = [detect_solution_leakage(b.problem_statement, b.patch) for b in bundles]
    overspec = [detect_over_specification(b.problem_statement, b.patch) for b in bundles]
    hints = [detect_hint_contamination(b.hints_text, b.patch) for b in bundles]
    assertions = [analyze_test_assertions(b.test_patch) for b in bundles]
    parsed = [r for r in assertions if r.parse_ok]

    def line(label: str, count: int, denominator: int = total, note: str = "") -> str:
        return f"{label:<38}{count:>4}/{denominator:<5}({count / denominator * 100:>5.1f}%)  {note}"

    leaked = sum(f.leaked for f in leakage)
    print(f"SWE-bench Verified — {total} instances, deterministic checks, $0.00\n" + "=" * 78)
    print(line("solution leakage (gold file named)", leaked,
               note=f"published figure: {PUBLISHED_LEAKAGE} — delta {abs(leaked - PUBLISHED_LEAKAGE)}"))
    print(line("  of which full path (high conf.)", sum(f.confidence == "high" for f in leakage)))
    print(line("over-specified (internal symbol)", sum(f.over_specified for f in overspec)))
    print(line("  high severity (symbol + file)", sum(f.severity == "high" for f in overspec)))
    print(line("hint text present", sum(f.hints_present for f in hints)))
    print(line("  hint discloses gold-patch lines", sum(f.contaminated for f in hints)))
    print(line("weak fail-to-pass assertions", sum(r.has_weak_assertions for r in parsed), len(parsed),
               note="of instances whose test diff parses"))
    print(line("  assertion parse coverage", len(parsed)))

    flagged = sum(
        1
        for i in range(total)
        if leakage[i].leaked
        or overspec[i].over_specified
        or hints[i].contaminated
        or assertions[i].has_weak_assertions
    )
    print("-" * 78)
    print(line("AT LEAST ONE DEFECT", flagged))
    print(line("clean on all four checks", total - flagged))

    print(
        "\nLimitation stated plainly: "
        f"{total - len(parsed)}/{total} instances are INDETERMINATE for assertion analysis "
        "(the diff adds no test function, or is a mid-file hunk that does not parse). "
        "Those are excluded from the weak-assertion rate rather than counted as clean."
    )

    out = Path(__file__).resolve().parent.parent / "results" / "real_corpus_findings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "instances": total,
        "solution_leakage": leaked,
        "published_leakage_reference": PUBLISHED_LEAKAGE,
        "over_specified_internal": sum(f.over_specified for f in overspec),
        "hint_contamination": sum(f.contaminated for f in hints),
        "weak_assertions": sum(r.has_weak_assertions for r in parsed),
        "assertion_parse_coverage": len(parsed),
        "at_least_one_defect": flagged,
    }, indent=2))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
