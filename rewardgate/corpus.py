"""Loading the real held-out corpus (SWE-bench Verified).

Kept deliberately small: a task bundle is a plain dataclass, so every checker consumes the same
shape whether the bundle came from the third-party corpus or from the synthetic mutation set.
That symmetry is what lets one scorer grade both tiers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REAL_CORPUS_PATH = Path(__file__).resolve().parent.parent / "corpus" / "real" / "raw" / "swebench_verified.parquet"


@dataclass(frozen=True)
class TaskBundle:
    """One candidate benchmark task, in the shape a reviewer receives it."""

    instance_id: str
    repo: str
    problem_statement: str
    patch: str
    test_patch: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    hints_text: str = ""
    difficulty: str = ""

    @property
    def source(self) -> str:
        """`real` for third-party instances, `synthetic` for authored mutants."""
        return "real"


def _parse_test_list(raw: str | list[str] | None) -> tuple[str, ...]:
    """FAIL_TO_PASS / PASS_TO_PASS ship as a JSON-encoded list in the parquet."""
    if raw is None:
        return ()
    if isinstance(raw, list):
        return tuple(raw)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ()
    return tuple(parsed) if isinstance(parsed, list) else ()


def load_real_corpus(path: Path | None = None) -> list[TaskBundle]:
    """Load SWE-bench Verified. Raises if the corpus has not been fetched."""
    target = path or REAL_CORPUS_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"Real corpus not found at {target}. Run: scripts/fetch_real_corpus.sh"
        )

    import pyarrow.parquet as pq  # imported lazily so checkers stay dependency-free

    rows = pq.read_table(target).to_pylist()
    return [
        TaskBundle(
            instance_id=r["instance_id"],
            repo=r["repo"],
            problem_statement=r.get("problem_statement") or "",
            patch=r.get("patch") or "",
            test_patch=r.get("test_patch") or "",
            fail_to_pass=_parse_test_list(r.get("FAIL_TO_PASS")),
            pass_to_pass=_parse_test_list(r.get("PASS_TO_PASS")),
            hints_text=r.get("hints_text") or "",
            difficulty=r.get("difficulty") or "",
        )
        for r in rows
    ]
