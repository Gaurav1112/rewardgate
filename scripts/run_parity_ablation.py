"""The ablation that tests whether the headline survives a fair information fight.

RewardGate's only measured advantage is CONTAMINATION_GIT, where the baseline scores 0.000. But
the baseline is shown `git log --oneline`, and the contaminating commit sits off the current branch
by construction — so that 0.000 may be an artefact of what it was shown rather than a capability
gap.

This reruns the baseline with `git log -p --all` in its prompt: the same evidence the pipeline's
checker reads. If RewardGate still wins, the advantage is about mechanism. If it does not, the
headline is an information asymmetry I designed, and the honest conclusion changes.

Run: uv run python scripts/run_parity_ablation.py   (~$1.80, ~12 min)
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rewardgate import baseline  # noqa: E402
from rewardgate.evaluate import BUNDLES_DIR, RESULTS_DIR, _audit_from_dict, load_truth  # noqa: E402
from rewardgate.scoring import score_audits  # noqa: E402


def main() -> None:
    truth = load_truth()
    ids = sorted(truth)
    audits = []
    for i, bundle_id in enumerate(ids, 1):
        print(f"  [parity {i}/{len(ids)}] {bundle_id}", flush=True)
        audits.append(baseline.audit_bundle(BUNDLES_DIR / bundle_id, parity=True))

    (RESULTS_DIR / "baseline_parity_audits.json").write_text(
        json.dumps([asdict(a) for a in audits], indent=2)
    )

    plain = [_audit_from_dict(x) for x in json.loads((RESULTS_DIR / "baseline_audits.json").read_text())]
    rg = [_audit_from_dict(x) for x in json.loads((RESULTS_DIR / "rewardgate_audits.json").read_text())]

    rows = [
        ("baseline (git log --oneline)", score_audits("plain", plain, truth)),
        ("baseline (git log -p --all)", score_audits("parity", audits, truth)),
        ("RewardGate", score_audits("rg", rg, truth)),
    ]
    print(f"\n{'SYSTEM':<32}{'macro-F1':>10}{'CONTAM F1':>12}{'exact':>8}{'cost':>10}")
    print("=" * 72)
    for name, s in rows:
        contam = next(c.f1 for c in s.per_class if c.defect == "CONTAMINATION_GIT")
        print(f"{name:<32}{s.macro_f1:>10.3f}{contam:>12.3f}{s.exact_match:>6}/15{s.total_cost_usd:>10.4f}")

    summary = {name: {"macro_f1": round(s.macro_f1, 4),
                      "contamination_f1": round(next(c.f1 for c in s.per_class if c.defect == "CONTAMINATION_GIT"), 4),
                      "exact_match": s.exact_match, "cost_usd": round(s.total_cost_usd, 4)}
               for name, s in rows}
    (RESULTS_DIR / "parity_ablation.json").write_text(json.dumps(summary, indent=2))
    print(f"\nsaved -> {RESULTS_DIR / 'parity_ablation.json'}")


if __name__ == "__main__":
    main()
