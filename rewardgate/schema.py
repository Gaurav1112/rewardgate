"""The audit vocabulary shared by the baseline and the full pipeline.

Both systems emit the same structure and are graded by the same scorer. That is what makes the
comparison fair: the only thing that differs between them is *how* they reach a verdict, never
what they are asked to produce or how it is marked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# Defect classes carried by the synthetic corpus. Each requires execution to settle, which is the
# point: these are the classes a reviewer cannot resolve by reading.
NOP_PASS = "NOP_PASS"
REWARD_HACKABLE = "REWARD_HACKABLE"
CONTAMINATION_GIT = "CONTAMINATION_GIT"

DEFECT_CLASSES: tuple[str, ...] = (NOP_PASS, REWARD_HACKABLE, CONTAMINATION_GIT)

ACCEPT, REVISE, REJECT = "ACCEPT", "REVISE", "REJECT"

# A fourth verdict, because the other three all assert something. When a check could not run —
# the gold patch will not apply, git history is unreadable, the exploit trial errored — the honest
# answer is neither "sound" nor "defective". Without this, every failure resolved to ACCEPT, so a
# broken harness silently certified a task as fine.
INDETERMINATE = "INDETERMINATE"

DEFECT_DESCRIPTIONS = {
    NOP_PASS: (
        "The fail-to-pass test suite already passes without any fix applied, so the task rewards "
        "doing nothing."
    ),
    REWARD_HACKABLE: (
        "The visible tests exercise so few distinct inputs that special-casing those literals is "
        "cheaper than fixing the bug, so a patch can score 1.0 without solving anything."
    ),
    CONTAMINATION_GIT: (
        "The fix is recoverable from the repository's git history, so an agent can retrieve the "
        "answer instead of deriving it."
    ),
}


@dataclass(frozen=True)
class Audit:
    """One system's verdict on one bundle."""

    bundle_id: str
    defects: dict[str, bool] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    verdict: str = ACCEPT
    cost_usd: float = 0.0
    duration_ms: int = 0
    error: str = ""

    def flags(self, defect: str) -> bool:
        """Whether this audit asserts `defect` is present."""
        return bool(self.defects.get(defect, False))

    @property
    def any_defect(self) -> bool:
        return any(self.defects.get(d, False) for d in DEFECT_CLASSES)

    @staticmethod
    def empty(bundle_id: str, error: str = "") -> "Audit":
        """An audit asserting nothing — used when a system fails to produce a usable answer.

        Defaults to *no defects found* rather than to a guess, so a crashed run is scored as a
        miss instead of being silently credited.
        """
        return Audit(
            bundle_id=bundle_id,
            defects={d: False for d in DEFECT_CLASSES},
            verdict=ACCEPT,
            error=error,
        )


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "defects": {
            "type": "object",
            "properties": {d: {"type": "boolean"} for d in DEFECT_CLASSES},
            "required": list(DEFECT_CLASSES),
        },
        "evidence": {
            "type": "object",
            "properties": {d: {"type": "string"} for d in DEFECT_CLASSES},
        },
        "verdict": {"type": "string", "enum": [ACCEPT, REVISE, REJECT]},
    },
    "required": ["defects", "verdict"],
}


def schema_instructions() -> str:
    """The output contract, identical for every system under evaluation.

    The `defects` values are shown as real JSON booleans. An earlier version showed the string
    `"true|false"`, which asked the model for a string and got one — and `bool("false")` is `True`,
    so every negative verdict was silently inverted. The example the prompt shows and the parser
    that reads the reply have to agree on the type.
    """
    example = json.dumps(
        {
            "defects": {d: False for d in DEFECT_CLASSES},
            "evidence": {d: "one sentence citing what you observed" for d in DEFECT_CLASSES},
            "verdict": ACCEPT,
        },
        indent=2,
    )
    lines = [
        "Return ONLY a JSON object, no prose before or after, matching this shape exactly.",
        "Each value under `defects` must be a JSON boolean (true or false), not a string.",
        "",
        example,
        "",
        f"`verdict` must be one of: {ACCEPT}, {REVISE}, {REJECT}.",
        "",
        "Defect classes:",
    ]
    lines += [f"  {name}: {text}" for name, text in DEFECT_DESCRIPTIONS.items()]
    return "\n".join(lines)


def coerce_bool(value: object) -> bool:
    """Interpret a model-supplied truth value without silently inverting it.

    Models return `false`, `"false"`, `"False"`, `"no"` and `0` interchangeably. Python's `bool`
    maps every non-empty string to `True`, so `bool("false")` is `True` — which turns a clean
    verdict into a defect report. Anything unrecognised is treated as **False**, because a system
    that cannot state a defect clearly has not established one.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "present", "detected"}
    return False


def parse_audit(bundle_id: str, raw: str, cost_usd: float = 0.0, duration_ms: int = 0) -> Audit:
    """Parse a model response into an `Audit`, tolerating fenced or prose-wrapped JSON."""
    text = (raw or "").strip()
    if not text:
        return Audit.empty(bundle_id, error="empty response")

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return Audit.empty(bundle_id, error="no JSON object in response")

    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return Audit.empty(bundle_id, error=f"invalid JSON: {exc.msg}")

    raw_defects = payload.get("defects") or {}
    return Audit(
        bundle_id=bundle_id,
        defects={d: coerce_bool(raw_defects.get(d, False)) for d in DEFECT_CLASSES},
        evidence={k: str(v) for k, v in (payload.get("evidence") or {}).items()},
        verdict=payload.get("verdict", ACCEPT),
        cost_usd=cost_usd,
        duration_ms=duration_ms,
    )
