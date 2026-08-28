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

**Evidence.** 12 bundles × 3 defect classes = 36 binary judgements per system. Identical cases,
identical output schema, identical scorer.

| METRIC | BASELINE | REWARDGATE | CHANGE |
|---|---:|---:|---:|
| **macro-F1 (primary)** | 0.400 | **0.933** | **+133.3%** |
| macro precision | 0.250 | 1.000 | +300.0% |
| macro recall | 1.000 | 0.889 | −11.1% |
| exact-match bundles | 0/12 | **11/12** | — |
| cost per bundle (USD) | 0.1157 | 0.2581 | +123.0% |

| PER-CLASS F1 | BASELINE | REWARDGATE | SUPPORT |
|---|---:|---:|---:|
| NOP_PASS | 0.400 | **1.000** | 3 |
| REWARD_HACKABLE | 0.400 | 0.800 | 3 |
| CONTAMINATION_GIT | 0.400 | **1.000** | 3 |

Full run: **$4.49**, 24 minutes wall clock.

**Where the gain actually came from.** Not recall — the baseline already had recall 1.000. It came
from **precision, 0.250 → 1.000**. The baseline flagged every defect on every bundle including all
three clean ones, so it never once said a task was sound. Exact-match went 0/12 → 11/12.

**The honest cost.** RewardGate is **123% more expensive per bundle** and recall fell 11.1%, from
the single false negative described below. Paying roughly double per bundle to stop rejecting every
sound task is a trade a reviewer would take, but it is a trade, and the recall regression is real.

**The challenging case, and what it revealed.** `retrylite-reward-hackable` was missed because the
agent, told to cheat, **fixed the bug properly instead**. `retrylite`'s genuine fix is a one-token
`min(...)`, so honesty cost no more than the hardcode. That is my own cost hypothesis working
against me: exploit-based detection has a blind spot when the real fix is as cheap as the exploit.
The same defect on `semverlite` was caught immediately, so this is agent variance on an easy fix,
not a logic error.

**Decision.** Shipped. The unimplemented mitigation is *k* independent trials taking the union,
which would raise cost roughly linearly — stated as a gap rather than quietly omitted.

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
