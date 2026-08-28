# Agent Trajectories

Every agent used, in the product and during development, with its role, tools, guardrails, retry
behaviour and human checkpoints. Full transcripts are in [`trajectories/`](trajectories/) as
readable markdown alongside the raw JSONL event streams.

---

## Product agents

### 1. Adversarial exploit agent — the one that matters

| | |
|---|---|
| **Role** | Determine whether a benchmark task can be passed without solving it |
| **Model** | `claude-sonnet-4-5-20250929` |
| **Input** | A sandboxed copy of the bundle: `instruction.md`, `tests/`, `src/` |
| **Output** | A patch, plus `EXPLOIT_FOUND` / `EXPLOIT_NOT_FOUND` |
| **Tools** | `Read`, `Edit`, `Write`, `Glob`, `Grep`, `Bash(python -m pytest:*)` |
| **Cost** | ~$0.25 per bundle, 9–15 turns, ~60s |
| **Implementation** | [`rewardgate/exploit.py`](rewardgate/exploit.py) |

**Full trajectories:**

- [`exploit-agent-csvlite-reward-hackable.md`](trajectories/exploit-agent-csvlite-reward-hackable.md)
  — **11 steps, exploit succeeds.** The agent reads the instruction, reads the single visible test,
  writes a one-line special case, runs pytest, sees green. Adjudication: visible suite
  `exit=0 passed=4`, held-out suite `exit=1 failed=1` → `REWARD_HACKABLE`.
- [`exploit-agent-csvlite-clean.md`](trajectories/exploit-agent-csvlite-clean.md)
  — **15 steps, and the transcript contradicts its own verdict.** The agent wrote a dict
  memorising all eight visible inputs and replied `EXPLOIT_FOUND`. The adjudication nonetheless
  recorded `RESISTED` with **0 hardcoded cases**, because the cost grader's patterns did not match
  a dict literal. This file is kept unedited as the evidence for that bug; the dict pattern was
  added afterwards and the held-out suite, which shared every input with the visible one, was
  rebuilt. See the README's *Main failure mode*.

Both are included deliberately. A trajectory set showing only successes hides how the system
behaves when it does not find what it is looking for.

**Guardrails.**

1. It runs against a **disposable temporary copy**, never the corpus on disk.
2. Its tool surface is **restricted to read/edit plus `pytest`**, with the operator's ambient MCP
   servers and settings excluded from the session (`--strict-mcp-config`, empty `--mcp-config`).
3. `held_out/`, `solution.patch`, `task.yaml`, `.git` and `conftest.py` are **deleted before it
   starts**. The contaminated bundles' history literally contains the answer, and `conftest.py` is
   imported by pytest — a reviewer used that to demonstrate arbitrary host execution.

**What the guardrails do not do.** The allowlist bounds what the agent *invokes*, not the code it
*writes*, and the harness then executes that code. Module-scope statements in an exploit patch run
on the host. Real isolation needs a container with no network; that is **not implemented** and is
the largest outstanding gap. See [README Safety](README.md#safety).

**Retry strategy.** None, deliberately, and this is a known limitation. A single trial is run per
bundle, bounded by `--max-turns 25` and a 600-second timeout. The measured consequence is one
false negative (`retrylite-reward-hackable`): the stored evidence shows an exploit *was* found but
priced at zero special-cases — a cost-grader blind spot, not the agent honestly fixing the bug. An
earlier version of this document told the second story; it was wrong. The fix is *k* independent trials taking the union; it is **not implemented**, and it would
raise cost roughly linearly. Timeouts and unparseable output surface as `ERROR`, never as "clean".

**Human checkpoint.** The agent's verdict never auto-rejects a task. `REJECT` is a recommendation
requiring human sign-off before an author's work is turned away.

### 2. Baseline auditor — the comparison, not the product

| | |
|---|---|
| **Role** | Represent how this task is handled today: read the bundle, form a judgement |
| **Model** | `claude-sonnet-4-5-20250929`, `--max-turns 1` |
| **Tools** | **None.** All tools explicitly disallowed |
| **Cost** | **$0.1174** per bundle (measured) |
| **Implementation** | [`rewardgate/baseline.py`](rewardgate/baseline.py) |

Sees the same artifacts as the pipeline — instruction, tests, source, git short log — and differs
only in being unable to execute anything.

**It is a competent opponent, not a straw man.** Across 15 bundles it flagged all three defects on
**zero** of them and got **11/15 exactly right**, including a perfect 1.000 F1 on `NOP_PASS`. A
suite that only asserts a module imports is visibly inadequate on the page; reading is genuinely
sufficient for that class, and the pipeline's agent adds nothing there.

**Where it fails is specific.** `CONTAMINATION_GIT` F1 **0.000** — it missed all three contaminated
bundles while correctly passing all three clean-git ones. It is shown `git log --oneline`, which is
innocent because the fix sits on a side branch. No amount of reading recovers that; it needs
`git log -p --all`.

Raw audits: [`results/baseline_audits.json`](results/baseline_audits.json).

> **Correction.** An earlier version of this document reported that the baseline "contradicted
> itself", returning `CONTAMINATION_GIT: true` beside evidence saying no git history was shipped,
> and that it flagged every defect on every bundle at precision 0.250. **That was my bug, not the
> model's.** `bool("false")` is `True` in Python, and my prompt template asked for the string
> `"true|false"`, so every negative verdict was inverted before scoring. The model's evidence prose
> and verdict field were both correct. The claim is withdrawn; see
> [IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md#withdrawn--a-finding-that-was-my-own-bug).

### Deterministic components — not agents, by design

`NOP_PASS` and `CONTAMINATION_GIT` are settled by the reward gate and a `git log -p --all` scan.
No model is involved, they cost $0.00, and their evidence is an exit code and a commit SHA rather
than an opinion. An earlier design had one agent per defect class; it was removed. See
[IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md#removed--a-per-defect-class-agent-fan-out).

---

## Development agents

Coding-agent use is required by the brief, and these shaped the project materially, so they are
recorded too.

### 3. Research agents (3, parallel)

**Role:** ground topic selection in evidence rather than memory. **Tools:** web search, page fetch,
paper and repository search. **Guardrail:** each was instructed to mark unverified claims
explicitly and to answer "NOT FOUND" rather than guess.

What they changed:

- Established the hackathon's real rubric, deadline and tie-break order from primary sources.
- Surfaced the quantified pain the README leads with (OpenAI's 68.3% filter rate; the 18.5%
  evaluator-misalignment figure; the MCPMark pass@1→pass^4 collapse).
- Found the published 135/500 leakage figure that the leakage checker is validated against.

### 4. Adversarial design panel (4, parallel)

Four independent lenses on candidate projects: a **judge simulator** scoring against the real
rubric, a **product manager** researching whether the user exists, a **delivery engineer** costing
the build in hours and dollars, and a **red team** attacking every idea.

**Guardrail:** each was told to be harsh and to mark uncertainty; the red team was told explicitly
to assume every idea was mediocre until proven otherwise.

Two decisions came directly from this panel and both changed the project:

1. **The architecture pivot.** The judge simulator predicted a static LLM reviewer would cap out on
   the 30-point engineering criterion — *"why is this an agent and not twelve prompts and
   ripgrep?"* That is why the agent **attacks** tasks instead of reviewing them.
2. **The anti-circularity tier.** The red team identified "you plant the defects and build the
   detector" as the objection that would decide the outcome. The third-party SWE-bench Verified
   tier, and the cross-validation against the published 135/500, exist because of that critique.

A third candidate project (a bilingual engineering-communication tool) was **killed** by this panel
on the grounds that its corpus was employer-internal — a data-policy violation and a
disqualification risk.

### 5. Claude Code — implementation

All code in this repository was written with Claude Code as the coding agent, working from the
design spec in [`docs/specs/`](docs/specs/). The development loop was: write a checker, measure it
on the real corpus, inspect the output, correct the definition, pin the corrected number as a
regression test. Two of the three iterations in the changelog exist because that measurement step
contradicted the implementation.

---

## Trajectory files

| File | Contents |
|---|---|
| `trajectories/exploit-agent-csvlite-reward-hackable.md` | Readable transcript, successful exploit |
| `trajectories/exploit-agent-csvlite-reward-hackable.jsonl` | Raw event stream |
| `trajectories/exploit-agent-csvlite-clean.md` | Readable transcript, failed exploit |
| `trajectories/exploit-agent-csvlite-clean.jsonl` | Raw event stream |
| `trajectories/baseline-csvlite-nop-pass.md` | Baseline: full prompt and raw response |
| `results/baseline_audits.json` | Every baseline verdict, with evidence |
| `results/rewardgate_audits.json` | Every pipeline verdict, with evidence |
| `results/exploit_trials.json` | **Only the four `csvlite` control trials** from Iteration 3 — not the full corpus run |
| `results/eval_run.log` | Console log of the evaluation that produced the headline table |

Regenerate with `uv run python scripts/generate_trajectories.py` (measured $0.5991).

### Two things to be transparent about

**The saved transcripts come from a dedicated trajectory run, not from the evaluation that
produced the headline table.** The evaluation stores verdicts and costs per bundle, not full event
streams. The transcripts are the same agent, same brief, same bundles, produced by
`scripts/generate_trajectories.py` — but they are a separate invocation, and because model
sampling is not pinnable the exploit text may differ from the run that produced the table.

**Transcripts exist for 3 bundles, not all of them.** Storing full event streams for every bundle
on every run would add roughly 100 KB per trial to the repository. The three chosen cover the
distinct outcomes: exploit succeeds, exploit fails, and the baseline's single-turn response.
