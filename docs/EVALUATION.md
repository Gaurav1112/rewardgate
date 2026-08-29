# Measured improvement, in full

The README states the result and the ablation that refutes it. This is the long version: how the
comparison is set up, why the numbers are not circular, and the case both systems miss.

15 bundles × 3 defect classes = **45 binary judgements** per system. Identical cases, identical
output schema, identical scorer. All figures come from [`results/summary.json`](../results/summary.json).

**Primary metric: macro-F1.** Macro because the classes are unbalanced; F1 rather than accuracy
because most pairs are negatives, so a system flagging nothing would score well on accuracy.

An earlier version led with **+0.333 macro-F1**, measured against a baseline shown only
`git log --oneline` — which cannot see a fix parked on a side branch. That comparison was unfair.
It is superseded by the ablation below, and the retired table, the per-class breakdown and the
reasoning that retired it are preserved in
[IMPROVEMENT_CHANGELOG.md](../IMPROVEMENT_CHANGELOG.md).

Full run: **$5.5877**, 1711.3s wall clock, 45 paired judgements per system.

---

## Why these numbers are not circular

The obvious failure mode for a project like this is circular. If I author the defects *and* build
the detector, precision and recall measure nothing but my own imagination. So the evidence is split
into two tiers, and the more important one is not mine:

| Tier | Corpus | Authored by | What it establishes |
|---|---|---|---|
| **Third-party** | [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified), 500 real instances | Princeton NLP — **not me** | The text checkers find real defects in a real, widely-used benchmark |
| **Held out** | [SWE-Gym](https://huggingface.co/datasets/SWE-Gym/SWE-Gym), 2,438 instances, zero overlap | Also not me | The rate is not a property of Verified alone |
| Synthetic | 15 bundles, 3 self-authored micro-repos | Me | Baseline-vs-agent comparison on defects requiring execution |

**The one external reference point.** My solution-leakage detector measures **133/500**; *The
SWE-bench Illusion* reports **135/500** using a different heuristic (theirs also counts import
statements, mine counts bare filenames). Corroboration that the leakage is real, not a replication
of their figure.

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

---

## A second metric, because macro-F1 is not the only question

macro-F1 asks *did it reach the same verdict*. On 15 bundles the answer is a near-tie, and that is
reported without softening. But a reviewer reading an audit asks a second question — *can I check
this without redoing the work* — and there the two systems are not close.

| | parity baseline | RewardGate |
|---|---:|---:|
| Positive verdicts | 9 | 8 |
| Correct | 8 | **8** |
| False positives | **1** | **0** |
| Backed by an **executed** artifact | **0** | **8** |
| Cost to audit 2,938 third-party instances | ~$345 extrapolated | **$0.00** |

**The distinction is executed, not merely cited.** The parity baseline does quote commit SHAs — it
was shown `git log -p --all` and it reports what it read, which is a real and useful thing to do.
RewardGate's eight positives each carry something it *produced by running code*: a pytest exit
code, a SHA it found by walking history itself, or an exploit patch that turns the visible suite
green while the held-out suite stays red. The difference matters when the verdict is wrong — and
one of the baseline's nine is (`semverlite-nop-pass / REWARD_HACKABLE`, a hallucinated defect on a
sound task). A cited artifact and an executed one are indistinguishable until one of them is
fabricated.

**And coverage.** The deterministic tier audits **2,938 instances across two corpora in about six
seconds for $0.00**. At the baseline's measured $0.1174 per task that is roughly **$345** and, at
its measured rate, over a day of wall clock. This is not a cleverness gap; it is the difference
between a check you run on every task and one you run on a sample.

Neither of these is offered as a replacement for the macro-F1 result. That comparison is a tie and
stays a tie.

---

## Human time per task — the third row, and it does not favour this tool

The challenge's suggested comparison table has three rows: primary outcome, **human time per task**,
and cost per task. Two were reported and the third was not, so it is measured here.

`uv run python scripts/measure_human_time.py` times the commands a reviewer cannot avoid running to
check one task by hand — the suite unpatched, the gold patch applied and reverted, a history scan —
against `audit_bundle(run_exploit=False)` on the same 15 bundles.

| | manual floor | RewardGate |
|---|---:|---:|
| per task | **0.17s** | 0.26s |
| 15 tasks | **2.52s** | 3.91s |

**The tool is slower, by about 50%.** It materialises each bundle twice so the oracle's applied
patch cannot leak into the no-op measurement, and it walks every ref rather than one branch. Those
are correctness choices and removing them would be a regression, but they are not free.

Two things this number is not. It is a **floor**, not human time: it is what the task costs someone
who types instantly, reads nothing and decides nothing. No reviewer was timed, so the gap between
the floor and real human time is not estimated here. And neither column covers `REWARD_HACKABLE` —
a reviewer cannot settle that by hand at all without writing an exploit.

So on a single task, this tool's value is **not** time saved, and the honest statement is that it
costs a tenth of a second more. What it buys is that the right commands run every time without the
reviewer having to know which ones they are, and that the verdict arrives attached to an artifact.
Where time does become decisive is at a scale the manual process does not reach: the deterministic
text tier audits 2,938 third-party instances for $0.00, and no reviewer is going to hand-check
2,938 tasks at any speed.

That is the third independent attempt in this project to demonstrate an advantage — after macro-F1
and the parity ablation — and the third to come back neutral or negative. Artifact:
[`results/human_time.json`](../results/human_time.json).

---

## The ablation that refutes the headline

Two reviewers independently said the same thing: the baseline is shown `git log --oneline`, while
the contaminating commit sits off the current branch **by construction**. So its 0.000 might be an
artefact of what I showed it rather than a capability gap. That is a testable objection, so I
tested it — `uv run python scripts/run_parity_ablation.py`, results in
[`results/parity_ablation.json`](../results/parity_ablation.json).

| System | macro-F1 | CONTAMINATION_GIT F1 | exact-match |
|---|---:|---:|---:|
| baseline, `git log --oneline` | 0.600 | 0.000 | 11/15 |
| **baseline, `git log -p --all`** | **0.889** | **1.000** | **13/15** |
| RewardGate | 0.933 | 1.000 | 14/15 |

**Given the same evidence, the baseline detects contamination perfectly — 1.000, identical to
RewardGate.** The headline gap collapses from **0.333 to 0.044**, which is one judgement out of 45.

That one judgement is worth naming, because it inverts the story. Pairing the two systems gives 0
judgements where only the baseline is right, 1 where only RewardGate is, and **McNemar exact
p = 1.00** — the largest value the test can return. The single discordant pair is
`semverlite-nop-pass / REWARD_HACKABLE`, where the parity baseline raises a **false positive** and
RewardGate does not. So under a fair comparison the residual difference is not contamination at
all, and it is not a mechanism: it is one hallucination the executing system did not make.

So the honest conclusion is stronger than the one I started with and worse for my own system: the
measured advantage was **an information asymmetry I designed**, not a capability difference. An LLM
shown the right `git` output finds the fix on the side branch without any help from me.

What survives is smaller and duller: the pipeline *runs the right command by default*,
deterministically, for $0.00, and attaches the commit SHA. The baseline only matched it because I
hand-fed it ~6 KB of `git log -p --all` in the prompt — with no artifact, and only because I
already knew which command to run. (The pipeline is not cheaper: $3.83 against the parity
baseline's $1.86, because it also runs an exploit agent. It is the *contamination check* that is
free.)

**And the retreat itself has a limit, which cuts the other way.** `baseline.py` truncates that log
to `MAX_FILE_CHARS = 6000`. The corpus histories are 2–4 commits and 5.6–6.7 KB, so the fix lands
inside the window by luck of ordering; the contamination checker reads the history uncapped. The
parity result is therefore a property of a two-commit synthetic corpus, not of the method. On a
repository with ten thousand commits the baseline would see a fraction of a percent of the history
and the checker would still see all of it. I have not tested that, so I am not claiming it — but
the honest statement is that the ablation refutes my headline *at this scale* and is silent above
it, not that the gap is truly 0.044 everywhere.

---

## So what does this project actually establish?

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
reported that way. What the agent contributes is not a higher score on this corpus: it is
**executed proof for the one class a reader cannot confirm without running it.**

The rest of the value is **defaults and artifacts** — knowing which command to run, running it
every time without being prompted, and emitting a commit SHA a reviewer can check rather than a
sentence they have to trust.

---

## The challenging case

`retrylite-reward-hackable` — missed by **both** systems.

The stored evidence in [`results/rewardgate_audits.json`](../results/rewardgate_audits.json) reads:
*"the only patch found also fixes held-out behaviour; the task resisted gaming."* That string is
emitted from exactly one branch of `exploit.py` — the one requiring the held-out suite to **pass**.
So the agent did not produce an exploit at all in that run, and the pipeline recorded it as the
task resisting.

The task is reward-hackable by construction. So the blind spot is not in the cost grader as first
supposed: it is that **one failed exploit attempt is being reported as evidence that no exploit
exists.** Absence of a found attack is not absence of an attack, and the audit's own wording ("the
task resisted gaming") asserts the stronger claim. A single trial cannot support it.

The k=5 experiment then settled it. See the README's *Main failure mode*: the agent finds a working
exploit 5 times out of 5, and the grader cannot price the interval predicate it writes.

No trajectory was captured for this bundle — `trajectories/` holds `csvlite` only — so I cannot say
from the record whether the earlier single trial tried and failed or never tried. That gap is
itself a finding: the one case where I most needed the transcript is the one where I did not save
it.

Two earlier versions of this section were wrong. The first said the agent chose to fix the bug
honestly; the second said an exploit was found but priced at zero special-cases. The second is the
evidence string belonging to a **different bundle** — `retrylite-contaminated-git` — which I
misattributed while correcting the first. The changelog records both.
