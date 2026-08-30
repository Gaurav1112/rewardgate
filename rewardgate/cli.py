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
import json
import shlex
import sys
import textwrap
from pathlib import Path

from rewardgate.auditor import AuditTrace, audit_bundle
from rewardgate.execution import SANDBOX_IMAGE, ContainerConfig, container_available
from rewardgate.schema import (
    ACCEPT,
    DEFECT_REMEDIES,
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
        # Copy to a temp directory first. The previous block ran `patch -p1` against the shipped
        # bundle and reversed it afterwards, which mutates the reviewer's corpus for as long as the
        # suite takes to run. That is the exact pattern `tests/conftest.py`'s session guard now
        # forbids, and it is not hypothetical: it made a *clean* bundle audit as NOP_PASS in this
        # very tool, because every audit path materialises a bundle by copying it and one copy
        # landed inside the window. So this tool was printing, as its own verification recipe, the
        # thing that would fail its own test suite.
        #
        # `--` matters twice over: shlex.quote protects the argument's CONTENT, not its POSITION,
        # and a bundle directory named `-P` emitted `cd -P || exit 1`, which succeeds, moves to the
        # parent, and left the following `patch` running in the reviewer's home directory.
        f'work=$(mktemp -d) && cp -R -- {shlex.quote(str(shown))}/. "$work" && cd -- "$work" || exit 1',
        "uv run pytest tests/ -q                             # no-op:  expect failures",
        "patch -p1 < solution.patch && uv run pytest tests/ -q  # oracle: expect all pass",
        # No restore step: the tree is disposable. Removing it also removes the failure mode where
        # an interrupted paste leaves the bundle patched and every later audit of it wrong.
    ]

    contamination = trace.contamination
    if not getattr(contamination, "has_git", False):
        commands.append("# no git history shipped, so there is nothing to search for the fix in")
        return commands

    # Search for a line the fix actually adds. Prefer one the checker proved is disclosed, so the
    # reader reproduces the finding rather than a paraphrase of it.
    disclosed = sorted(getattr(contamination, "disclosed_lines", ()) or ())
    # `_significant_solution_lines` is keyed by file, so it must be flattened to *lines* here.
    # Iterating the mapping directly yields paths, and `sorted()` accepts both without complaint:
    # the emitted grep silently became a search for `src/csvlite/__init__.py`, which matches the
    # diff header of every commit touching that file and fired on the negative control.
    by_file = _significant_solution_lines(read_patch(bundle_dir))
    candidates = disclosed or sorted(set().union(*by_file.values()) if by_file else ())
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
        # From the auditor's computed set, not a substring guess at its prose.
        blocked = defect in trace.blocked
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

    # Gated on `gameable`, not `is_reward_hackable`. The latter requires 0 < hardcoded_cases <= 2,
    # so the "exploit cost not measurable" verdict — whose own printed advice is *review the patch
    # by hand* — was the one verdict that withheld the patch. That is the most common outcome on
    # this corpus: 33 of 75 saved trials. A report cannot tell the reader to inspect something and
    # then not show it to them.
    if exploit is not None and exploit.produced_patch and exploit.gameable:
        lines += ["", _rule(), "EXPLOIT PATCH (this is what made the visible suite pass)", _rule(), ""]
        lines += [f"  {line}" for line in exploit.exploit_patch.splitlines()[:40]]

    lines += ["", _rule(), "VERIFY THIS YOURSELF", _rule(), ""]
    lines += [f"  {line}" for line in verification_commands(bundle_dir, trace)]
    lines.append("")

    # The reader is an author deciding whether to submit, not an archivist. A verdict without a
    # next step leaves them holding a rejection and nothing to act on, so every proven defect gets
    # the specific repair — and a clean run says so rather than staying silent.
    proven = [name for name, present in audit.defects.items() if present]
    if proven:
        lines += ["", _rule(), "WHAT TO FIX BEFORE YOU SUBMIT", _rule(), ""]
        for name in proven:
            lines.append(f"  {name}")
            lines += [f"    {line}" for line in textwrap.wrap(DEFECT_REMEDIES[name], 74)]
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


HOST_EXECUTION_WARNING = """\
{rule}
CONSEQUENTIAL ACTION: this runs an agent that WRITES code, and then EXECUTES it here.

  * The agent is given a hostile brief and asked to produce a patch for {bundle}.
  * That patch is applied to a temporary copy and run with pytest ON THIS MACHINE.
{isolation}
  * Cost is roughly $0.28 and one model call.

Only run this on a bundle you are willing to execute code from.
Use --no-exploit for the free, offline, deterministic tiers.
{rule}"""

# Two accurate descriptions of two different situations. The unconfined one is the default because
# `--docker` needs an image the reviewer has to build; the confined one still names what it does
# *not* cover, because "runs in a container" reads as total isolation and this is not that.
_UNCONFINED = """\
  * The temp directory isolates the corpus. It does NOT isolate the host: module-scope
    code in the patch runs with your permissions. Pass --docker to contain it."""

_CONFINED = """\
  * The patch is executed in a container with --network none, as a non-root user, with no
    host path mounted. Verify: uv run python scripts/prove_containment.py
  * The AGENT SESSION is still not contained — it needs the network to reach the API.
    It writes to a temp directory and holds Read/Edit/Write/Grep/Glob and pytest."""


def confirm_host_execution(
    bundle_dir: Path, assume_yes: bool, container: ContainerConfig | None = None
) -> bool:
    """Approval before the one consequential action this tool takes.

    Rule 04 asks for human approval *before* the action happens, and the exploit tier was opt-out:
    host execution ran by default with nothing said. Interactive sessions now get a real gate.

    Non-interactive callers are warned and proceed, because the alternative is an interactive
    prompt in CI and in every documented command. That is a deliberate weakening of the gate and
    it is stated rather than hidden: piping input is itself a decision to run unattended.
    """
    print(
        HOST_EXECUTION_WARNING.format(
            rule=_rule("!"), bundle=bundle_dir.name,
            isolation=_CONFINED if container else _UNCONFINED,
        ),
        file=sys.stderr,
    )
    if assume_yes or not sys.stdin.isatty():
        return True
    reply = input("  Type 'yes' to run the exploit trial: ").strip().lower()
    if reply != "yes":
        print("  aborted; nothing was executed", file=sys.stderr)
        return False
    return True


REVIEW_DECISIONS = {"confirm": "confirmed by reviewer", "override": "overridden by reviewer",
                    "defer": "deferred — no decision recorded"}


def record_review(verdict: str, assume_yes: bool) -> tuple[str, int]:
    """Rule 05: put a qualified human in the loop on a verdict that turns away someone's work.

    Returns (decision, exit code). A REJECT is a recommendation and this is where it stops being
    only that: an interactive reviewer confirms, overrides, or defers, and the decision is printed
    into the report so it is part of the record rather than a banner nobody answered.

    `override` exits 0. That is the point of having a human: the tool can be wrong, and a reviewer
    who has looked at the evidence outranks it. `defer` exits 3 — undecided is not the same as
    accepted, and it must not read as one.

    Non-interactive callers get the banner and the tool's own verdict, unchanged. That is a
    weakened gate, and it is stated rather than implied.
    """
    if verdict != REJECT or assume_yes or not sys.stdin.isatty():
        return ("", EXIT_DEFECT if verdict == REJECT else EXIT_ACCEPT)
    print(_rule("!"))
    print("HUMAN CHECKPOINT — this verdict turns away an author's work.")
    print("A REJECT is a recommendation. Record your decision:")
    print("  confirm   the evidence supports rejecting this task")
    print("  override  you have reviewed the evidence and disagree")
    print("  defer     you are not the right reviewer, or need more information")
    print(_rule("!"))
    while True:
        reply = input("  decision [confirm/override/defer]: ").strip().lower()
        if reply in REVIEW_DECISIONS:
            break
    print(f"\n  recorded: {REVIEW_DECISIONS[reply]}")
    return (reply, {"confirm": EXIT_DEFECT, "override": EXIT_ACCEPT,
                    "defer": EXIT_INDETERMINATE}[reply])


def audit_as_dict(audit: Audit, trace: AuditTrace, bundle_dir: Path) -> dict:
    """The verdict as data, for a CI job or a submission pipeline.

    Deliberately includes `exit_code` and `checked_classes`. A caller that reads only `verdict`
    cannot distinguish "no defect found" from "two of three classes were never examined", and that
    is the exact fail-open this project exists to catch — committed by anyone integrating it.
    """
    exploit = trace.exploit
    return {
        "bundle_id": audit.bundle_id,
        "verdict": audit.verdict,
        "exit_code": {ACCEPT: EXIT_ACCEPT, INDETERMINATE: EXIT_INDETERMINATE}.get(
            audit.verdict, EXIT_DEFECT
        ),
        "checked_classes": 2 if exploit is None else 3,
        "total_classes": 3,
        "defects": dict(audit.defects),
        "evidence": dict(audit.evidence),
        "remedies": {n: DEFECT_REMEDIES[n] for n, present in audit.defects.items() if present},
        "executed": {
            "oracle": trace.gate.oracle.summary if trace.gate else None,
            "nop": trace.gate.nop.summary if trace.gate else None,
            "exploit_verdict": exploit.verdict if exploit else "not run (--no-exploit)",
            "exploit_patch": exploit.exploit_patch if exploit and exploit.gameable else "",
        },
        "verify_yourself": verification_commands(bundle_dir, trace),
        "error": audit.error or "",
    }


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

    container = ContainerConfig() if args.docker else None
    if container and (reason := container_available(container)):
        # Fail, do not fall back. A `--docker` run that quietly degrades to host execution is
        # worse than no flag: the reviewer asked for containment, did not get it, and the report
        # says nothing. This is the same fail-closed rule the audit applies to its own checks.
        print(f"error: --docker requested but unavailable: {reason}", file=sys.stderr)
        return EXIT_USAGE

    if not args.no_exploit and not confirm_host_execution(bundle_dir, args.yes, container):
        return EXIT_INDETERMINATE

    audit, trace = audit_bundle(
        bundle_dir, run_exploit=not args.no_exploit, container=container
    )
    report = render_report(audit, trace, bundle_dir)
    print(report)
    if audit.error:
        print(f"  BLOCKED: {audit.error}\n")

    # The report is the deliverable, and until now it existed only on stdout. The person this tool
    # is written for is paid per *accepted* task: they need something to attach to a submission, or
    # to hand a reviewer, or to diff against last week's run. Printing it and throwing it away made
    # the audit a thing you watch rather than a thing you keep.
    if args.out:
        Path(args.out).write_text(report + "\n")
        print(f"  report written to {args.out}\n")
    if args.json:
        Path(args.json).write_text(json.dumps(audit_as_dict(audit, trace, bundle_dir), indent=2) + "\n")
        print(f"  machine-readable verdict written to {args.json}\n")
    if audit.verdict == ACCEPT:
        return EXIT_ACCEPT
    if audit.verdict == INDETERMINATE:
        return EXIT_INDETERMINATE
    decision, code = record_review(audit.verdict, args.yes)
    if decision:
        print(f"  REVIEW DECISION: {REVIEW_DECISIONS[decision]}\n")
    return code


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
    audit_parser.add_argument(
        "--yes", action="store_true",
        help="skip the host-execution confirmation (implied when stdin is not a terminal)",
    )
    audit_parser.add_argument(
        "--out", metavar="FILE",
        help="write the audit memo to FILE — the artifact you attach to a submission",
    )
    audit_parser.add_argument(
        "--json", metavar="FILE",
        help="write the verdict as JSON, including exit_code and how many classes were checked",
    )
    audit_parser.add_argument(
        "--docker", action="store_true",
        help="run every test execution in a network-less container "
             f"(build it first: docker build -t {SANDBOX_IMAGE} docker/)",
    )
    audit_parser.set_defaults(func=cmd_audit)

    list_parser = sub.add_parser("list", help="list available bundles")
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
