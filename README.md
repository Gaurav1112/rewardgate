# RewardGate

## 210 of 500 SWE-bench Verified tasks trip at least one defect check. Deterministically, for $0.00.

The benchmark used to grade coding agents leaks the gold file into the issue text, asserts on
internal symbols, and ships fail-to-pass suites that assert nothing. RewardGate measures all of it
in about a second on a corpus I did not build.

```bash
git clone https://github.com/Gaurav1112/rewardgate && cd rewardgate
uv sync && ./scripts/fetch_real_corpus.sh
uv run python -m rewardgate.report_real
```

RewardGate audits a candidate benchmark or RL-environment task *before* it enters a training
corpus, and **proves defects by execution rather than by opinion** — every positive verdict carries
a test exit code, a commit SHA, or an exploit patch that turns a suite green while the bug it tests
for is untouched.

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
so weaker assertions and thinner hint text are what you would expect.

**On the one claim with an outside reference point, stated precisely.** My leakage detector flags
**133/500** instances (**107** on a full path, 26 more on a bare filename). *The SWE-bench Illusion*
([arXiv:2506.12286](https://arxiv.org/abs/2506.12286)) reports **135/500**. Those two numbers are
close, and they are **not the same measurement**: their §4.2 heuristic also fires on import
statements, mine fires on the basename. Treat it as two independently-written heuristics landing in
the same place — corroboration that the leakage is real and roughly this common, not a reproduction
of their figure.

---

### If you have eight minutes

1. `uv run python -m rewardgate.report_real` — the 42% finding. Free, about a second, no API key.
2. [`rewardgate-demo.mp4`](rewardgate-demo.mp4) — 4:47 walkthrough.
3. [The ablation that refutes the headline](docs/EVALUATION.md#the-ablation-that-refutes-the-headline)
   — where I disproved my own result. `uv run python scripts/run_parity_ablation.py --replay`.
4. [SUBMISSION.md](SUBMISSION.md) — the four deliverables, and every known defect in one place.
5. [REQUIREMENTS.md](REQUIREMENTS.md) — every challenge requirement mapped to its implementation.

---

## Who has this problem

**A contractor paid per accepted task to author agentic coding benchmarks.** Surge AI advertises
[$100–150+/hr for "Agentic Coding RL Environments"](https://surgehq.ai/swe); Mercor runs a
[Quality Control Academy](https://work.mercor.com/jobs/list_AAABmz5zP3ryQLdyseVDjb2O/quality-control-academy-fellowship)
training auditors to catch "overspecification"; xAI, Handshake and micro1 staff equivalent roles.
These people are paid for *accepted* work and personally absorb every rejection.

**The bottleneck.** They find out a task is broken days later, from a reviewer. And the base rate
of broken is not small — **OpenAI's own audit** of 1,699 SWE-bench tasks **flagged 38.3% for
underspecified problem statements** and **61.1% for unit tests that may unfairly fail valid
solutions**, and **68.3% were filtered out entirely**
([OpenAI](https://openai.com/index/introducing-swe-bench-verified/)). OpenAI
[stopped reporting SWE-bench Verified in 2026](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/),
citing flawed tests and contamination. (They stopped using it; the dataset is Princeton's and still
exists.)

Checking a task properly today means building a container, running the suite twice, and reading git
history by hand. So it mostly does not happen — and the expensive defects are precisely the ones
that look fine on inspection.

**Why it matters.** A defective task is worse than no task. It inflates benchmark scores and feeds
false-positive reward signal into training. At $100–150/hr, each rejected task is hundreds of
dollars of expert time burned.

---

## Baseline solution and advanced solution

**Baseline — `rewardgate/baseline.py`.** One direct prompt with basic instructions and no tools. It
is handed the instruction, the visible tests, the source and the git log, and asked for a verdict
in the same schema the full pipeline emits. `uv run python -m rewardgate.evaluate --replay`.

**Advanced — `rewardgate/auditor.py`.** Two deterministic checkers plus one adversarial agent,
routing each defect class to the cheapest mechanism that can *prove* it.
`uv run rewardgate audit <bundle>`.

Both see the same bundles, emit the same schema, and are scored by the same function
(`score_audits`). What differs, in the rules' own vocabulary:

| Axis | What the advanced solution adds |
|---|---|
| **Capability** | It can *settle* `REWARD_HACKABLE`. The baseline can only form an opinion about it; the pipeline writes an exploit patch, runs it, and shows the visible suite green while the held-out suite is red. Under the fair (parity) comparison this is also the only class where the two differ: F1 **0.800** vs **0.667**. |
| **Reliability** | Every positive verdict carries a mechanical artifact — an exit code, a commit SHA, an exploit patch. Nothing rests on a model's assertion, which matters given a measured **18.5% evaluator–human misalignment rate** in LLM-as-judge ([arXiv:2607.02577](https://arxiv.org/abs/2607.02577)). |
| **Coverage** | Two of three classes are settled **deterministically at $0.00**, so they can run in CI on every task, not just on a sample. |
| **Safety** | `--docker` runs every test execution in a network-less, non-root container — [measured both ways](docs/SANDBOXING.md#measured-not-asserted), not asserted. |
| **Engineering** | A check that cannot run returns `INDETERMINATE`, never `ACCEPT` — including on `--no-exploit`, where only two of three classes are examined. 293 tests, exit codes that distinguish "broken" from "uncheckable", and a documented bundle contract. |

**And the honest limit, stated here rather than buried.** On the primary metric the advantage is
small: macro-F1 **0.933** against a fair baseline's **0.889** on 15 bundles, one discordant
judgement, **McNemar exact p = 1.00**. The improvement above is real but it is in evidence quality,
coverage and safety, not in a headline score. The
[ablation](docs/EVALUATION.md#the-ablation-that-refutes-the-headline) that established this is mine,
and it is reproducible for free in under a second.

**Coding agents used.** Claude Code (Claude Opus 5) for implementation; the Claude Code CLI in
headless mode is the adversarial exploit agent inside the product itself. Trajectories for both are
in [AGENT_TRAJECTORIES.md](AGENT_TRAJECTORIES.md) and [`trajectories/`](trajectories/).

---

## Architecture

> **The core design decision: prove defects by execution, not by opinion.**

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

A model that merely *believes* a task is contaminated scores nothing here. This is a response to a
measured problem: a 2026 audit found an **18.5% evaluator–human misalignment rate** across BFCL v4,
τ²-Bench, LiveMCPBench and MCP-Atlas ([arXiv:2607.02577](https://arxiv.org/abs/2607.02577)).
LLM-as-judge is itself unreliable, so the primary metric is grounded in test execution instead.

**One agent, two deterministic checkers.** Component count is deliberately low: each defect class
is routed to the *cheapest mechanism that can prove it*. An LLM asked "is this contaminated?"
returns an opinion; `git log -p --all` returns a commit SHA. The opinion costs **$0.1967** per call
in system-prompt overhead alone, before any work
([`results/cli_overhead_probe.json`](results/cli_overhead_probe.json)), and is less convincing.

**Why an agent at all?** Because `REWARD_HACKABLE` is the one class nothing else can settle. A
reward-hackable task **passes the reward gate** — gold patch green, empty patch red, tests look
reasonable. It is indistinguishable from a good task by every mechanical criterion the field uses.
The only way to establish that a task can be gamed is to game it.

---

## Agent engineering: what the one agent actually required

Component count is a poor proxy for engineering. Every item below exists because something failed
and an adversarial review proved it. Each names the symbol that implements it and the defect it
closes; `tests/test_docs_match_artifacts.py` asserts every symbol still exists.

| # | Mechanism | Where | The failure it closes |
|---|---|---|---|
| 1 | Ambient MCP servers stripped from the agent session | `exploit._run_agent` | The operator's connected tools would otherwise be in scope, so the trial would measure their machine, not the task |
| 2 | Tool allowlist: read/edit the sandbox, run pytest, nothing else | `exploit.ALLOWED_TOOLS` | Bounds what the agent *invokes*. Explicitly does **not** bound what it writes — see Safety |
| 3 | `held_out/`, `solution.patch`, `task.yaml`, `.git`, `conftest.py` withheld | `exploit.WITHHELD_FROM_SANDBOX` | The first two hand over the answer; `.git` carries the fix on contaminated bundles; `conftest.py` is imported by pytest, and a reviewer used it to demonstrate arbitrary host execution |
| 4 | **Environment** allowlist, not the operator's shell | `exploit.agent_env`, `execution.MaterialisedBundle._test_env` | The unfiltered environment on this machine carried `GH_TOKEN`, `AUTH0_CLIENT_SECRET`, `SENDGRID_API_KEY` and a live `SSH_AUTH_SOCK` that can sign as the user |
| 5 | Adjudication on a **fresh** materialisation, not the agent's tree | `exploit.run_exploit_trial` | The agent's own session cannot influence the measurement that grades it |
| 6 | Diff staged and force-added before capture | `exploit.capture_exploit_patch` | An exploit written into a *new* file produced an empty diff; so did a bundle shipping a `.gitignore` that lists `src/`. Both graded "RESISTED — no exploit found" |
| 7 | `held_out_ran` rejects pytest exit 4/5 and timeouts | `exploit.ExploitResult.held_out_ran` | `reward == 0.0` is also what a suite that never ran returns. Reading that as "held-out failed" reports a genuine fix as a proven exploit |
| 8 | `nop_ran`, the same guard on the reward gate | `gates.RewardGateResult.nop_ran` | A bundle whose unpatched suite hangs would be certified ACCEPT with the gate never measured |
| 9 | `cost_measurable` as an explicit state | `exploit.ExploitResult.cost_measurable` | A proven exploit matching no known pattern must not be priced at "0 special-cases, cheaper to fix properly" — that inverts the truth |
| 10 | Cost counts only literals the **visible suite** uses | `exploit.ExploitResult.hardcoded_cases` | `ch == '"'` and `ch == ','` are in every character-scanning parser. Without this gate an honest, merely-incomplete implementation graded REWARD_HACKABLE |
| 11 | Contamination fingerprint subtracted **per file** | `checkers.contamination._shipped_lines` | The bundle author writes the gold patch, so naming a decoy file into it cancelled the real fingerprint and a side-branch fix reported clean |
| 12 | Network-less container for every test execution | `execution.container_create_argv` | Module-scope code in an agent-written patch ran on the host with the operator's permissions |
| 13 | `--docker` fails rather than falling back | `cli.cmd_audit` | A run that silently degrades to host execution is worse than no flag: containment was requested, not delivered, and the report said nothing |
| 14 | Typed confirmation before host execution | `cli.confirm_host_execution` | The consequential action — running agent-written code on your machine — used to happen by default with nothing said |
| 15 | Reviewer records confirm / override / defer on a REJECT | `cli.record_review` | `override` exits 0: a reviewer who has read the evidence outranks the tool |

**And the measurement around it.** k=5 trials on all 15 bundles with Wilson intervals, an exact
permutation test over all 455 relabellings, and a decision rule
[pre-registered](results/multitrial_preregistration.json) before the first trial ran — which is how
the experiment was able to refute its own hypothesis rather than confirm it.

**What is deliberately absent.** No memory across bundles, no orchestration, no retries. Iteration 6
measured whether retries would help: k=1 and k=5 give identical verdicts, so the agent is
deterministic on this corpus and retries buy nothing. Adding components that do not change a
measured outcome is the thing this project argues against.

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

15 bundles × 3 defect classes = **45 binary judgements** per system, identical cases, identical
scorer. **[docs/EVALUATION.md](docs/EVALUATION.md) is the full version**, including why the numbers
are not circular and the case both systems miss. The two results that matter:

**The ablation refutes my own headline.** Two reviewers said the baseline was shown
`git log --oneline` while the contaminating commit sits off the current branch *by construction*,
so its 0.000 might be an artefact of what I showed it. It is:

| System | macro-F1 | CONTAMINATION_GIT F1 | exact-match |
|---|---:|---:|---:|
| baseline, `git log --oneline` | 0.600 | 0.000 | 11/15 |
| **baseline, `git log -p --all`** | **0.889** | **1.000** | **13/15** |
| RewardGate | 0.933 | 1.000 | 14/15 |

The gap collapses from **0.333 to 0.044** — one judgement in 45, **McNemar exact p = 1.00**. The
measured advantage was an information asymmetry I designed, not a capability difference.

**What survives is a second question the tie does not answer** — *can a reviewer check this without
redoing the work?*

| | parity baseline | RewardGate |
|---|---:|---:|
| Positive verdicts / correct | 9 / 8 | 8 / **8** |
| False positives | **1** | **0** |
| Backed by an **executed** artifact | **0** | **8** |
| Cost to audit 2,938 third-party instances | ~$345 extrapolated | **$0.00** |

The parity baseline does cite commit SHAs — it was shown the log and reports what it read. But a
cited artifact and an executed one are indistinguishable until one of them is fabricated, and one
of its nine is (`semverlite-nop-pass / REWARD_HACKABLE`, a hallucinated defect on a sound task).
The macro-F1 comparison is a tie and stays a tie.

---

## Prior art

**Terminal-Bench 2.0** ([arXiv:2601.11868](https://arxiv.org/abs/2601.11868)) already runs oracle +
no-op + an adversarial exploit agent + git-history hygiene as a pre-merge QA pipeline. **It is this
project's core loop, published first**, and anyone assessing this work should know that before
reading further. Detection rates have been published too
([arXiv:2606.08960](https://arxiv.org/abs/2606.08960): 323/1,968 tasks hackable across five
benchmarks).

What I have not found published is the pair doing the actual work here: **adjudicating an exploit
mechanically by held-out execution** with no human in the loop (Terminal-Bench uses author
inspection), and **grading on exploit *cost*** — the count of literal special-cases — rather than
on whether an exploit exists. Grading on existence gave a **100% false-positive rate**; cost took
it to zero across six clean bundles.

Full treatment, including **EvilGenie** ([arXiv:2511.21654](https://arxiv.org/abs/2511.21654)),
which reports evidence *against* this project's execution-over-judgement bet:
**[docs/PRIOR_ART.md](docs/PRIOR_ART.md)**.

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
even under `--no-exploit`.

```bash
docker build -t rewardgate-sandbox:1 docker/
uv run rewardgate audit path/to/my-task --docker
```

`--docker` runs the no-op trial, the oracle trial and the adjudication in a container with
`--network none`, as a non-root user, with capabilities dropped and **no host path mounted**. It is
**measured, not asserted** — `scripts/prove_containment.py` runs the same hostile probe both ways:

| probe | host | contained |
|---|---|---|
| open a socket | `reachable` | `blocked (OSError)` |
| write to a host path | `written` | `blocked (FileNotFoundError)` |
| canary on disk afterwards | `True` | `False` |

**What it still does not cover.** The **agent session** is not contained and cannot be under
`--network none`, because that session *is* an API call. It is bounded by a temp copy, a tool
allowlist, and an environment allowlist — not by a container. `--docker` is also opt-in, so the
default path still executes agent-written code on the host, and the approval banner says so in
those words. Full trust model: **[docs/SANDBOXING.md](docs/SANDBOXING.md)**.

A **human checkpoint** is required before any `REJECT` is finalised, and a check that cannot run
returns `INDETERMINATE` rather than defaulting to `ACCEPT`. The exploits exist so gameable tasks are
rejected *before* they train a model. See [LICENSE](LICENSE) for intended use.

## Run it

Full instructions, including a **free path that needs no API key**, are in
[REPRODUCTION.md](REPRODUCTION.md).

```bash
uv sync
./scripts/fetch_real_corpus.sh          # 2.0 MB, checksum-pinned
uv run python corpus/synthetic/build.py # 15 bundles, labels by construction
uv run pytest -q                        # 293 tests; pins every third-party-corpus number
uv run python -m rewardgate.report_real # third-party findings, $0.00
uv run python -m rewardgate.evaluate --replay   # re-score saved audits offline, $0.00
```

To audit a task of your own, the required layout is in
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
- [docs/EVALUATION.md](docs/EVALUATION.md) — the full measured comparison and the ablation
- [docs/SANDBOXING.md](docs/SANDBOXING.md) — trust model, what `--docker` contains and what it does not
- [docs/PRIOR_ART.md](docs/PRIOR_ART.md) — the full prior-art treatment
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
