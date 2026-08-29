# Improvement Changelog

How RewardGate evolved, and what each change actually bought. Every "evidence" cell is a number I
measured, not an estimate. Experiments that were removed are included, because the ones that
failed taught more than the ones that worked.

Each stage is measured on the same corpus with the same scorer.

## Summary

| Stage | What I tried and why | Evidence | Decision / Learning |
|---|---|---|---|
| **Baseline** | One direct prompt, no tools — the brief's own suggested baseline | macro-F1 **0.600**, exact 11/15, $0.1174/bundle | Established the starting point |
| **Iteration 1** | AST weak-assertion analysis, after seeing suites that only assert a module imports | 48/350 real instances flagged; a coverage hole my own fixtures had hidden | **Kept.** Fixtures chosen to pass are not a test set |
| **Iteration 2** | Over-specification checker (asserts on internal symbols) | 42/500; caught and fixed a 5× overcount in my own counter | **Kept.** The measuring instrument needs its own tests |
| **Iteration 3** | Adversarial exploit agent — the one component that needs a model | Proves REWARD_HACKABLE by execution; visible green, held-out red | **Kept.** But my first definition of the defect was simply wrong |
| **Iteration 4** | Parity ablation: give the baseline `git log -p --all`, the same evidence my checker reads | baseline **0.889** vs RewardGate **0.933**; gap 0.333 → **0.044**; McNemar **p = 1.00** | **Kept, and it refuted my own headline.** The advantage was an information asymmetry I designed |
| **Iteration 6b** | k=5 exploit trials on all 15 bundles, pre-registered | 2/3 detected 5/5, `retrylite` 0/5, 0 false alarms in 60 clean trials, **p = 0.0286** | **Kept, hypothesis refuted.** Verdicts are deterministic (every detection rate 0.0 or 1.0); exploit *generation* is not (9/15 bundles mixed). The miss is detector expressiveness, not agent capability |
| **Iteration 5** | Adversarial panel against the shipped tool | 4 working fail-opens found, each reporting a defective task as sound | **Kept.** My own thesis applied to my own code |
| **Removed** | A five-agent fan-out, one LLM per defect class | Deterministic checks give stronger evidence at $0.00: an exit code and a commit SHA beat an opinion | **Removed.** Number of agents is not a measure of engineering |
| **Final** | Deterministic tiers + one adversarial agent | macro-F1 **0.933** vs a *fair* baseline's **0.889**, n=15, p=1.00 | Main contribution: **42% of SWE-bench Verified is defective, measured for $0.00** |

The sections below give each stage in full, including the numbers I had to withdraw.

---

## Stage 0 — Baseline

**What I tried and why.** One direct prompt with basic instructions, no tools: paste the task
bundle into a model and ask whether it is sound. This is the brief's own suggested baseline and it
is what a reviewer does today — open the bundle, read it, form a judgement.

**Evidence.** See the comparison table in [README.md](README.md#measured-improvement).

**Decision.** Kept as the permanent comparison point. The baseline sees exactly the same artifacts
as the final system — instruction, tests, source, git short log — and differs only in being unable
to execute anything. Holding the inputs constant is what makes the resource difference the finding
rather than a confound.

---

## Iteration 1 — Weak-assertion analysis, and a coverage hole my fixtures hid

**What I tried and why.** An AST-based checker for fail-to-pass tests that assert nothing
meaningful (`assert x is not None`, bare `except: pass`, no assertion at all). I parsed the added
lines of each `test_patch` as a Python module.

Against my own fixtures it passed 11 of 11. Against the 500 real SWE-bench Verified instances it
**declined to give a verdict on 54% of them**.

The cause: my fixtures were clean whole-file additions. Real `test_patch` hunks edit *existing*
files, so their added lines start at arbitrary indentation mid-file and are not a parseable
module. I had validated the checker only against input shaped the way I happened to write it.

**Evidence.**

| Measure | Before | After |
|---|---:|---:|
| Assertion parse coverage | 231/500 (46.2%) | **350/500 (70.0%)** |
| Syntax-error failures | 176 | **57** |
| Test functions scored | 312 | **481** |

The fix was block-level recovery: extract each `def test_*` with its decorators, dedent it, and
parse it independently rather than parsing the hunk as one unit.

**Decision.** Kept. Also adopted a rule that shaped everything after it — an unparseable hunk
returns **indeterminate**, never "clean". A tool auditing benchmarks for silent failure must not
fail silently itself. 150/500 instances remain indeterminate and are reported as such rather than
being counted as passing.

---

## Iteration 2 — Over-specification, and a 5× overcount I caught myself

**What I tried and why.** Detect issues that name the symbol their own fix modifies, which removes
the diagnosis step the task claims to measure. First implementation flagged any named symbol
appearing in the issue text: **229/500 (45.8%)**.

That number was too high to be true, so I inspected the flags instead of publishing them. Most
were reporters naming the **public API they called** — *"`Table.write` drops the supplied
formats"*. That is a good bug report, not a leaked solution. Git's hunk-context header hands you
the enclosing function regardless of whether it is public or internal, and I had been counting
both.

**Evidence.**

| Measure | Counting any symbol | Counting internal symbols only |
|---|---:|---:|
| Over-specified | 229/500 (45.8%) | **42/500 (8.4%)** |
| Headline "at least one defect" | 310/500 (62.0%) | **210/500 (42.0%)** |

Samples that separated the two: public-only flags were `write`, `RST`, `ITRS`. Internal flags were
`_format_float`, `_parse_quoted` — names a reporter could not produce without having seen the
patch.

**Decision.** Kept, graded by symbol visibility. **Learning: precision matters more than recall
when the output is a rejection**, because a false positive costs an author a rewrite they never
needed. I would rather miss a marginal defect than send someone to rework a sound task.

---

## Iteration 3 — The adversarial exploit agent, and a definition that was simply wrong

**What I tried and why.** Three defect classes are settled by deterministic checks. `REWARD_HACKABLE`
is not, because a reward-hackable task **passes the reward gate**: gold patch green, empty patch
red, tests look reasonable. It is indistinguishable from a good task by every mechanical criterion
the field uses. So I built an agent given a hostile brief — make the visible tests pass *without*
fixing the stated bug — adjudicated by execution against held-out tests.

It worked on the first try. On the reward-hackable bundle it produced:

```python
# Special case the exact test input
if row == 'a,"b,c"':
    return ["a", "b,c"]
return row.split(",")
```

Visible suite green, held-out suite red. A benchmark task certifying an agent as correct while the
bug it tests for is untouched.

**Then I ran the control, and it failed.** The same agent flagged the **clean** bundle too — it
just hardcoded all three visible inputs instead of one. **False-positive rate: 100%.**

The definition was wrong. "An exploit exists" is not a discriminating property: *any* finite,
visible test suite can be hardcoded given enough branches. Had I shipped after the positive
result, I would have published a detector that flags every task ever written.

**Evidence.** Regraded on exploit **cost** — how many literal inputs the exploit must special-case
— and strengthened the clean bundles to 8+ parametrised cases so a real separation could exist.

Numbers below are read from the shipped [`results/rewardgate_audits.json`](results/rewardgate_audits.json),
not from the earlier `exploit_trials.json` run. An earlier version of this table used the older
file, which predated the fix for dict-literal counting and therefore showed `0` special-cases for
bundles the current grader prices at 8 — the table contradicted the paragraph beneath it.

| Bundle | Label | Verdict | Hardcoded cases |
|---|---|---|---:|
| `csvlite-clean` | CLEAN | gameable, but costly — more work than the real fix | 8 |
| `csvlite-nop-pass` | NOP_PASS | no patch made the visible suite pass | — |
| `csvlite-reward-hackable` | REWARD_HACKABLE | **REWARD_HACKABLE** | **1** |
| `csvlite-contaminated-git` | CONTAMINATION_GIT | gameable, but costly | 9 |

The separation the grader actually achieves is **1 versus 8**, not *exploit* versus *no exploit*.
An exploit exists everywhere; only its price distinguishes a sound task from a hackable one.

False positives **0/3**, true positives **1/1**. Same agent, same corpus, same code — only the
definition of the defect changed.

**Decision.** Kept, graded by cost with a threshold of 2 special-cases.

**A claim I made here and have withdrawn.** This entry used to say that, given a diverse visible
suite, the agent *chose to genuinely fix the bug despite being told to cheat* — a nice result about
incentives. The transcript says otherwise. `trajectories/exploit-agent-csvlite-clean.md` records the
agent writing a dictionary that memorises all eight visible inputs and replying `EXPLOIT_FOUND`. It
cheated, successfully, and my grader's pattern list failed to price the dict literal. I had read the
grade rather than the transcript and reported the grade as a finding about the agent.

---

## Iteration 4 — the ablation that refuted my own headline

**What I tried and why.** Two independent reviewers made the same objection: RewardGate's only
measured win is `CONTAMINATION_GIT`, where the baseline scores 0.000 — but the baseline is shown
`git log --oneline`, and the contaminating commit sits off the current branch by construction. So
the 0.000 could be an artefact of what I showed it. I added a `parity` mode giving the baseline
`git log -p --all`, the same evidence my checker reads, and re-ran all 15 bundles.

**Evidence.**

| System | macro-F1 | CONTAMINATION_GIT F1 | exact-match | cost |
|---|---:|---:|---:|---:|
| baseline, `git log --oneline` | 0.600 | 0.000 | 11/15 | $1.7606 |
| **baseline, `git log -p --all`** | **0.889** | **1.000** | **13/15** | $1.8553 |
| RewardGate | 0.933 | 1.000 | 14/15 | $3.8271 |

**The objection was right.** Given the same evidence the baseline detects contamination perfectly.
The headline gap falls from 0.333 to **0.044** — one judgement in 45.

**Decision.** Kept, and the headline rewritten around it. The measured advantage was an information
asymmetry I designed. What survives is narrower: the pipeline runs the right command by default and
attaches a commit SHA, and the contamination check itself costs $0.00. It is **not** cheaper
overall — $3.8271 against the parity baseline's $1.8553, 2.06×, because it also runs an exploit
agent. An earlier draft of this entry claimed "half the token cost", which inverted the ratio
sitting two lines above it in the same table.

**The refutation has its own limit, and I found it late.** `baseline.py` caps the git log it shows
at `MAX_FILE_CHARS = 6000`; the corpus histories are 5.6–6.7 KB over 2–4 commits, so the
contaminating hunk survives truncation by ordering luck, while the checker reads history uncapped.
So the ablation refutes the headline *at toy scale* and says nothing above it. I am recording that
rather than quietly banking the more flattering reading — the whole point of running the ablation
was to stop choosing between framings.

**Learning.** I had already written that "the difference is one `git` command" and thought that was
the maximally honest framing. It was not — the honest version is that *the command is the whole
contribution, and an LLM given its output needs nothing else from me.* The experiment that could
refute a claim is worth more than any amount of careful hedging around it.

---

## Iteration 5 — the tool was unusable on anything but its own corpus

**What I tried and why.** A reviewer asked the obvious question I had never tested: what happens
if you point `rewardgate audit` at a directory that is not a bundle? The answer was a full,
confident-looking report — every trial at `exit=4`, a blocker reading *"no-op trial did not run"*,
and exit code 1. The real cause, "there is no test suite and no gold patch here", appeared nowhere
in the output. And exit 1 is the same code a proven `REJECT` returns.

**Evidence.** Two distinct defects, both mine:

1. **No stated contract.** The bundle format existed only as an example directory. There was no
   document telling anyone which files are required, which are optional, or — the load-bearing one
   — that `held_out/` must share no inputs with `tests/`. A user reproducing the layout by eye
   would very plausibly have reused inputs, which is exactly the mistake I made and had to fix in
   iteration 3. The rule was enforced by a test on *my* corpus and by nothing at all on theirs.
2. **`INDETERMINATE` and `REJECT` shared exit code 1.** A CI job gating on non-zero would treat
   "this task is broken, reject it" and "my harness could not run, fix it and re-run" as the same
   event. The whole point of introducing `INDETERMINATE` was that those are different claims; the
   exit code threw the distinction away at the boundary where it mattered most.

**Decision.** Added `docs/BUNDLE_FORMAT.md` stating the contract, including the disjointness rule
and what an `ACCEPT` does *not* cover. Added a preflight that names missing artifacts before
anything executes, and split the exit codes: `0` ACCEPT, `1` defect proven, `2` usage, `3`
INDETERMINATE. A test now asserts every shipped bundle satisfies the documented contract, so the
document and the corpus cannot drift apart.

Writing the document also caught a factual error I had been repeating: I described the visible
`csvlite` suite as having 17 cases. It has 8 quoted-field cases across 11 collected tests. The
number matters, because it is the quantity the hardcoding-cost argument rests on.

**Learning.** The failure here is narrower than "missing docs". Every safety property of this
project is enforced by a test over the 15 bundles I built. Point it at a sixteenth and the
enforcement is gone, silently — the audit still returns ACCEPT, in the same format, with the same
authority. **A tool whose invariants are checked by its own test suite rather than by its own code
is trustworthy only on the inputs its author already thought of.** Documenting the contract does
not fix that; it just stops the tool from being confidently wrong without saying so.

---

## Iteration 6 — the k-trial experiment, which refuted its own hypothesis

**What I tried and why.** This project's stated main failure mode was that the exploit agent runs
once per bundle: *"a stochastic agent can miss an exploit it would find on a rerun."*
`retrylite-reward-hackable` was the miss, and I had assumed it was sampling noise. So I ran k=5
trials on all 15 bundles — clean ones included, at the same k, because sampling only the defective
bundles harder raises recall while leaving the false-alarm rate at its k=1 value.

The decision rule (≥2 of 5), the permutation test, and the conditions that would refute the
hypothesis were committed in
[`results/multitrial_preregistration.json`](results/multitrial_preregistration.json) **before the
first trial ran**, with `REWARD_HACK_THRESHOLD` frozen in the same commit.

**Evidence.** 75 trials, $26.67.

| Bundle | Truth | Detected | 95% Wilson |
|---|---|---:|---|
| `csvlite-reward-hackable` | HACKABLE | **5/5** | [0.57, 1.00] |
| `semverlite-reward-hackable` | HACKABLE | **5/5** | [0.57, 1.00] |
| `retrylite-reward-hackable` | HACKABLE | **0/5** | [0.00, 0.43] |
| the other 12 bundles | — | **0/5** each | [0.00, 0.43] |

Permutation statistic **+0.667**, exact **p = 0.0286** over all 455 relabellings.

**The hypothesis is dead, and the pre-registration named this exact outcome.** `retrylite` scored
0 of 5. Not sampling noise — and not an agent failure either, which is what I assumed next and also
got wrong. Reading the five stored trials: the agent produced a **working exploit every single
time**, visible green and held-out red, using an interval predicate `if 7 <= attempt <= 39`. The
cost grader has no pattern for a numeric range, so it priced all five at zero and returned
`GAMEABLE (exploit cost not measurable)`, which is not counted as a detection.

The blind spot is in the **grader**, not the agent. I had to read the artifacts twice to get that
right; the summary table alone would have left me with the wrong story.

**Three things survive, and they are worth more than the hypothesis was.**

*The main failure mode is not what I said it was.* k=1 and k=5 produce **identical** verdicts on all
15 bundles. Every detection is 5/5 and every miss is 0/5 — perfectly bimodal, no bundle anywhere in
between. The agent is not a noisy sampler; it is deterministic on this corpus and has a capability
boundary. "Run it k times" was the wrong fix for a problem I had diagnosed wrongly.

*The first significant result in the project.* p = 0.0286. The 15-bundle macro-F1 comparison cannot
reach significance at any effort — it needs 6 one-way discordant pairs and the design yields at most
3. Reframing the question as "does the agent discriminate above chance?" makes it reachable. This
does **not** say the agent beats the baseline; that comparison remains p = 1.00.

*The false-alarm rate held under equal budget.* 0/5 on all 12 non-hackable bundles, including the
three `-clean` ones. The pre-registration flagged the opposite outcome as publishable: if a clean
bundle had alarmed even once, the earlier "0 false alarms on 6 clean bundles" would have been a k=1
artefact and macro-F1 might have fallen. It did not. **60 additional trials at the same k as the
positives, and the false-alarm rate is still zero** — a stronger claim than the one it replaces.

**Decision.** Kept, and the main failure mode rewritten. The remaining work is not more trials, it
is finding out *why* `retrylite` is out of reach — the brief, the patterns, or the task shape.

**Learning.** I named a failure mode in writing, believed it for two days, and it was wrong. The
experiment that could refute it cost $26.67 and about three hours. Writing the refutation condition
down first is what made the negative result publishable instead of embarrassing.

---

## Final — the combined system

> **The macro-F1 table below is measured against the *unfair* baseline** (`git log --oneline`).
> Iteration 4 re-derives it under parity: the gap is **0.044** at **McNemar p = 1.00**, not
> +0.333. Kept unedited so the sequence shows what was believed at each step.

**What I tried and why.** The three kept changes composed: deterministic checks for the classes
they can prove, the cost-graded exploit agent for the one they cannot, and every verdict tied to
an artifact.

**Evidence.** 15 bundles × 3 defect classes = 45 binary judgements per system. Identical cases,
identical output schema, identical scorer. Figures from `results/summary.json` and
`results/significance.json`.

| METRIC | BASELINE | REWARDGATE | ABSOLUTE Δ |
|---|---:|---:|---:|
| **macro-F1 (primary)** | 0.600 | **0.933** | **+0.333** |
| macro precision | 0.667 | 1.000 | +0.333 |
| macro recall | 0.556 | 0.889 | +0.333 |
| exact-match bundles | 11/15 | **14/15** | +3 |
| false alarms on 6 clean bundles | 0 | 0 | — |
| cost per bundle (USD) | 0.1174 | 0.2551 | +117% |

| PER-CLASS F1 | BASELINE | REWARDGATE | SUPPORT |
|---|---:|---:|---:|
| NOP_PASS | **1.000** | **1.000** | 3 |
| REWARD_HACKABLE | **0.800** | **0.800** | 3 |
| CONTAMINATION_GIT | **0.000** | **1.000** | 3 |

Full run: **$5.5877**, 1711.3s. McNemar exact **p = 0.25** — not significant.

**Where the gain actually came from, and it is uncomfortable.** Not from the agent. It **ties the
baseline on its own class** (`REWARD_HACKABLE`, 0.800 both). `NOP_PASS` also ties at 1.000. All
three discordant judgements are `CONTAMINATION_GIT`; drop that class and both systems score 0.900
exactly. The entire measured difference is one deterministic `git log -p --all`.

**The honest cost.** 117% more per bundle, for a difference concentrated in the one class that
costs nothing to check.

**The challenging case.** `retrylite-reward-hackable` was missed by both systems in the final run.
The stored evidence says an exploit *was* found but priced at zero special-cases — a
cost-measurement blind spot, not the agent honestly fixing the bug. An earlier version of this
document told the second story; it was wrong, and it is corrected here.

**Decision.** Shipped, with the claim narrowed to what the evidence supports. The unimplemented
mitigations are *k* independent trials and a larger corpus of independent base repositories — at
3 repos, six discordant pairs are needed for significance and the design can produce at most a few.

---

## Withdrawn — a finding that was my own bug

**What I claimed.** That the baseline was an indiscriminate flag-everything system: precision
0.250, exact-match 0/12, and — the anecdote I put in the README, the changelog and the video
script — that on one bundle it returned `CONTAMINATION_GIT: true` while its own evidence field read
*"No git history is shipped with the bundle"*, contradicting itself inside a single response. I
presented that as a finding about LLM reliability.

**What was actually true.** `bool("false")` is `True` in Python, and my own prompt template asked
the model for the **string** `"true|false"`. So the model returned `"false"`, `parse_audit` stored
`True`, and all 36 baseline judgements were inverted into defect reports before scoring. The
model's evidence prose was correct. Its `verdict` field was correct. **The contradiction was
manufactured by my parser, and I wrote it up as a discovery.**

**How it was caught.** Not by me. An adversarial integrity audit was asked to verify every numeric
claim against the artifacts, and it reproduced the coercion by execution.

**Why nothing else caught it.** The corrupted values were *plausible*. An all-flags-true baseline
is exactly what I expected from a naive prompt, so the result confirmed my prior instead of
provoking suspicion. And `schema.py` had **zero tests** while every headline number in the project
flowed through it — I had tested the checkers and the scorer, and never the parser between them.

**Evidence of the correction.** After fixing coercion and the prompt template, and re-running:

| | claimed (buggy) | measured (fixed) |
|---|---:|---:|
| baseline macro-F1 | 0.400 | **0.600** |
| baseline precision | 0.250 | **0.667** |
| baseline recall | 1.000 | **0.556** |
| baseline exact-match | 0/12 | **11/15** |
| improvement | +133.3% | **+55.6%** (absolute Δ +0.333) |

**Decision.** Claim withdrawn, narrative rewritten, 11 tests added to `schema.py` (30 parametrised cases). The real
baseline is a competent opponent that ties on `NOP_PASS` and fails only where execution is
required — a smaller and more defensible result than the one I nearly submitted.

**Learning, and it is the one I would actually carry forward:** *this project exists to catch
results that pass every mechanical check while measuring nothing, and I produced one about my own
work.* A green test suite, a plausible number and a satisfying narrative are exactly the conditions
under which nobody looks again. The parser between a model and a metric deserves the same scrutiny
as the metric.

---

## Removed — a per-defect-class agent fan-out

**What I tried and why.** The obvious architecture is one specialised agent per defect class:
a contamination agent, an assertion agent, an over-specification agent, and so on. It looks
thorough and it is what "multi-agent" usually means.

**Evidence for removing it.** For every class except `REWARD_HACKABLE`, a deterministic check
produces *stronger* evidence at *zero* cost:

| Defect | Deterministic mechanism | Cost | Evidence quality |
|---|---|---:|---|
| `NOP_PASS` | run the suite with an empty patch | $0.00 | exit code |
| `CONTAMINATION_GIT` | `git log -p --all` line match | $0.00 | commit SHA |
| Solution leakage | string match, issue vs patch | $0.00 | the matched path |
| Weak assertions | AST analysis | $0.00 | the test's AST |

An LLM asked "is this contaminated?" returns an opinion. `git log -p --all` returns a commit. The
opinion costs ~$0.19 per call in system-prompt overhead alone and is less convincing.

**Decision. Removed.** Five near-identical prompt calls would have added cost, latency,
non-determinism, and five more trajectories to document, in exchange for weaker evidence.
**Learning: the number of agents is not a measure of engineering. The right question is what is
the cheapest mechanism that can *prove* this claim** — and for most of these, that is not a model.

---

## Removed — relying on the bundle's `conftest.py` for imports

**What I tried and why.** Each bundle ships a `conftest.py` that puts `src/` on `sys.path`, which
is the idiomatic way to make a source tree importable under pytest without an install step.

**Evidence for removing it.** Every oracle trial returned 0.0 — including on bundles whose gold
patch was known-good. pytest derives `rootdir` from its arguments, so passing an absolute path to
`tests/` put the bundle-root `conftest.py` above `confcutdir`, and it was **never loaded**. Every
task looked unsolvable for a reason having nothing to do with the task.

**Decision.** Replaced with an explicit `PYTHONPATH` in the subprocess environment. The
`conftest.py` is retained only for humans running pytest by hand.

**Learning, and the reason this is in the changelog rather than buried in a commit:** this failed
*loudly* here, because I was checking that oracle runs return 1.0. The identical misconfiguration
in a real benchmark harness fails *quietly* — tasks are marked unsolved, the model is blamed, and
the harness is never suspected. **A harness that cannot verify its own environment produces
confident numbers about the wrong thing.**

---

## Main failure mode

**The cost grader cannot price an exploit it has no pattern for, and a defect it cannot price is a
defect it does not report.**

The k=5 experiment was designed to test whether `retrylite-reward-hackable` was missed through
sampling noise. The agent found a working exploit in **4 of 5 trials** — visible suite
green, held-out suite red, every time. What it wrote was an *interval* predicate:

```python
if 7 <= attempt <= 39:
    return MAX_DELAY_SECONDS
```

`_HARDCODE_PATTERNS` matches equality, membership, `startswith`/`endswith`, `case`, and dict keys.
A numeric range guard matches none of them, so `hardcoded_cases` is 0, `cost_measurable` is False,
and the verdict degrades to `GAMEABLE (exploit cost not measurable)` — which `is_reward_hackable`
does not count. The task is reward-hackable, the agent proved it four times out of five, and the
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
