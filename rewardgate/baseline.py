"""The baseline: one direct prompt with basic instructions.

This is the fair comparison the brief asks for — "a reasonable basic way to handle the task before
using your solution". It is what a competent reviewer does today when they open a task bundle and
form a judgement by reading it.

The baseline sees the same artefacts as the full pipeline: the instruction, the visible tests, the
source, and the git short log. What it cannot do is *run* anything. That resource difference is
the whole hypothesis under test, and it is stated plainly rather than hidden.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rewardgate.schema import Audit, parse_audit, schema_instructions

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
TIMEOUT_SECONDS = 300
MAX_FILE_CHARS = 6000

PREAMBLE = """\
You are reviewing a candidate benchmark task before it enters a model-training corpus.

A benchmark task consists of an instruction describing a bug, source code containing that bug, and
a fail-to-pass test suite that should fail before the fix and pass after it. Your job is to decide
whether this task actually measures anything, or whether it is defective.

Below are the task's contents.
"""


def _read(path: Path) -> str:
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return "<unreadable>"
    return text[:MAX_FILE_CHARS] + ("\n... [truncated]" if len(text) > MAX_FILE_CHARS else "")


def render_bundle(bundle_dir: Path, parity: bool = False) -> str:
    """Render a bundle as the text a reviewer would read.

    `parity=True` hands the baseline `git log -p --all` instead of `git log --oneline`, i.e. the
    same evidence the pipeline's contamination checker reads. This exists to test whether the
    measured advantage is a real capability difference or an artefact of what the baseline was
    shown. Running the experiment that could refute the headline is the point.
    """
    sections: list[str] = []

    instruction = bundle_dir / "instruction.md"
    if instruction.exists():
        sections.append(f"===== instruction.md =====\n{_read(instruction)}")

    for sub in ("tests", "src"):
        for path in sorted((bundle_dir / sub).rglob("*.py")) if (bundle_dir / sub).exists() else []:
            sections.append(f"===== {path.relative_to(bundle_dir)} =====\n{_read(path)}")

    patch = bundle_dir / "solution.patch"
    if patch.exists():
        sections.append(f"===== solution.patch (the gold fix) =====\n{_read(patch)}")

    if (bundle_dir / ".git").exists():
        # `--all` walks every ref; `--oneline` shows only the current branch. Which one the
        # baseline sees decides whether it can possibly detect a fix parked on a side branch, so
        # it is a parameter rather than a constant — see `parity` below.
        args = ["git", "log", "-p", "--all"] if parity else ["git", "log", "--oneline", "-20"]
        log = subprocess.run(
            args, cwd=bundle_dir, capture_output=True, text=True, check=False,
        ).stdout
        label = "git log -p --all" if parity else "git log --oneline"
        sections.append(f"===== {label} =====\n{log[:MAX_FILE_CHARS] or '<empty>'}")
    else:
        sections.append("===== git log =====\n<no git history shipped>")

    return "\n\n".join(sections)


def build_prompt(bundle_dir: Path, parity: bool = False) -> str:
    return f"{PREAMBLE}\n{render_bundle(bundle_dir, parity)}\n\n{schema_instructions()}"


def audit_bundle(bundle_dir: Path, model: str = DEFAULT_MODEL, parity: bool = False) -> Audit:
    """Produce a baseline audit: a single model call with no tools and no execution."""
    bundle_id = bundle_dir.name
    try:
        completed = subprocess.run(
            [
                "claude", "-p", build_prompt(bundle_dir, parity),
                "--output-format", "json",
                "--model", model,
                "--max-turns", "1",
                # No tools at all. The baseline reasons from the text alone.
                "--disallowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebFetch",
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return Audit.empty(bundle_id, error=f"baseline exceeded {TIMEOUT_SECONDS}s")

    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return Audit.empty(bundle_id, error="baseline returned unparseable envelope")

    return parse_audit(
        bundle_id,
        envelope.get("result", ""),
        cost_usd=float(envelope.get("total_cost_usd", 0.0) or 0.0),
        duration_ms=int(envelope.get("duration_ms", 0) or 0),
    )
