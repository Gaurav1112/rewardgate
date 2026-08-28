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
import shlex
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


def verification_commands(bundle_dir: Path, trace: AuditTrace) -> list[str]:
    """The commands a reader pastes to check the report's claims against their own machine.

    Generated from the audit rather than templated, because a hardcoded block was wrong in three
    independent ways at once and every one of them was invisible from the code:

    * `python -m pytest` assumed an ambient interpreter with pytest installed. On a machine with
      only `python3`, and with pytest inside the project venv, the first command a reviewer pastes
      dies at `command not found`.
    * `git stash` was used to undo the gold patch. Bundles are gitignored, so stash does not touch
      them — and a clean bundle ships no `.git` at all, so the command runs against the *enclosing*
      repository and silently stashes the reviewer's own uncommitted work. Actively destructive,
      and it did not even revert the thing it was there to revert.
    * The contamination grep took its search string from `grep '^+' solution.patch | head -1`,
      which is the diff's `+++ b/...` file header, not a line of the fix. That header appears in
      any history containing the file, so the command reported contamination on
      `csvlite-clean-git-history` — the corpus's own negative control.
    """
    from rewardgate.checkers.contamination import _significant_solution_lines
    from rewardgate.gates import read_patch

    # `patch`, not `git apply`. A bundle that ships no `.git` of its own resolves to the enclosing
    # repository, and `git apply` then interprets the diff's paths relative to *that* repo's root
    # rather than the bundle. It exits 0 having patched nothing: the oracle command silently
    # reports the unfixed suite's failures. `patch -p1` is cwd-relative and has no repo semantics.
    # Relative where possible. The absolute form published the operator's home directory into
    # every captured report, and three of those captures were committed to a public repository
    # after the history had already been scrubbed once.
    try:
        shown = bundle_dir.resolve().relative_to(Path.cwd())
    except ValueError:
        shown = bundle_dir
    # shlex.quote, because `bundle_dir` is the untrusted artifact this tool exists to audit and
    # this block is explicitly sold as "paste this to check my claims". A bundle directory named
    # `csvlite-clean$(touch RG_PWNED)` executed on the reviewer's machine when they pasted line
    # one. `|| exit` chains it: without that, a failed `cd` left the following `patch` commands
    # running against the reviewer's own working directory -- the same "operates on the enclosing
    # repo" class as the `git stash` bug this block was rewritten to fix.
    commands = [
        f"cd {shlex.quote(str(shown))} || exit 1",
        "uv run pytest tests/ -q                             # no-op:  expect failures",
        "patch -p1 < solution.patch && uv run pytest tests/ -q  # oracle: expect all pass",
        "patch -R -p1 < solution.patch                       # restore the tree",
    ]

    contamination = trace.contamination
    if not getattr(contamination, "has_git", False):
        commands.append("# no git history shipped, so there is nothing to search for the fix in")
        return commands

    # Search for a line the fix actually adds. Prefer one the checker proved is disclosed, so the
    # reader reproduces the finding rather than a paraphrase of it.
    disclosed = sorted(getattr(contamination, "disclosed_lines", ()) or ())
    candidates = disclosed or sorted(_significant_solution_lines(read_patch(bundle_dir)))
    if not candidates:
        commands.append("# no gold-patch line is distinctive enough to search history for")
        return commands

    # Scoped to `src/` because the bundle commits `solution.patch` itself. In `git log -p` the
    # patch file's own `+` lines appear as `++`, so an unscoped grep matches the gold fix inside
    # the shipped patch and reports contamination on `csvlite-clean-git-history` — the corpus's
    # negative control. The checker is not fooled (it strips one `+` and compares whole lines);
    # an unscoped grep is a looser test than the finding it claims to reproduce.
    expectation = "expect a match" if disclosed else "expect no match"
    needle = candidates[0].replace("'", "'\\''")
    commands.append(f"git log -p --all -- src/ | grep -F '{needle}'   # {expectation}")
    return commands


def render_report(audit: Audit, trace: AuditTrace, bundle_dir: Path) -> str:
    """Render a reviewer-grade audit memo."""
    label, gloss = VERDICT_STYLE.get(audit.verdict, (audit.verdict, ""))
    if audit.verdict == INDETERMINATE and trace.exploit is None:
        gloss = "2 of 3 classes checked — sound so far, but not certified"
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

    skipped = trace.exploit is None
    for defect in (NOP_PASS, CONTAMINATION_GIT, REWARD_HACKABLE):
        present = audit.flags(defect)
        # A class nobody looked at must not render as `ok`. On `--no-exploit` the report was
        # byte-identical for a clean bundle and a known reward-hackable one apart from the test
        # counts, and both said ACCEPT.
        evidence = audit.evidence.get(defect, "")
        blocked = any(w in evidence for w in ("failed to apply", "INDETERMINATE", "did not run"))
        if defect == REWARD_HACKABLE and skipped:
            marker = "skipped"
        elif present:
            marker = "DEFECT "
        elif blocked:
            # A check that could not run must not render green. A user with a corrupt gold patch
            # read "[  ok   ] NOP_PASS" and nearly moved on; the real cause was only in a trailing
            # BLOCKED: line, below the table they were actually scanning.
            marker = "BLOCKED"
        else:
            marker = "  ok   "
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

    lines += ["", _rule(), "VERIFY THIS YOURSELF", _rule(), ""]
    lines += [f"  {line}" for line in verification_commands(bundle_dir, trace)]
    lines.append("")

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
