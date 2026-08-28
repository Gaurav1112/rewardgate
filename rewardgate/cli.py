"""Command-line interface — the tool a task author actually runs.

The deliverable here is the **audit report**: the document a reviewer reads, or that an author
attaches to their submission. It is written to imitate the genre it replaces — a review memo with
a verdict, findings anchored to evidence, and a command the reader can paste to check any claim
themselves.

Every finding carries its artifact. Nothing in the report is an assertion the reader has to take
on trust.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rewardgate.auditor import AuditTrace, audit_bundle
from rewardgate.schema import (
    ACCEPT,
    CONTAMINATION_GIT,
    DEFECT_DESCRIPTIONS,
    INDETERMINATE,
    NOP_PASS,
    REJECT,
    REVISE,
    REWARD_HACKABLE,
    Audit,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLES = ROOT / "corpus" / "synthetic" / "bundles"

# Exit codes. INDETERMINATE gets its own code because a CI job that gates on "not zero" would
# otherwise treat "this task is broken" and "I could not check this task" as the same event. They
# call for opposite responses: reject the task, versus fix the harness and re-run.
EXIT_ACCEPT = 0
EXIT_DEFECT = 1
EXIT_USAGE = 2
EXIT_INDETERMINATE = 3

# The bundle contract, documented in docs/BUNDLE_FORMAT.md. Each value says what silently degrades
# when the artifact is absent — in every case the check stops running but keeps reporting "no
# defect found", which is the precise failure mode this project exists to catch.
REQUIRED_ARTIFACTS = {
    "tests": "the fail-to-pass suite; without it both reward-gate trials collect nothing (pytest exit 4)",
    "solution.patch": "the gold fix; without it the oracle trial is identical to the no-op trial",
}
EXPLOIT_ARTIFACTS = {
    "held_out": "the adjudicating suite; without it an exploit cannot be distinguished from a real fix",
}


def missing_artifacts(bundle_dir: Path, need_exploit: bool = True) -> dict[str, str]:
    """Return the required artifacts absent from `bundle_dir`, mapped to what they cost.

    Checked before running rather than after, because an audit of a directory that is not a bundle
    produces a report full of exit-4 trials whose real cause — "there is no test suite here" — is
    nowhere in the output.
    """
    contract = {**REQUIRED_ARTIFACTS, **(EXPLOIT_ARTIFACTS if need_exploit else {})}
    return {name: why for name, why in contract.items() if not (bundle_dir / name).exists()}

VERDICT_STYLE = {
    ACCEPT: ("ACCEPT", "the reward gate holds and no defect was proven"),
    REVISE: ("REVISE", "repairable — the task measures something, but weakly"),
    REJECT: ("REJECT", "the task cannot measure what it claims"),
    INDETERMINATE: ("INDETERMINATE", "a check could not run — no verdict is claimed"),
}


def _rule(char: str = "-", width: int = 78) -> str:
    return char * width


def render_report(audit: Audit, trace: AuditTrace, bundle_dir: Path) -> str:
    """Render a reviewer-grade audit memo."""
    label, gloss = VERDICT_STYLE.get(audit.verdict, (audit.verdict, ""))
    lines = [
        _rule("="),
        f"REWARDGATE AUDIT — {audit.bundle_id}",
        _rule("="),
        "",
        f"VERDICT: {label}",
        f"         {gloss}",
        "",
        _rule(),
        "FINDINGS",
        _rule(),
        "",
    ]

    for defect in (NOP_PASS, CONTAMINATION_GIT, REWARD_HACKABLE):
        present = audit.flags(defect)
        marker = "DEFECT " if present else "  ok   "
        lines.append(f"[{marker}] {defect}")
        lines.append(f"          {audit.evidence.get(defect, '')}")
        if present:
            lines.append(f"          why it matters: {DEFECT_DESCRIPTIONS[defect]}")
        lines.append("")

    gate = trace.gate
    lines += [
        _rule(),
        "EXECUTED EVIDENCE",
        _rule(),
        "",
        f"  oracle trial (gold patch applied)   reward={gate.oracle.reward}  {gate.oracle.summary}",
        f"  no-op trial  (empty patch)          reward={gate.nop.reward}  {gate.nop.summary}",
    ]

    exploit = trace.exploit
    if exploit is None:
        lines.append("  exploit trial                       not run (--no-exploit)")
    elif exploit.error:
        lines.append(f"  exploit trial                       ERROR: {exploit.error}")
    else:
        lines += [
            f"  exploit trial                       {exploit.verdict}",
            f"    special-cased inputs              {exploit.hardcoded_cases}",
            f"    visible suite under exploit       {exploit.visible.summary if exploit.visible else 'n/a'}",
            f"    held-out suite under exploit      {exploit.held_out.summary if exploit.held_out else 'n/a'}",
            f"    turns / cost                      {exploit.turns} turns, ${exploit.cost_usd:.4f}",
        ]

    contamination = trace.contamination
    if getattr(contamination, "commits", ()):
        lines += ["", "  contaminating commits:"]
        lines += [f"    {c}" for c in contamination.commits]

    if exploit is not None and exploit.produced_patch and exploit.is_reward_hackable:
        lines += ["", _rule(), "EXPLOIT PATCH (this is what made the visible suite pass)", _rule(), ""]
        lines += [f"  {line}" for line in exploit.exploit_patch.splitlines()[:40]]

    lines += [
        "",
        _rule(),
        "VERIFY THIS YOURSELF",
        _rule(),
        "",
        f"  cd {bundle_dir}",
        "  git apply solution.patch && python -m pytest tests/ -q   # oracle: expect pass",
        "  git stash && python -m pytest tests/ -q                  # no-op:  expect fail",
        "  git log -p --all | grep -F \"$(grep '^+' solution.patch | head -1 | cut -c2-)\"",
        "",
    ]

    if audit.verdict == REJECT:
        lines += [
            _rule("!"),
            "HUMAN CHECKPOINT REQUIRED",
            "A REJECT is a recommendation, not a decision. A qualified reviewer must confirm",
            "before an author's work is turned away.",
            _rule("!"),
            "",
        ]

    return "\n".join(lines)


def cmd_audit(args: argparse.Namespace) -> int:
    bundle_dir = Path(args.bundle)
    if not bundle_dir.exists():
        candidate = DEFAULT_BUNDLES / args.bundle
        if not candidate.exists():
            print(f"error: no such bundle: {args.bundle}", file=sys.stderr)
            print(f"       looked in {bundle_dir} and {candidate}", file=sys.stderr)
            return EXIT_USAGE
        bundle_dir = candidate

    absent = missing_artifacts(bundle_dir, need_exploit=not args.no_exploit)
    if absent:
        print(f"error: {bundle_dir} is missing artifacts the audit depends on:", file=sys.stderr)
        for name, why in absent.items():
            print(f"       {name:<16} {why}", file=sys.stderr)
        print("       see docs/BUNDLE_FORMAT.md. No verdict is claimed.", file=sys.stderr)
        return EXIT_INDETERMINATE

    audit, trace = audit_bundle(bundle_dir, run_exploit=not args.no_exploit)
    print(render_report(audit, trace, bundle_dir))
    if audit.error:
        print(f"  BLOCKED: {audit.error}\n")
    if audit.verdict == ACCEPT:
        return EXIT_ACCEPT
    return EXIT_INDETERMINATE if audit.verdict == INDETERMINATE else EXIT_DEFECT


def cmd_list(_args: argparse.Namespace) -> int:
    if not DEFAULT_BUNDLES.exists():
        print("no bundles built. run: uv run python corpus/synthetic/build.py", file=sys.stderr)
        return 2
    for path in sorted(p for p in DEFAULT_BUNDLES.iterdir() if p.is_dir()):
        print(path.name)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rewardgate",
        description="Audit a candidate benchmark task before it enters a training corpus.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    audit_parser = sub.add_parser("audit", help="audit one task bundle")
    audit_parser.add_argument("bundle", help="path to a bundle, or a name under corpus/synthetic/bundles")
    audit_parser.add_argument(
        "--no-exploit", action="store_true",
        help="deterministic checks only — free, offline, no model calls",
    )
    audit_parser.set_defaults(func=cmd_audit)

    list_parser = sub.add_parser("list", help="list available bundles")
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
