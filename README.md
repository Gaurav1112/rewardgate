# RewardGate

**Audits a candidate benchmark / RL-environment task before it enters a training corpus — and
proves defects by execution rather than by opinion.**

---

## Read this first: how I avoided grading my own homework

The obvious failure mode for a project like this is circular. If I author the defects *and* build
the detector, precision and recall measure nothing but my own imagination. So the evidence is split
into two tiers, and the more important one is not mine:

| Tier | Corpus | Authored by | What it establishes |
|---|---|---|---|
| **Third-party** | [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified), 500 real instances | Princeton NLP — **not me** | The text checkers find real defects in a real, widely-used benchmark |
| Synthetic | 15 bundles, 3 self-authored micro-repos | Me | Baseline-vs-agent comparison on defects requiring execution |

**The cross-validation that matters:** my solution-leakage detector independently measures
**133/500** instances leaking the gold file path in the issue text. *The SWE-bench Illusion*
([arXiv:2506.12286](https://arxiv.org/abs/2506.12286)) reports **135/500**. A two-instance
difference, on a corpus I did not build, against a figure I did not choose.

**And the limit of that defence, stated plainly.** The third-party tier validates *one* checker
against *one* external number. It does **not** de-circularise the headline macro-F1 — that figure
is measured entirely on 15 self-authored bundles whose labels come from the injector that created
them, n=3 per class. The over-specification, hint and weak-assertion rates have no external anchor
at all. Treat the 42.0% defect rate as "what these four checkers find", not as ground truth about
SWE-bench.

**What does make the synthetic comparison meaningful** is the negative controls: three
`clean-git-history` bundles carrying real multi-commit histories that do *not* contain the fix.
Without them, "does `.git` exist?" would score a perfect contamination F1. With them, the
contamination number measures the checker rather than the corpus.

False-positive rate is reported everywhere, never just recall — see [Measured
improvement](#measured-improvement).

---

## Who has this problem

**A contractor paid per accepted task to author agentic coding benchmarks.** Surge AI advertises
[$100–150+/hr for "Agentic Coding RL Environments"](https://surgehq.ai/swe); Mercor runs a
[Quality Control Academy](https://work.mercor.com/jobs/list_AAABmz5zP3ryQLdyseVDjb2O/quality-control-academy-fellowship)
training auditors to catch "overspecification… and gameable shortcuts"; xAI, Handshake and micro1
staff equivalent roles. These people are paid for *accepted* work and personally absorb every
rejection.

### The bottleneck

They find out a task is broken days later, from a reviewer. And the base rate of broken is not
small — **OpenAI's own audit** of 1,699 SWE-bench tasks found **38.3% had underspecified problem
statements**, **61.1% had unit tests that unfairly fail valid solutions**, and **68.3% were
filtered out entirely** ([OpenAI](https://openai.com/index/introducing-swe-bench-verified/)).
OpenAI [retired SWE-bench Verified in 2026](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)
citing flawed tests and leakage.

Checking a task properly today means building a container, running the suite twice, and reading
git history by hand. So it mostly does not happen — and the expensive defects are precisely the
ones that look fine on inspection.

### Why it matters

A defective task is worse than no task. It inflates benchmark scores and feeds false-positive
reward signal into training. At $100–150/hr, each rejected task is hundreds of dollars of expert
time burned.

---

## The core design decision

> **Prove defects by execution, not by opinion.**

Every positive verdict carries a mechanical artifact — a test exit code, a commit SHA, or an
exploit patch that turns a suite green. A model that merely *believes* a task is contaminated
scores nothing here.

This is a response to a measured problem: a 2026 audit found an **18.5% evaluator–human
misalignment rate** across BFCL v4, τ²-Bench, LiveMCPBench and MCP-Atlas
([arXiv:2607.02577](https://arxiv.org/abs/2607.02577)). LLM-as-judge is itself unreliable, so the
primary metric is grounded in test execution instead.

---

## Architecture

```
candidate task bundle
      │
      ├─► Reward gate ──────────────► NOP_PASS           deterministic · $0.00 · ~2s
      │     oracle: gold patch must pass (1.0)
      │     no-op:  empty patch must fail (0.0)
      │
      ├─► History scan ─────────────► CONTAMINATION_GIT  deterministic · $0.00 · <1s
      │     git log -p --all, matched against gold-patch lines
      │
      └─► Adversarial exploit agent ► REWARD_HACKABLE    agentic · ~$0.25 · ~60s
            hostile brief, sandboxed shell, adjudicated by execution
                      │
                      └─► human checkpoint before any REJECT
```

**One agent, two deterministic checkers.** Component count is deliberately low: each defect class
is routed to the *cheapest mechanism that can prove it*. An LLM asked "is this contaminated?"
returns an opinion; `git log -p --all` returns a commit SHA. The opinion costs **$0.1967** per call in
system-prompt overhead alone, before any work ([`results/cli_overhead_probe.json`](results/cli_overhead_probe.json)), and is less convincing.

**Why an agent at all?** Because `REWARD_HACKABLE` is the one class nothing else can settle. A
reward-hackable task **passes the reward gate** — gold patch green, empty patch red, tests look
reasonable. It is indistinguishable from a good task by every mechanical criterion the field uses.
The only way to establish that a task can be gamed is to game it.

---

## What it found

On the third-party corpus — 500 real instances, deterministic checks, **$0.00**:

| Check | Rate |
|---|---:|
| Solution leakage (issue names the gold file) | **133/500 (26.6%)** |
| Over-specification (issue names an *internal* symbol) | 42/500 (8.4%) |
| Hint channel discloses gold-patch lines | 54/500 (10.8%) |
| Weak fail-to-pass assertions | 48/350 (13.7%) of parsed |
| **At least one defect** | **210/500 (42.0%)** |

**Stated limitation:** 150/500 instances are *indeterminate* for assertion analysis — the diff adds
no test function, or is a mid-file hunk that does not parse. They are excluded from the rate, never
counted as clean.

And the demonstration, on a task whose reward gate holds perfectly:

```python
# the exploit agent's patch
if row == 'a,"b,c"':
    return ["a", "b,c"]
return row.split(",")
```

Visible suite **green**. Held-out suite **red**. A benchmark task certifying an agent as correct
while the bug it tests for is untouched.

---

## Measured improvement

15 bundles × 3 defect classes = **45 binary judgements** per system. Identical cases, identical
output schema, identical scorer. All figures below come from
[`results/summary.json`](results/summary.json).

**Primary metric: macro-F1.** Macro because the classes are unbalanced; F1 rather than accuracy
because most pairs are negatives, so a system flagging nothing would score well on accuracy.

| METRIC | BASELINE | REWARDGATE | CHANGE |
|---|---:|---:|---:|
| **macro-F1 (primary)** | 0.524 | **0.933** | **+78.2%** |
| macro precision | 0.500 | 1.000 | +100.0% |
| macro recall | 0.556 | 0.889 | +60.0% |
| exact-match bundles | 9/15 | **14/15** | +55.6% |
| cost per bundle (USD) | 0.1160 | 0.2543 | +119.3% |

| PER-CLASS F1 | BASELINE | REWARDGATE | SUPPORT |
|---|---:|---:|---:|
| NOP_PASS | **1.000** | **1.000** | 3 |
| REWARD_HACKABLE | 0.571 | 0.800 | 3 |
| CONTAMINATION_GIT | **0.000** | **1.000** | 3 |

Full run: **$5.55**, 1613.7s (26.9 min) wall clock.

### The baseline is a real opponent, and it wins one class outright

It flagged all three defects on **zero** of 15 bundles and got **9/15 exactly right**. This is not
a straw man — a careful reader with the same artifacts genuinely solves much of this problem, and
the per-class table shows precisely where reading stops being enough.

**`NOP_PASS` — a tie at 1.000.** A fail-to-pass suite that only asserts a module imports is visibly
inadequate on the page. Executing it proves the same thing the reading did. **The agent adds
nothing here, and the honest conclusion is that this class does not need one.**

**`CONTAMINATION_GIT` — 0.000 versus 1.000, the largest single gap.** The baseline sees
`git log --oneline`, which is innocent: the fix lives on a side branch. It missed all three
contaminated bundles. It also correctly passed all three *clean-git* bundles — so its 0.000 is a
genuine miss, not indiscriminate caution. Only `git log -p --all` finds the fix, and that is a
command, not a judgement.

**`REWARD_HACKABLE` — 0.571 versus 0.800.** The baseline can sometimes tell that a single-input
test looks thin. It cannot tell whether an exploit actually works, and on `semverlite-clean-git-history`
it guessed wrong and flagged a sound task.

**Where the improvement really comes from:** not from being cleverer than the baseline, but from
the two classes where a verdict requires running a command the baseline cannot run. That is a
narrower claim than "+78% overall", and it is the one the evidence supports.

**The honest cost:** RewardGate is **119% more expensive per bundle**. Doubling per-task cost to
recover the contamination class is a trade a reviewer would take, but it is a trade.

### The challenging case

`retrylite-reward-hackable` — a genuine miss, and the reason is substantive rather than a bug.
Told to cheat, the agent **fixed the bug properly instead**. `retrylite`'s real fix is a one-token
`min(...)`, so writing the honest fix cost no more than writing the hardcode.

That is my own cost hypothesis working against me: exploit-based detection has a blind spot when
the genuine fix is as cheap as the exploit. Re-running the same bundle type on `semverlite` found
the exploit immediately, so this is agent variance on an easy fix, not a logic flaw. The honest
mitigation is *k* independent trials taking the union — **not implemented**, and it would raise
cost roughly linearly.

---

## Hot take

**Reward-hackability is a property of the evaluation protocol, not of the individual task.**

My first detector defined the defect as "an exploit exists." It flagged the clean bundle too —
**100% false positives** — because *any* finite, visible test suite can be hardcoded given enough
branches. Existence is not a discriminating property.

Regrading on exploit **cost** — how many literal inputs the exploit must special-case — gave 0
false positives out of 3. Same agent, same corpus, same code; only the definition changed.

The practical consequence is a rule an author can act on before shipping: **test-input diversity is
the defence against reward hacking, and it is measurable in advance.** With eight parametrised
cases the agent chose to genuinely fix the bug *despite being explicitly instructed to cheat*,
because hardcoding eight cases cost more than writing the real implementation. SWE-bench ships its
tests alongside the task, which is exactly why no amount of care on any single task closes this.

---

## Prior art, and what is different here

**BenchJack** ([arXiv:2605.12673](https://arxiv.org/html/2605.12673v1)) drives coding agents to
audit benchmarks for reward-hacking exploits, and is the closest published work. The difference is
posture: BenchJack audits *published benchmarks in bulk, for research*. RewardGate is a
**pre-submission gate for one task**, run by the author before they hand it over, emitting a
reviewer-grade verdict rather than a corpus statistic. Related: RewardHackBench, HackDetect, and
the ABC paper ([arXiv:2507.02825](https://arxiv.org/abs/2507.02825)) on rigorous agentic
benchmarks.

## What I deliberately did not do

- **Real SWE-bench Docker images.** They are 2–10 GB each; twelve will not fit in the 26 GB free on
  this machine. Execution-based classes are demonstrated on self-authored micro-repos instead, and
  the text-based classes run against all 500 real instances.
- **An agent per defect class.** Deterministic checks produce stronger evidence at zero cost for
  every class except one. See [IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md#removed--a-per-defect-class-agent-fan-out).
- **LLM-as-judge scoring.** The 18.5% evaluator-misalignment finding above is the reason.
- **Multi-seed trials.** Known gap; it is the fix for the challenging case and is not implemented.
- **Automatic repair** of detected defects. The tool reports; the human decides.

## Safety

The exploit agent writes code, so it is contained three ways: it runs against a **disposable temp
copy**, its tools are restricted to read/edit plus `pytest` (no network, no arbitrary shell), and
`held_out/`, `solution.patch` and `.git` are **stripped before it starts** — the contaminated
bundles' history literally contains the answer. A **human checkpoint** is required before any
`REJECT` is finalised. The exploits exist so gameable tasks are rejected *before* they train a
model.

## Run it

Full instructions, including a **free path that needs no API key**, are in
[REPRODUCTION.md](REPRODUCTION.md).

```bash
uv sync
./scripts/fetch_real_corpus.sh          # 2.0 MB, checksum-pinned
uv run python corpus/synthetic/build.py # 15 bundles, labels by construction
uv run pytest -q                        # includes regression tests pinning every headline number
uv run python -m rewardgate.report_real # third-party findings, $0.00
uv run python -m rewardgate.evaluate --replay   # re-score saved audits offline, $0.00
```

## Documents

- [IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md) — what changed, why, and what was removed
- [REPRODUCTION.md](REPRODUCTION.md) — clean-environment setup, measured cost and runtime
- [AGENT_TRAJECTORIES.md](AGENT_TRAJECTORIES.md) — every agent, end to end
- [docs/specs/](docs/specs/) — design specification

## Provenance

Everything in this repository was written during the hackathon window (2026-08-28 onward) except
the SWE-bench Verified dataset, which is third-party public data fetched by
`scripts/fetch_real_corpus.sh` and not vendored. Built with Claude Code as the coding agent; the
adversarial exploit agent is the Claude Code CLI in headless mode. No credentials are stored in
this repository.
