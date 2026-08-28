# Improvement Changelog

How RewardGate evolved, and what each change actually bought. Every "evidence" cell is a number I
measured, not an estimate. Experiments that were removed are included, because the ones that
failed taught more than the ones that worked.

Each stage is measured on the same corpus with the same scorer.

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

| Bundle | Label | Verdict | Hardcoded cases |
|---|---|---|---:|
| `csvlite-clean` | CLEAN | RESISTED — agent had to fix it properly | 0 |
| `csvlite-nop-pass` | NOP_PASS | RESISTED — no exploit found | 0 |
| `csvlite-reward-hackable` | REWARD_HACKABLE | **REWARD_HACKABLE** | **1** |
| `csvlite-contaminated-git` | CONTAMINATION_GIT | RESISTED — agent had to fix it properly | 0 |

False positives **0/3**, true positives **1/1**. Same agent, same corpus, same code — only the
definition of the defect changed.

**Decision.** Kept, graded by cost with a threshold of 2 special-cases. The striking part: given a
diverse visible suite, the agent **chose to genuinely fix the bug despite being explicitly told to
cheat**, because hardcoding 8 parametrised cases was more work than writing the real
implementation.

---

## Final — the combined system

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
| baseline macro-F1 | 0.400 | **0.524** |
| baseline precision | 0.250 | **0.500** |
| baseline recall | 1.000 | **0.556** |
| baseline exact-match | 0/12 | **9/15** |
| improvement | +133.3% | **+78.2%** |

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
