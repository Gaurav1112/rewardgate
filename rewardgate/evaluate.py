"""Evaluation harness: run both systems over the corpus and score them identically.

Two modes:

* **live** — invokes the models, writes every audit to `results/`, and reports measured cost.
* **replay** — re-scores audits already on disk. No API key, no cost, no network. This exists so a
  judge can reproduce the headline number offline and separately choose whether to spend money
  reproducing the runs that produced it.

Replay is not a convenience. A result nobody can check is not a result, and requiring an API key
to verify arithmetic would put the main claim behind a paywall.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import yaml

from rewardgate import auditor, baseline
from rewardgate.schema import DEFECT_CLASSES, Audit
from rewardgate.scoring import Score, format_comparison, score_audits

ROOT = Path(__file__).resolve().parent.parent
BUNDLES_DIR = ROOT / "corpus" / "synthetic" / "bundles"
RESULTS_DIR = ROOT / "results"


def load_truth() -> dict[str, list[str]]:
    """Ground truth from the corpus manifest — the record of what each mutation injected."""
    manifest = yaml.safe_load((BUNDLES_DIR / "labels.yaml").read_text())
    return {entry["id"]: entry.get("defects") or [] for entry in manifest["bundles"]}


def _audit_to_dict(audit: Audit) -> dict:
    return asdict(audit)


def _audit_from_dict(payload: dict) -> Audit:
    return Audit(
        bundle_id=payload["bundle_id"],
        defects=payload.get("defects", {}),
        evidence=payload.get("evidence", {}),
        verdict=payload.get("verdict", "ACCEPT"),
        cost_usd=payload.get("cost_usd", 0.0),
        duration_ms=payload.get("duration_ms", 0),
        error=payload.get("error", ""),
    )


def save_audits(name: str, audits: list[Audit]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}_audits.json"
    path.write_text(json.dumps([_audit_to_dict(a) for a in audits], indent=2))
    return path


def load_audits(name: str) -> list[Audit]:
    path = RESULTS_DIR / f"{name}_audits.json"
    if not path.exists():
        raise FileNotFoundError(f"no saved audits at {path}; run a live evaluation first")
    return [_audit_from_dict(item) for item in json.loads(path.read_text())]


def run_baseline(bundle_ids: list[str]) -> list[Audit]:
    audits = []
    for index, bundle_id in enumerate(bundle_ids, start=1):
        print(f"  [baseline {index}/{len(bundle_ids)}] {bundle_id}", flush=True)
        audits.append(baseline.audit_bundle(BUNDLES_DIR / bundle_id))
    return audits


def run_rewardgate(bundle_ids: list[str], run_exploit: bool = True) -> list[Audit]:
    audits = []
    for index, bundle_id in enumerate(bundle_ids, start=1):
        print(f"  [rewardgate {index}/{len(bundle_ids)}] {bundle_id}", flush=True)
        audit, _trace = auditor.audit_bundle(BUNDLES_DIR / bundle_id, run_exploit=run_exploit)
        audits.append(audit)
    return audits


def _report(scores: Score) -> None:
    print(
        f"  {scores.system:<12} macro-F1={scores.macro_f1:.3f}  "
        f"P={scores.macro_precision:.3f} R={scores.macro_recall:.3f}  "
        f"exact={scores.exact_match}/{scores.bundles}  ${scores.total_cost_usd:.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RewardGate against the baseline.")
    parser.add_argument(
        "--replay", action="store_true",
        help="score saved audits offline; no API key or network needed",
    )
    parser.add_argument(
        "--no-exploit", action="store_true",
        help="run the deterministic tiers only (free, no model calls)",
    )
    parser.add_argument("--only", help="restrict to bundle ids containing this substring")
    args = parser.parse_args()

    truth = load_truth()
    bundle_ids = sorted(truth)
    if args.only:
        bundle_ids = [b for b in bundle_ids if args.only in b]

    print(f"corpus: {len(bundle_ids)} bundles, {len(DEFECT_CLASSES)} defect classes "
          f"= {len(bundle_ids) * len(DEFECT_CLASSES)} binary judgements\n")

    started = time.time()
    if args.replay:
        print("replay mode — scoring saved audits, no model calls\n")
        baseline_audits, rewardgate_audits = load_audits("baseline"), load_audits("rewardgate")
    else:
        baseline_audits = run_baseline(bundle_ids)
        save_audits("baseline", baseline_audits)
        rewardgate_audits = run_rewardgate(bundle_ids, run_exploit=not args.no_exploit)
        save_audits("rewardgate", rewardgate_audits)

    baseline_score = score_audits("baseline", baseline_audits, truth)
    rewardgate_score = score_audits("rewardgate", rewardgate_audits, truth)

    print()
    _report(baseline_score)
    _report(rewardgate_score)
    print("\n" + format_comparison(baseline_score, rewardgate_score))
    print(f"\nwall clock: {time.time() - started:.1f}s")

    if not args.replay:
        elapsed = time.time() - started

        def block(score: Score) -> dict:
            return {
                "macro_f1": round(score.macro_f1, 4),
                "macro_precision": round(score.macro_precision, 4),
                "macro_recall": round(score.macro_recall, 4),
                "exact_match": score.exact_match,
                "cost_usd": round(score.total_cost_usd, 4),
                "cost_per_bundle_usd": round(score.cost_per_bundle, 4),
                "errors": score.errors,
            }

        # Wall clock is persisted so the runtime quoted in the docs is checkable from an artifact
        # rather than only from console output that scrolls away.
        summary = {
            "bundles": len(bundle_ids),
            "defect_classes": len(DEFECT_CLASSES),
            "judgements_per_system": len(bundle_ids) * len(DEFECT_CLASSES),
            "wall_clock_seconds": round(elapsed, 1),
            "total_cost_usd": round(
                baseline_score.total_cost_usd + rewardgate_score.total_cost_usd, 4
            ),
            "baseline": block(baseline_score),
            "rewardgate": block(rewardgate_score),
        }
        (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"saved -> {RESULTS_DIR}")


if __name__ == "__main__":
    main()
