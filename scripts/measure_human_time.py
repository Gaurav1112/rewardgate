"""Human time per task — the row the challenge PDF names and this project was not reporting.

The PDF's suggested comparison table has three rows: primary outcome, **human time per task**, and
cost per task. Two of the three were reported. This measures the third.

WHAT IS AND IS NOT MEASURED, because this is the easiest number in the project to fake.

A person auditing one task by hand cannot avoid running certain commands. They must run the suite
unpatched, apply the gold patch and run it again, restore the tree, and walk the history looking
for the fix. This script runs exactly that sequence, per bundle, and times it. That wall clock is a
**floor**: it is what the task costs a reviewer who types instantly, reads nothing, and decides
nothing. Real human time is strictly greater and this script does not estimate by how much — no
reviewer was timed, so no such number is reported.

The floor is still the honest comparison, because the same floor is what the tool removes. And it
understates the tool's advantage rather than inflating it, which is the direction an unverifiable
number should err in.

    uv run python scripts/measure_human_time.py

$0.00, no API key. Writes results/human_time.json.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rewardgate.auditor import audit_bundle  # noqa: E402
from rewardgate.diffutil import added_lines  # noqa: E402

BUNDLES = ROOT / "corpus" / "synthetic" / "bundles"
RESULTS = ROOT / "results"


def _run(args: list[str], cwd: Path) -> int:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False).returncode


def manual_floor(bundle: Path) -> float:
    """Seconds of unavoidable command execution to check one task by hand.

    Run on a COPY. Patching the shipped bundle would leave a clean task looking fixed to anything
    else reading the corpus — the exact defect a test in this repository shipped with.
    """
    with tempfile.TemporaryDirectory(prefix="rewardgate-manual-") as tmp:
        work = Path(tmp) / bundle.name
        shutil.copytree(bundle, work, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".pytest_cache"))
        patch = work / "solution.patch"

        start = time.perf_counter()
        # 1. Does the suite already pass without a fix? (NOP_PASS)
        _run([sys.executable, "-m", "pytest", "tests/", "-q", "--no-header", "-p", "no:cacheprovider"], work)
        # 2. Does the gold patch actually make it pass? (solvability)
        _run(["patch", "-p1", "-i", str(patch)], work)
        _run([sys.executable, "-m", "pytest", "tests/", "-q", "--no-header", "-p", "no:cacheprovider"], work)
        _run(["patch", "-R", "-p1", "-i", str(patch)], work)
        # 3. Is the fix sitting in the history? (CONTAMINATION_GIT)
        if (work / ".git").exists():
            needles = [ln.strip() for ln in added_lines(patch.read_text()) if len(ln.strip()) >= 12]
            if needles:
                subprocess.run(
                    f"git log -p --all -- src/ | grep -F {json.dumps(needles[0])}",
                    cwd=work, shell=True, capture_output=True, check=False,
                )
        return time.perf_counter() - start


def tool_time(bundle: Path) -> float:
    start = time.perf_counter()
    audit_bundle(bundle, run_exploit=False)
    return time.perf_counter() - start


def main() -> None:
    if not (BUNDLES / "labels.yaml").exists():
        sys.exit("run: uv run python corpus/synthetic/build.py")

    bundles = sorted(p for p in BUNDLES.iterdir() if p.is_dir())
    rows = []
    print(f"{'BUNDLE':<32}{'MANUAL FLOOR':>14}{'REWARDGATE':>13}")
    print("=" * 59)
    for bundle in bundles:
        manual, tool = manual_floor(bundle), tool_time(bundle)
        rows.append({"bundle_id": bundle.name, "manual_floor_s": round(manual, 2),
                     "rewardgate_s": round(tool, 2)})
        print(f"{bundle.name:<32}{manual:>13.2f}s{tool:>12.2f}s")

    manual_total = sum(r["manual_floor_s"] for r in rows)
    tool_total = sum(r["rewardgate_s"] for r in rows)
    print("=" * 59)
    print(f"{'total, ' + str(len(rows)) + ' tasks':<32}{manual_total:>13.2f}s{tool_total:>12.2f}s")
    print(f"{'per task':<32}{manual_total / len(rows):>13.2f}s{tool_total / len(rows):>12.2f}s")

    payload = {
        "what_this_measures": (
            "Wall clock of the commands a reviewer cannot avoid running to check one task by hand: "
            "the suite unpatched, the gold patch applied and reverted, and a history scan. It is a "
            "FLOOR, not human time -- it excludes typing, reading and deciding. No reviewer was "
            "timed, so no estimate of that overhead is reported."
        ),
        "what_neither_side_covers": (
            "REWARD_HACKABLE. A reviewer cannot settle it by hand at all without writing an exploit, "
            "and the free tier does not attempt it. Both columns are the two deterministic classes."
        ),
        "tasks": len(rows),
        "manual_floor_total_s": round(manual_total, 2),
        "rewardgate_total_s": round(tool_total, 2),
        "manual_floor_per_task_s": round(manual_total / len(rows), 2),
        "rewardgate_per_task_s": round(tool_total / len(rows), 2),
        "per_bundle": rows,
    }
    out = RESULTS / "human_time.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nsaved -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
