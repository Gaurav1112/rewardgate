# RewardGate

## 210 of 500 SWE-bench Verified tasks trip at least one defect check. Deterministically, for $0.00.

The benchmark used to grade coding agents leaks the gold file into the issue text, asserts on
internal symbols, and ships fail-to-pass suites that assert nothing. RewardGate measures all of it
in about a second on a corpus I did not build.

**On the one claim with an outside reference point, stated precisely.** My leakage detector flags
**133/500** instances (**107** on a full path, 26 more on a bare filename). *The SWE-bench Illusion*
([arXiv:2506.12286](https://arxiv.org/abs/2506.12286)) reports **135/500**. Those two numbers are
close, and they are **not the same measurement**: their §4.2 heuristic also fires on import
statements, mine fires on the basename, and neither is specified precisely enough to replicate the
other. Treat it as two independently-written heuristics landing in the same place — corroboration
that the leakage is real and roughly this common, not a reproduction of their figure. An earlier
version of this README called it "two apart, on a corpus I did not build", which read as a
replication it is not.

Across all four checkers, **210 of 500 instances (42.0%)** trip at least one.

**And it replicates out of sample.** One corpus cannot distinguish *"42% of SWE-bench Verified"*
from *"42% of how these benchmarks get built"*, and the checkers were written while looking at
Verified. So I ran them unchanged against **SWE-Gym — 2,438 instances, different repositories,
zero shared instances** (asserted in `tests/test_holdout_corpus.py`, not assumed):

| Check | SWE-bench Verified (500) | SWE-Gym held out (2,438) |
|---|---:|---:|
| Solution leakage | 26.6% | **27.2%** |
| Over-specification | 8.4% | 6.3% |
| Hint discloses gold patch | 10.8% | 3.2% |
| Weak fail-to-pass assertions | 13.7% | 30.7% |
| **At least one defect** | **42.0%** | **43.5%** |

The headline rate holds on 4.9× more data the detectors have never seen. The two that move are
informative rather than embarrassing: SWE-Gym is auto-collected where Verified was human-screened,
so weaker assertions and thinner hint text are what you would expect. `./scripts/fetch_holdout_corpus.sh`
then `uv run python -m rewardgate.report_real --holdout` — $0.00, no model calls. That is what these
four checks find — not a ground-truth defect rate — and it is deterministic, takes about a second,
needs no API key, and reproduces in three commands.

```bash
git clone https://github.com/Gaurav1112/rewardgate && cd rewardgate
uv sync && ./scripts/fetch_real_corpus.sh
uv run python -m rewardgate.report_real
```

RewardGate audits a candidate benchmark or RL-environment task *before* it enters a training
corpus, and **proves defects by execution rather than by opinion** — every positive verdict carries
a test exit code, a commit SHA, or an exploit patch that turns a suite green while the bug it tests
for is untouched.

---

### If you have eight minutes

1. `uv run python -m rewardgate.report_real` — the 42% finding. Free, about a second, no API key.
2. [`rewardgate-demo.mp4`](rewardgate-demo.mp4) — 4:47 walkthrough.
3. [The ablation that refutes the headline](#the-ablation-that-refutes-the-headline) — where I
   disproved my own result. `uv run python scripts/run_parity_ablation.py --replay`.
4. [SUBMISSION.md](SUBMISSION.md) — the four deliverables, and every known defect in one place.
5. [REQUIREMENTS.md](REQUIREMENTS.md) — every challenge requirement mapped to its implementation.

---

## Who has this problem

**A contractor paid per accepted task to author agentic coding benchmarks.** Surge AI advertises
[$100–150+/hr for "Agentic Coding RL Environments"](https://surgehq.ai/swe); Mercor runs a
[Quality Control Academy](https://work.mercor.com/jobs/list_AAABmz5zP3ryQLdyseVDjb2O/quality-control-academy-fellowship)
training auditors to catch "overspecification"; xAI, Handshake and micro1
staff equivalent roles. These people are paid for *accepted* work and personally absorb every
rejection.

### The bottleneck

They find out a task is broken days later, from a reviewer. And the base rate of broken is not
small — **OpenAI's own audit** of 1,699 SWE-bench tasks **flagged 38.3% for underspecified problem
statements** and **61.1% for unit tests that may unfairly fail valid solutions**, and **68.3% were
filtered out entirely** ([OpenAI](https://openai.com/index/introducing-swe-bench-verified/)).
OpenAI [stopped reporting SWE-bench Verified in 2026](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/),
citing flawed tests and contamination. (They stopped using it; the dataset is Princeton's and
still exists.)

Checking a task properly today means building a container, running the suite twice, and reading
git history by hand. So it mostly does not happen — and the expensive defects are precisely the
ones that look fine on inspection.

### Why it matters

A defective task is worse than no task. It inflates benchmark scores and feeds false-positive
reward signal into training. At $100–150/hr, each rejected task is hundreds of dollars of expert
time burned.

---

## Baseline solution and advanced solution

The challenge asks for both, and for the advanced one to be a real improvement rather than a
cosmetic variation. Here they are, named plainly.

**Baseline solution — `rewardgate/baseline.py`.** One direct prompt with basic instructions and no
tools. It is handed the instruction, the visible tests, the source and the git log, and asked for a
verdict in the same schema the full pipeline emits. Run it with
`uv run python -m rewardgate.evaluate --replay`.

**Advanced solution — `rewardgate/auditor.py`.** Two deterministic checkers plus one adversarial
agent, routing each defect class to the cheapest mechanism that can *prove* it. Run it with
`uv run rewardgate audit <bundle>`.

Both see the same bundles, emit the same schema, and are scored by the same function
(`score_audits`). What differs, in the rules' own vocabulary:

| Axis | What the advanced solution adds |
|---|---|
| **Capability** | It can *settle* `REWARD_HACKABLE`. The baseline can only form an opinion about it; the pipeline writes an exploit patch, runs it, and shows the visible suite green while the held-out suite is red. Under the fair (parity) comparison this is also the only class where the two differ: F1 **0.800** vs **0.667**. |
| **Reliability** | Every positive verdict carries a mechanical artifact — an exit code, a commit SHA, an exploit patch. Nothing rests on a model's assertion, which matters given a measured **18.5% evaluator–human misalignment rate** in LLM-as-judge ([arXiv:2607.02577](https://arxiv.org/abs/2607.02577)). |
| **Coverage** | Two of three classes are settled **deterministically at $0.00**, so they can run in CI on every task, not just on a sample. |
| **Engineering quality** | A check that cannot run returns `INDETERMINATE`, never `ACCEPT` — including on `--no-exploit`, where only two of three classes are examined. 258 tests, exit codes that distinguish "broken" from "uncheckable", and a documented bundle contract. |

**And the honest limit, stated here rather than buried.** On the primary metric the advantage is
small: macro-F1 **0.933** against a fair baseline's **0.889** on 15 bundles, one discordant
judgement, **McNemar exact p = 1.00**. The improvement above is real but it is in evidence quality
and coverage, not in a headline score. The [ablation](#the-ablation-that-refutes-the-headline)
that established this is mine, and it is reproducible for free in under a second.

**Coding agents used.** Claude Code (Claude Opus 5) for implementation; the Claude Code CLI in
headless mode is the adversarial exploit agent inside the product itself. Trajectories for both are
in [AGENT_TRAJECTORIES.md](AGENT_TRAJECTORIES.md) and [`trajectories/`](trajectories/).

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

### Why these numbers are not circular

The obvious failure mode for a project like this is circular. If I author the defects *and* build
the detector, precision and recall measure nothing but my own imagination. So the evidence is split
into two tiers, and the more important one is not mine:

| Tier | Corpus | Authored by | What it establishes |
|---|---|---|---|
| **Third-party** | [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified), 500 real instances | Princeton NLP — **not me** | The text checkers find real defects in a real, widely-used benchmark |
| Synthetic | 15 bundles, 3 self-authored micro-repos | Me | Baseline-vs-agent comparison on defects requiring execution |

**The one external reference point.** My solution-leakage detector measures **133/500**; *The
SWE-bench Illusion* reports **135/500** using a different heuristic (theirs also counts import
statements, mine counts bare filenames). Corroboration that the leakage is real, not a
replication of their figure — see the note at the top of this file.

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

## Measured improvement

15 bundles × 3 defect classes = **45 binary judgements** per system. Identical cases, identical
output schema, identical scorer. All figures below come from
[`results/summary.json`](results/summary.json).

**Primary metric: macro-F1.** Macro because the classes are unbalanced; F1 rather than accuracy
because most pairs are negatives, so a system flagging nothing would score well on accuracy.

An earlier version of this section led with **+0.333 macro-F1**, measured against a baseline shown
only `git log --oneline` — which cannot see a fix parked on a side branch. That comparison was
unfair. It is superseded by the ablation below, and the retired table, the per-class breakdown and
the reasoning that retired it are preserved in
[IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md).

Full run: **$5.5877**, 1711.3s wall clock, 45 paired judgements per system.

### The ablation that refutes the headline

Two reviewers independently said the same thing: the baseline is shown `git log --oneline`, while
the contaminating commit sits off the current branch **by construction**. So its 0.000 might be an
artefact of what I showed it rather than a capability gap. That is a testable objection, so I
tested it — `uv run python scripts/run_parity_ablation.py`, results in
[`results/parity_ablation.json`](results/parity_ablation.json).

| System | macro-F1 | CONTAMINATION_GIT F1 | exact-match |
|---|---:|---:|---:|
| baseline, `git log --oneline` | 0.600 | 0.000 | 11/15 |
| **baseline, `git log -p --all`** | **0.889** | **1.000** | **13/15** |
| RewardGate | 0.933 | 1.000 | 14/15 |

**Given the same evidence, the baseline detects contamination perfectly — 1.000, identical to
RewardGate.** The headline gap collapses from **0.333 to 0.044**, which is one judgement out of 45.

That one judgement is worth naming, because it inverts the story told above. Pairing the two
systems gives 0 judgements where only the baseline is right, 1 where only RewardGate is, and
**McNemar exact p = 1.00** — the largest value the test can return. The single discordant pair is
`semverlite-nop-pass / REWARD_HACKABLE`, where the parity baseline raises a **false positive** and
RewardGate does not. So under a fair comparison the residual difference is not contamination at
all, and it is not a mechanism: it is one hallucination the executing system did not make.

That also retires the "ties on its own class" reading in the section above, which was measured
against the unfair baseline and never re-derived after the ablation.

So the honest conclusion is stronger than the one I started with and worse for my own system: the
measured advantage was **an information asymmetry I designed**, not a capability difference. An LLM
shown the right `git` output finds the fix on the side branch without any help from me.

What survives is smaller and duller: the pipeline *runs the right command by default*, deterministically,
for $0.00, and attaches the commit SHA. The baseline only matched it because I hand-fed it ~6 KB of
`git log -p --all` in the prompt — with no artifact, and only because I already knew which command
to run. (The pipeline is not cheaper: $3.83 against the parity baseline's $1.86, because it also
runs an exploit agent. It is the *contamination check* that is free.)

**And the retreat itself has a limit, which cuts the other way.** `baseline.py` truncates that log
to `MAX_FILE_CHARS = 6000`. The corpus histories are 2–4 commits and 5.6–6.7 KB, so the fix lands
inside the window by luck of ordering; the contamination checker reads the history uncapped. The
parity result is therefore a property of a two-commit synthetic corpus, not of the method. On a
repository with ten thousand commits the baseline would see a fraction of a percent of the history
and the checker would still see all of it. I have not tested that, so I am not claiming it — but
the honest statement is that the ablation refutes my headline *at this scale* and is silent above
it, not that the gap is truly 0.044 everywhere.

### So what does this project actually establish?

**A routing result: which defect classes need an agent, and which are waste.** Two of the three are
settled deterministically, at $0.00, in about a second — and the parity ablation proves a
well-informed reader settles them too, once shown the same `git` output. Spending a model call
there buys nothing but latency and an opinion where an exit code was available.

`REWARD_HACKABLE` is the exception, and it is the whole reason an agent is in this pipeline. A
reward-hackable task **passes the reward gate**: gold patch green, empty patch red, tests that read
fine. No mechanical criterion the field currently uses separates it from a sound task. The only way
to establish that a task can be gamed is to game it — so that is the one place the agent is spent,
and it returns a patch and two exit codes rather than a judgement.

That is a finding I would carry to a team building RL environments, because it says where to spend
and where not to. The measured margin on 15 bundles is small and non-significant, and it is
reported that way above. What the agent contributes is not a higher score on this corpus: it is
**executed proof for the one class a reader cannot confirm without running it.**

The rest of the value is **defaults and artifacts** — knowing which command to run, running it
every time without being prompted, and emitting a commit SHA a reviewer can check rather than a
sentence they have to trust.

### The challenging case

`retrylite-reward-hackable` — missed by **both** systems.

The stored evidence in [`results/rewardgate_audits.json`](results/rewardgate_audits.json) reads:
*"the only patch found also fixes held-out behaviour; the task resisted gaming."* That string is
emitted from exactly one branch of `exploit.py` — the one requiring the held-out suite to **pass**.
So the agent did not produce an exploit at all, and the pipeline recorded that as the task
resisting.

The task is reward-hackable by construction. So the blind spot is not in the cost grader: it is
that **one failed exploit attempt is being reported as evidence that no exploit exists.** Absence of
a found attack is not absence of an attack, and the audit's own wording ("the task resisted
gaming") asserts the stronger claim. A single trial cannot support it.

No trajectory was captured for this bundle — `trajectories/` holds `csvlite` only — so I cannot say
whether the agent tried and failed or never tried. That gap is itself the finding: the one case
where I most needed the transcript is the one where I did not save it.

Two earlier versions of this section were wrong. The first said the agent chose to fix the bug
honestly; the second said an exploit was found but priced at zero special-cases. The second is the
evidence string belonging to a **different bundle** — `retrylite-contaminated-git` — which I
misattributed while correcting the first. The changelog records both.

---

## Prior art, and what is different here

**Two pieces of prior art I had cited in my own design spec and then left out of this section.**
An adversarial review caught the omission, and it matters because both are closer to this project
than anything else listed below.

* **[arXiv:2606.16062](https://arxiv.org/abs/2606.16062), *Auditing Reward Hackability in Code RL
  Training Environments*.** Per-task auditing of code-RL environments, a Docker-verified
  incorrect-patch pipeline, and an oracle "gold-sanity gate". That is this project's stated framing
  almost exactly. I cited it in `docs/specs/` for its 28.5% figure and never brought it into the
  comparison.
* **[RewardHackBench](https://github.com/islo-labs/reward-hack-bench).** Its contributor workflow
  already mandates "oracle + nop smoke tests — oracle must succeed and the nop must fail". That is
  the reward gate, as a documented submission requirement, before this project existed.

So the reward gate is not novel, and neither is per-task auditing of RL environments. What I have
not found published is the pair that does the actual work here: **adjudicating an exploit
mechanically by held-out execution with no human in the loop** (Terminal-Bench uses author
inspection), and **grading on exploit *cost* — the count of literal special-cases — rather than on
whether an exploit exists at all.** The second is what turned a detector with a 100% false-positive
rate into one with zero false alarms across six clean bundles.


**The closest prior art is Terminal-Bench 2.0** ([arXiv:2601.11868](https://arxiv.org/abs/2601.11868)),
and the overlap is substantial enough that it needs stating first rather than buried. Its §2.3 and Appendix B describe a pre-merge task QA pipeline that already runs, verbatim:

> "an automated workflow ran the task's oracle solution to ensure solvability… other checks
> verified the absence of common failure modes (e.g., a no-op 'dummy' agent should fail the task)."

> "**B.4 Adversarial Exploit Agent.** During task auditing, we run an adversarial exploit agent to
> attempt to pass the tests by cheating without actually looking at the tests and oracle solutions."

That is oracle + no-op + adversarial exploit agent + git-history hygiene, run by the contributor
before merge. **It is this project's core loop, published first.** Anyone assessing this work
should know that before reading further.

What is actually different, and it is narrower than "a new idea":

1. **Terminal-Bench adjudicates its exploit agent by human inspection** ("manually inspected and
   verified by an author"). Here adjudication is mechanical — held-out execution — so it needs no
   reviewer in the loop to decide whether an exploit counts.
2. **Its git check is an LLM lint over the Dockerfile.** This runs `git log -p --all` matched
   against gold-patch lines, which is what catches a fix parked on a side branch.
3. **Detection rates for this pipeline *have* been published — I was wrong to imply otherwise.**
   *Hardening Agent Benchmarks with Adversarial Hacker-Fixer Loops*
   ([arXiv:2606.08960](https://arxiv.org/abs/2606.08960)) reports **323 of 1,968 tasks (16%)
   hackable across five benchmarks, including 13/89 of Terminal-Bench 2.0**, and
   *Terminal Wrench* ([arXiv:2604.17596](https://arxiv.org/abs/2604.17596)) ships 331
   reward-hackable environments with 3,632 exploit trajectories. What is still different here is
   narrower: those papers measure **how many tasks are hackable**; this measures **the detector** —
   with clean negative controls, a reported false-alarm rate, and a significance test that comes
   back negative.
4. **Exploit *cost* rather than exploit *existence*.** Terminal-Bench flags that a cheat was found.
   Grading on existence gave a 100% false-positive rate here; counting how many literals the cheat
   must special-case is what made the signal usable. I could not find prior work formalising this.

Also relevant: **SpecBench** ([arXiv:2605.21384](https://arxiv.org/abs/2605.21384)) uses the same
visible-versus-held-out pass-rate gap, though to grade agents rather than tasks.
**BenchJack** ([arXiv:2605.12673](https://arxiv.org/abs/2605.12673)) is an automated red-teaming
system that drives coding agents to audit benchmarks, extended into a discover-and-patch loop:
219 flaws found, hackable-task ratio driven from ~100% to under 10% on the four benchmarks without fatal design flaws (10 were audited). That is
substantially more than "bulk research", and an earlier draft of this section understated it. **SWE-Bench+** ([arXiv:2410.06992](https://arxiv.org/abs/2410.06992)) and
**UTBoost** ([arXiv:2506.09289](https://arxiv.org/abs/2506.09289)) precede the leakage and
weak-assertion checks. The **ABC** paper ([arXiv:2507.02825](https://arxiv.org/abs/2507.02825))
gives the checklist this implements an executable subset of.

**A finding that cuts against this project's design:** **EvilGenie**
([arXiv:2511.21654](https://arxiv.org/abs/2511.21654)) reports that an LLM judge detected reward
hacking *highly effectively*, while held-out tests added little lift. This project bets the
opposite way — execution over judgement — on the basis of the 18.5% evaluator-misalignment figure
above. Both can be true in different regimes, and I have not tested an LLM judge here, so treat
the anti-judge stance as a design choice with contrary evidence rather than a settled result.

## What I deliberately did not do

- **Real SWE-bench Docker images.** They are 2–10 GB each; twelve will not fit in the 26 GB free on
  this machine. Execution-based classes are demonstrated on self-authored micro-repos instead, and
  the text-based classes run against all 500 real instances.
- **An agent per defect class.** Deterministic checks produce stronger evidence at zero cost for
  every class except one. See [IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md#removed--a-per-defect-class-agent-fan-out).
- **LLM-as-judge scoring.** The 18.5% evaluator-misalignment finding above is the reason.
- **Multi-seed trials.** Implemented in Iteration 6 and they were *not* the fix. At k=5 the agent
  is deterministic (5/5 or 0/5, nothing between), so the challenging case is a grader blind spot,
  not sampling. What remains unimplemented is a semantic cost measure.
- **Automatic repair** of detected defects. The tool reports; the human decides.

## Safety

**Trust model, stated plainly: `rewardgate audit` executes code from the bundle you point it at.**
That is inherent — the reward gate's whole job is running the task's test suite — and it is true
even under `--no-exploit`. Run it on bundles you authored, or inside a container. This is a
pre-submission self-check, not a tool for auditing strangers' submissions on your laptop.

What containment there is: the agent works on a **disposable temp copy**, its tool surface is
restricted to read/edit plus `pytest`, and `held_out/`, `solution.patch` and `.git` are **stripped
before it starts** — the contaminated bundles' history literally contains the answer. A **human
checkpoint** is required before any `REJECT` is finalised, and a check that cannot run now returns
`INDETERMINATE` rather than defaulting to `ACCEPT`.

**What that containment does not do, because an adversarial review demonstrated it.** An earlier
version of this section claimed "no network, no arbitrary shell". That was wrong. The tool
allowlist constrains what the *agent* may invoke; it does not constrain the code the agent is
explicitly asked to write, and the harness then executes that code — so a patch containing
`import os` at module scope runs on the host. A reviewer also demonstrated a full escape by
writing `conftest.py`, which pytest imports. Proper isolation means a container with no network,
and that is **not implemented** — it is the largest outstanding gap in this project.

The exploits exist so gameable tasks are rejected *before* they train a model. See
[LICENSE](LICENSE) for intended use.

## Run it

Full instructions, including a **free path that needs no API key**, are in
[REPRODUCTION.md](REPRODUCTION.md).

```bash
uv sync
./scripts/fetch_real_corpus.sh          # 2.0 MB, checksum-pinned
uv run python corpus/synthetic/build.py # 15 bundles, labels by construction
uv run pytest -q                        # 258 tests; pins every third-party-corpus number
uv run python -m rewardgate.report_real # third-party findings, $0.00
uv run python -m rewardgate.evaluate --replay   # re-score saved audits offline, $0.00
```

To audit a task of your own rather than one from this corpus, the required layout is in
[docs/BUNDLE_FORMAT.md](docs/BUNDLE_FORMAT.md):

```bash
uv run rewardgate audit path/to/my-task --no-exploit
# exit 1 = defect proven, 3 = a check could not run. Under --no-exploit only 2 of 3
# classes are examined, so exit 0 (ACCEPT) requires the full pipeline.
```

## Documents

- [IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md) — what changed, why, and what was removed
- [REPRODUCTION.md](REPRODUCTION.md) — clean-environment setup, measured cost and runtime
- [AGENT_TRAJECTORIES.md](AGENT_TRAJECTORIES.md) — every agent, end to end
- [REQUIREMENTS.md](REQUIREMENTS.md) — every challenge requirement mapped to its implementation
- [docs/BUNDLE_FORMAT.md](docs/BUNDLE_FORMAT.md) — the bundle contract, for auditing your own tasks
- [docs/specs/](docs/specs/) — design specification

## Provenance

Everything in this repository was written during the hackathon window (2026-08-28 onward) except
the SWE-bench Verified dataset, which is third-party public data fetched by
`scripts/fetch_real_corpus.sh` and not vendored. Built with Claude Code as the coding agent; the
adversarial exploit agent is the Claude Code CLI in headless mode. No credentials are stored in
this repository.

---

## Main failure mode

**The cost grader cannot price an exploit it has no pattern for, and a defect it cannot price is a
defect it does not report.**

The k=5 experiment was designed to test whether `retrylite-reward-hackable` was missed through
sampling noise. It is not. The agent found a working exploit in **5 of 5 trials** — visible suite
green, held-out suite red, every time. What it wrote was an *interval* predicate:

```python
if 7 <= attempt <= 39:
    return MAX_DELAY_SECONDS
```

`_HARDCODE_PATTERNS` matches equality, membership, `startswith`/`endswith`, `case`, and dict keys.
A numeric range guard matches none of them, so `hardcoded_cases` is 0, `cost_measurable` is False,
and the verdict degrades to `GAMEABLE (exploit cost not measurable)` — which `is_reward_hackable`
does not count. The task is reward-hackable, the agent proved it five times out of five, and the
regex could not put a number on it.

So the failure is **detector expressiveness, not agent capability**, and it is the third time a
reviewer has caught this same grader mispricing text it was not written for: a dict literal read as
zero cost, docstrings read as special-cases, and now an interval read as nothing at all. Pricing
memorisation by regular expression over patch lines is the wrong instrument. A semantic measure —
intersecting the literals a patch pins against the literals the visible suite uses, which the code
now half does — is the fix, and it is not implemented.

**I am deliberately not patching the regex.** Adding an interval pattern would flip retrylite to
detected and move macro-F1, but `results/multitrial_preregistration.json` freezes the cost metric,
and changing it after seeing the trials is the tuning that pre-registration exists to prevent. The
honest move is to report the blind spot and leave the number where it fell.

**The measured result, since it is the project's only significant one.** Across all 15 bundles at
k=5 (75 trials, $26.67), every detection is 5/5 and every miss is 0/5 — the agent is deterministic
here, not noisy. Exact permutation test over all 455 relabellings: statistic **+0.667**,
**p = 0.0286**. And zero false alarms in **60 clean trials** at the same k as the positives, the
stronger version of the earlier 0-in-6 figure. This says the agent discriminates reward-hackable
tasks above chance. It does **not** say it beats the baseline, which remains p = 1.00.

Reproduce: `uv run python scripts/run_multitrial.py --replay`, then read any file in
`results/multitrial/retrylite-reward-hackable/`.

## Hot take

**Reward-hackability is a property of the evaluation protocol, not of the individual task.**

My first detector defined the defect as "an exploit exists". It flagged the clean bundle too —
**100% false positives** — because *any* finite, visible test suite can be hardcoded given enough
branches. Existence is not a discriminating property; cost is. Regrading on how many literals the
exploit must special-case took false positives to zero.

The practical rule an author can act on before shipping: **test-input diversity is the defence, and
it is measurable in advance.** A suite with one visible input falls to a single `if`. A suite with
eight costs more to memorise than to solve.

And the second-order lesson, which cost me two rewrites: **the thing measuring your evaluation is
part of your evaluation.** A parser that inverted booleans, a held-out suite that reused its visible
inputs, and a cost counter blind to dict literals each produced confident, plausible, wrong numbers
that passed every test I had. SWE-bench ships its tests alongside the task; no amount of care on any
single task closes that, and no amount of care on any single checker closes this.
