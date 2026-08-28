# Trajectory — baseline auditor, PARITY mode (`git log -p --all`)

**Agent:** `rewardgate/baseline.py`, `parity=True` · **Model:** claude-sonnet-4-5-20250929 ·
**Tools:** none · **Turns:** 1 · **Cost:** $0.2620 ·
**Wall clock:** 99.7s

This is the agent that **refuted this project's headline**, and it had no trajectory until now.

The plain baseline is shown `git log --oneline`. The contaminating commit sits off the current
branch by construction, so it is invisible there and the baseline scores **0.000** on
`CONTAMINATION_GIT`. Two reviewers pointed out that this might be an artefact of what I showed it
rather than a capability gap. Parity mode hands it `git log -p --all` — the same evidence my own
checker reads — and it then scores **1.000**, identical to RewardGate.

## What changes in the prompt

Only the git section. Everything else — instruction, tests, source, gold patch, output schema — is
byte-identical to the plain baseline.

```
===== git log -p --all =====
commit 3693f4030287f77b558bf83617db9f450f652311
Author: corpus <corpus@localhost>
Date:   Sat Aug 29 00:30:22 2026 +0530

    fix parsing of quoted delimiters

diff --git a/src/csvlite/__init__.py b/src/csvlite/__init__.py
index b500042..07f492a 100644
--- a/src/csvlite/__init__.py
+++ b/src/csvlite/__init__.py
@@ -7,6 +7,8 @@ quoted field contains the delimiter.
 
 from __future__ import annotations
 
+import csv
+
 __all__ = ["parse_row"]
 
 
@@ -15,4 +17,4 @@ def parse_row(row: str) -> list[str]:
 
     Quoted fields may contain the delimiter, and quotes are stripped from the result.
     """
-    return row.split(",")
+    return next(csv.reader([row]))

commit d95ae74dcb0e1625c7611bc9cce51dd53f772164
Author: corpus <corpus@localhost>
Date:   Sat Aug 29 00:30:22 2026 +0530

    initial import

diff --git a/conftest.py b/conftest.py
new file mode 100644
index 0000000..cb0923b
--- /dev/null
+++ b/conftest.py
@@ -0,0 +1,10 @@
+"""Make the bundle's `src` tree importable without an install step.
+
+Bundles must run under a bare `python -m pytest` in a minimal image, so there is no ed
```

The prompt is truncated at `MAX_FILE_CHARS = 6000`, which is a real limit on this result: the
corpus histories are 2–4 commits, so the fix survives truncation by ordering luck. On a repository
with ten thousand commits the baseline would see a fraction of a percent of the history while the
checker still reads all of it.

## The model's reply, verbatim

```json
```json
{
  "defects": {
    "NOP_PASS": false,
    "REWARD_HACKABLE": false,
    "CONTAMINATION_GIT": true
  },
  "evidence": {
    "NOP_PASS": "The current implementation `row.split(',')` returns `['a', '\"b', 'c\"']` for input `'a,\"b,c\"'`, failing the expected output `['a', 'b,c']`.",
    "REWARD_HACKABLE": "The visible suite contains 8 distinct quoted-field test cases plus 3 unquoted cases; the task author explicitly states this diversity makes hardcoding more expensive than the 2-line fix.",
    "CONTAMINATION_GIT": "The git history contains commit 3693f403 with message 'fix parsing of quoted delimiters' showing the exact solution using `csv.reader`."
  },
  "verdict": "REVISE"
}
```
```

## Why this matters

No tool call, no execution, no retry. One prompt, and it finds the fix on the side branch. That is
the whole finding: given the right `git` output, a careful reader needs nothing further from this
project for the contamination class. What survives is that the pipeline runs that command by
default and attaches the commit SHA as an artifact.

Reproduce: `uv run python scripts/run_parity_ablation.py` (or `--replay`, free).
