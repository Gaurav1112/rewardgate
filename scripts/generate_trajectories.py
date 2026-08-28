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

import json  # noqa: E402
import subprocess  # noqa: E402

from rewardgate import baseline, trajectory  # noqa: E402
from rewardgate.exploit import EXPLOIT_BRIEF, run_exploit_trial  # noqa: E402

BUNDLES = ROOT / "corpus" / "synthetic" / "bundles"
OUT = ROOT / "trajectories"

SELECTED = [
    ("csvlite-reward-hackable", "exploit succeeds — the task is gameable"),
    ("csvlite-clean", "exploit fails — the agent had to fix the bug properly"),
]


def baseline_trajectory(bundle_id: str) -> float:
    """Capture the baseline's single turn as a trajectory.

    The baseline is one prompt with no tools, so it has no tool calls to render. Its trajectory is
    still worth recording: the brief asks for every agent, and the baseline's failure mode — a
    verdict that contradicts its own evidence field — is only visible in the raw response.
    """
    bundle_dir = BUNDLES / bundle_id
    prompt = baseline.build_prompt(bundle_dir)
    completed = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json",
         "--model", baseline.DEFAULT_MODEL, "--max-turns", "1",
         "--disallowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebFetch"],
        capture_output=True, text=True, check=False, timeout=baseline.TIMEOUT_SECONDS,
    )
    envelope = json.loads(completed.stdout)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"baseline-{bundle_id}.md").write_text(
        f"# Trajectory — Baseline auditor, {bundle_id}\n\n"
        "One prompt, no tools, one turn. Included because the brief asks for every agent used. "
        "Its reasoning is sound here; the transcript shows the ceiling of reading without executing.\n\n"
        "## Agent instructions (full prompt)\n\n```text\n"
        f"{prompt}\n```\n\n"
        "## Response\n\n```json\n"
        f"{envelope.get('result', '')}\n```\n\n"
        "| | |\n|---|---|\n"
        f"| turns | {envelope.get('num_turns', '?')} |\n"
        f"| cost (USD) | {float(envelope.get('total_cost_usd', 0)):.4f} |\n"
        f"| duration (ms) | {envelope.get('duration_ms', '?')} |\n"
        f"| tools available | none (all disallowed) |\n"
    )
    cost = float(envelope.get("total_cost_usd", 0) or 0)
    print(f"  baseline trajectory -> baseline-{bundle_id}.md  (${cost:.4f})")
    return cost


def main() -> None:
    total = 0.0
    print("capturing baseline trajectory", flush=True)
    total += baseline_trajectory("csvlite-nop-pass")

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
