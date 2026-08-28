# The bundle format

A **bundle** is one candidate benchmark task: a bug, a suite that should detect it, and the fix.
RewardGate audits bundles, so this file is what you need in order to point it at your own task
rather than at the shipped corpus.

The format is deliberately small. Everything in it exists because some check reads it; there are
no fields kept for future use.

## Layout

```
my-task/
├── instruction.md      # the bug, as an author would describe it to a solver
├── src/                # the code containing the bug
├── tests/              # the fail-to-pass suite — red before the fix, green after
├── held_out/           # an adjudicating suite the solver never sees
├── solution.patch      # the gold fix, as a unified diff
├── conftest.py         # puts src/ on sys.path (copy verbatim; see below)
└── task.yaml           # id, and any known labels
```

`tests/` and `solution.patch` are required. `held_out/` is required only when the exploit trial
runs; `rewardgate audit --no-exploit` does not need it. Missing artifacts are refused by name
before anything executes, with exit code 3 — see *Exit codes*.

## What each check actually reads

| Artifact | Read by | What its absence would do |
|---|---|---|
| `tests/` | reward gate, exploit trial | Both trials collect nothing (pytest exit 4) and the gate reports 0.0 for reasons unrelated to the task |
| `solution.patch` | oracle trial, contamination scan | The oracle trial becomes identical to the no-op trial, so the gate cannot bound anything |
| `held_out/` | exploit adjudication | An exploit becomes indistinguishable from a genuine fix |
| `src/` | the patch, and `conftest.py` | Nothing imports |
| `instruction.md` | the baseline, the exploit agent | The agent has to infer the bug from the tests, which changes what is being measured |
| `.git/` | contamination scan | Reported as "no git history shipped" — *not* as "clean" |

## The rules that make an audit meaningful

**1. `tests/` must be red before the fix and green after.** This is the reward gate, and it is
checked, not assumed. If your suite passes with an empty patch, the audit returns REJECT and it is
correct to do so — the task would score every agent as a solver.

**2. `held_out/` must share no inputs with `tests/`.** This is the load-bearing one, and it is the
rule this project got wrong first. If the held-out suite reuses visible inputs, a patch that
memorises the visible cases passes both suites and is graded a genuine fix. The exploit
adjudication is then decorative. `tests/test_corpus_invariants.py` asserts disjointness for the
shipped corpus; for your own bundles you have to hold the line yourself.

**3. `solution.patch` must apply with `git apply` against the shipped tree.** Generate it rather
than hand-writing it — `git diff` between the buggy and fixed trees, or `difflib.unified_diff`,
which is what `corpus/synthetic/build.py` does. Hand-written diffs get their hunk headers wrong
and fail to apply, and a patch that does not apply is reported as a blocker, not as a clean task.

**4. Make the visible suite diverse.** The number of distinct inputs that exercise the bug is what
sets the price of hardcoding. `csvlite`'s visible suite has 8 quoted-field cases (11 collected
tests) specifically so that special-casing them costs more than implementing the fix — and the
`REWARD_HACKABLE` mutation is exactly the operation of stripping that down to one. This is the
only property that actually resists reward hacking; the exploit trial measures whether you
achieved it, it does not create it.

Eight is not a recommendation, it is what this corpus uses. The threshold that grades an exploit
cheap is 2 hardcoded literals (`REWARD_HACK_THRESHOLD`), so a suite is safe from *that* grading
rule at 3 — but a grading rule is not a design target, and a suite sized to just clear it is a
suite that a slightly more patient agent memorises.

**5. `conftest.py` should be copied verbatim** from any corpus bundle. It exists so bundles run
under a bare `python -m pytest` with no editable install:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
```

Note that the harness *also* sets `PYTHONPATH` explicitly. That redundancy is not an oversight:
pytest derives its rootdir from its arguments, so passing an absolute path to `tests/` puts this
`conftest.py` above `confcutdir` and it is silently never loaded. The conftest is there for people
running pytest by hand; the environment variable is there for the harness.

## `task.yaml`

```yaml
id: my-task            # must match the directory name
base: my-repo          # optional: groups variants of the same underlying code
defects: []            # ground truth, if known — used only for scoring, never read by the audit
```

`defects` exists so a labelled corpus can be scored. **The audit never reads it.** If it did,
every reported metric would be circular. For a real candidate task you are auditing for the first
time, leave it empty or omit the file.

## Running an audit

```bash
uv run rewardgate audit path/to/my-task --no-exploit   # deterministic tiers only: free, offline
uv run rewardgate audit path/to/my-task                # adds the exploit trial (~$0.28, needs an API key)
```

### Exit codes

| Code | Verdict | Meaning |
|---|---|---|
| 0 | ACCEPT | The reward gate holds and no defect was proven |
| 1 | REJECT / REVISE | A defect was proven, with an artifact attached |
| 2 | — | Usage error: no such bundle |
| 3 | INDETERMINATE | A check could not run. **No verdict is claimed.** |

3 is separate from 1 on purpose. "This task is broken" and "I could not check this task" call for
opposite responses — reject the task, versus fix the harness and re-run — and a job gating on
"non-zero" would conflate them. An audit that cannot run its checks reports that it could not run
them; it never reports ACCEPT.

## What the audit will not tell you

It settles three defect classes: `NOP_PASS`, `CONTAMINATION_GIT`, `REWARD_HACKABLE`. A bundle that
returns ACCEPT has cleared those three and nothing else. It has not been checked for an ambiguous
instruction, a flaky suite, a wrong gold patch that happens to satisfy the tests, or a bug that is
uninteresting. ACCEPT means "these three failure modes are absent", which is a narrower claim than
"this is a good task", and the report is worded to keep that distinction visible.
