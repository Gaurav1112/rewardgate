"""Rendering agent trajectories.

The brief asks for trajectories that are easy to follow "from the agent instructions to the final
result", showing what the agent did, how its tools responded, and the feedback that shaped its
next step. A raw JSONL dump satisfies none of that, so this renders the event stream as a readable
transcript while keeping the JSONL alongside it for anyone who wants the unfiltered record.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

MAX_RESULT_CHARS = 900
MAX_TEXT_CHARS = 1200

# Event streams embed the agent runtime's full system prompt, which carries the operator's home
# directory, temp paths and installed tool inventory. None of that is evidence about the audit, and
# publishing it would leak the author's environment into a public repository.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(re.escape(str(Path.home()))), "<HOME>"),
    (re.compile(r"/(?:private/)?(?:var|tmp)/[^\s\"']*"), "<TMP>"),
    (re.compile(r"/Users/[^/\s\"']+"), "<HOME>"),
    (re.compile(r"/home/[^/\s\"']+"), "<HOME>"),
)


def redact(text: str) -> str:
    """Remove environment-identifying paths from text destined for the repository."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _redact_event(event: dict) -> dict:
    """Redact an event by round-tripping it through its JSON form."""
    return json.loads(redact(json.dumps(event)))


def _is_runtime_boilerplate(event: dict) -> bool:
    """True for the runtime's own session-init event.

    It carries the agent runtime's full configuration — every installed plugin, MCP server and
    slash command on the operator's machine. That is the author's environment, not evidence about
    the audit, and it has no place in a published transcript.
    """
    return event.get("type") == "system" and event.get("subtype") == "init"


def _truncate(text: str, limit: int) -> str:
    text = text.rstrip()
    return text if len(text) <= limit else text[:limit] + f"\n... [{len(text) - limit} more chars]"


def _blocks(event: dict) -> list[dict]:
    message = event.get("message") or {}
    content = message.get("content")
    return content if isinstance(content, list) else []


def render(events: list[dict], *, title: str, brief: str) -> str:
    """Render a stream-json event list as a markdown trajectory."""
    lines = [f"# Trajectory — {title}", "", "## Agent instructions", "", "```text",
             brief.rstrip(), "```", "", "## Steps", ""]

    step = 0
    pending_tools: dict[str, str] = {}

    for event in events:
        kind = event.get("type")

        if kind == "assistant":
            for block in _blocks(event):
                if block.get("type") == "text" and block.get("text", "").strip():
                    step += 1
                    lines += [f"### Step {step} — reasoning", "",
                              _truncate(block["text"], MAX_TEXT_CHARS), ""]
                elif block.get("type") == "tool_use":
                    step += 1
                    name = block.get("name", "?")
                    pending_tools[block.get("id", "")] = name
                    payload = json.dumps(block.get("input", {}), indent=2)
                    lines += [f"### Step {step} — tool call: `{name}`", "",
                              "```json", _truncate(payload, MAX_RESULT_CHARS), "```", ""]

        elif kind == "user":
            for block in _blocks(event):
                if block.get("type") != "tool_result":
                    continue
                name = pending_tools.get(block.get("tool_use_id", ""), "tool")
                content = block.get("content")
                if isinstance(content, list):
                    content = "\n".join(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
                status = "error" if block.get("is_error") else "ok"
                lines += [f"**tool response** (`{name}`, {status}) — this is the feedback that "
                          "shaped the next step:", "",
                          "```text", _truncate(str(content or "<empty>"), MAX_RESULT_CHARS),
                          "```", ""]

        elif kind == "result":
            lines += ["## Final result", "",
                      _truncate(str(event.get("result", "")), MAX_TEXT_CHARS), "",
                      "| | |", "|---|---|",
                      f"| turns | {event.get('num_turns', '?')} |",
                      f"| cost (USD) | {event.get('total_cost_usd', 0):.4f} |",
                      f"| duration (ms) | {event.get('duration_ms', '?')} |",
                      f"| stop reason | {event.get('stop_reason', '?')} |", ""]

    return "\n".join(lines)


def save(
    events: list[dict],
    out_dir: Path,
    slug: str,
    *,
    title: str,
    brief: str,
    extra: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write both the readable transcript and the raw JSONL, redacted. Returns both paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    events = [_redact_event(e) for e in events if not _is_runtime_boilerplate(e)]

    markdown = render(events, title=title, brief=brief)
    if extra:
        rows = "\n".join(f"| {k} | {v} |" for k, v in extra.items())
        markdown += f"\n## Adjudication\n\n| | |\n|---|---|\n{rows}\n"

    md_path = out_dir / f"{slug}.md"
    jsonl_path = out_dir / f"{slug}.jsonl"
    md_path.write_text(markdown)
    jsonl_path.write_text("\n".join(json.dumps(e) for e in events))
    return md_path, jsonl_path
