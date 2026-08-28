"""Generate the agent trajectory logs required by the submission.

Runs the exploit agent against representative bundles and renders each run as a readable
transcript plus the raw JSONL. Two bundles are chosen deliberately: one the agent exploits, and
one it fails to exploit. A trajectory set showing only successes hides how the system behaves when
it is wrong.

Run:  uv run python scripts/generate_trajectories.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rewardgate import trajectory  # noqa: E402
from rewardgate.exploit import EXPLOIT_BRIEF, run_exploit_trial  # noqa: E402

BUNDLES = ROOT / "corpus" / "synthetic" / "bundles"
OUT = ROOT / "trajectories"

SELECTED = [
    ("csvlite-reward-hackable", "exploit succeeds — the task is gameable"),
    ("csvlite-clean", "exploit fails — the agent had to fix the bug properly"),
]


def main() -> None:
    total = 0.0
    for bundle_id, why in SELECTED:
        print(f"running: {bundle_id} ({why})", flush=True)
        result = run_exploit_trial(BUNDLES / bundle_id)
        total += result.cost_usd

        md, jsonl = trajectory.save(
            list(result.transcript),
            OUT,
            f"exploit-agent-{bundle_id}",
            title=f"Exploit agent — {bundle_id}",
            brief=EXPLOIT_BRIEF,
            extra={
                "verdict": result.verdict,
                "hardcoded cases": result.hardcoded_cases,
                "risk": result.risk,
                "visible suite": result.visible.summary if result.visible else "n/a",
                "held-out suite": result.held_out.summary if result.held_out else "n/a",
                "adjudication": result.reason,
            },
        )
        print(f"  {result.verdict}  ->  {md.name}, {jsonl.name}  (${result.cost_usd:.4f})")

    print(f"\ntotal: ${total:.4f}")


if __name__ == "__main__":
    main()
