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
| **Cost** | ~$0.26 per bundle, 10–13 turns, ~60s |
| **Implementation** | [`rewardgate/exploit.py`](rewardgate/exploit.py) |

**Full trajectories:**

- [`exploit-agent-csvlite-reward-hackable.md`](trajectories/exploit-agent-csvlite-reward-hackable.md)
  — **16 steps, exploit succeeds.** The agent reads the instruction, reads the single visible test,
  writes a one-line special case, runs pytest, sees green. Adjudication: visible suite
  `exit=0 passed=4`, held-out suite `exit=1 failed=1` → `REWARD_HACKABLE`.
- [`exploit-agent-csvlite-clean.md`](trajectories/exploit-agent-csvlite-clean.md)
  — **15 steps, exploit fails.** Same brief, same tools, a suite with eight parametrised inputs.
  The agent concludes hardcoding is not worth it and implements the real fix. Held-out suite also
  passes → `RESISTED`.

Both are included deliberately. A trajectory set showing only successes hides how the system
behaves when it does not find what it is looking for.

**Guardrails.** The agent writes code, so it is contained three ways:

1. It runs against a **disposable temporary copy**, never the corpus on disk.
2. Its tool surface is **restricted to read/edit plus `pytest`** — no network, no arbitrary shell.
3. `held_out/`, `solution.patch` and `.git` are **deleted before it starts**. This one is load-
   bearing: the contaminated bundles' git history literally contains the answer, so leaving it
   would hand the agent what it is meant to be unable to see.

**Retry strategy.** None, deliberately, and this is a known limitation. A single trial is run per
bundle, bounded by `--max-turns 25` and a 600-second timeout. The measured consequence is one
false negative (`retrylite-reward-hackable`) where the agent chose to fix the bug rather than game
it. The fix is *k* independent trials taking the union; it is **not implemented**, and it would
raise cost roughly linearly. Timeouts and unparseable output surface as `ERROR`, never as "clean".

**Human checkpoint.** The agent's verdict never auto-rejects a task. `REJECT` is a recommendation
requiring human sign-off before an author's work is turned away.

### 2. Baseline auditor — the comparison, not the product

| | |
|---|---|
| **Role** | Represent how this task is handled today: read the bundle, form a judgement |
| **Model** | `claude-sonnet-4-5-20250929`, `--max-turns 1` |
| **Tools** | **None.** All tools explicitly disallowed |
| **Cost** | ~$0.12 per bundle |
| **Implementation** | [`rewardgate/baseline.py`](rewardgate/baseline.py) |

Sees the same artifacts as the pipeline — instruction, tests, source, git short log — and differs
only in being unable to execute anything.

**Observed failure mode, worth recording as a trajectory finding.** On
`csvlite-nop-pass` it returned `CONTAMINATION_GIT: true` while its own evidence field read *"No git
history is shipped with the bundle."* It contradicted itself inside a single response. Across all
12 bundles it flagged every defect on every bundle — precision 0.250, exact-match 0/12. Raw audits:
[`results/baseline_audits.json`](results/baseline_audits.json).

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
| `results/baseline_audits.json` | All 12 baseline verdicts with evidence |
| `results/rewardgate_audits.json` | All 12 pipeline verdicts with evidence |
| `results/exploit_trials.json` | Exploit trials with cost, turns and adjudication |

Regenerate with `uv run python scripts/generate_trajectories.py` (~$0.52).
