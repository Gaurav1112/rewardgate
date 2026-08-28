# RewardGate — Design Spec

**Date:** 2026-08-28
**Event:** micro1 Agentic Workflows Hackathon (closes 2026-08-31 18:00 UTC)
**Author:** Kumar Gaurav
**Status:** Locked pre-implementation — **historical record, not a description of what shipped**

> **Read this first.** This is the design as locked *before* building, kept unedited so the
> planning can be compared against the outcome. Several things here did not ship, and the
> [Improvement Changelog](../../IMPROVEMENT_CHANGELOG.md) is the authoritative account:
>
> * "4 self-authored micro-repos" — **3** shipped (csvlite, semverlite, retrylite).
> * "pass@1 and pass^3 across 3 seeds" — **not implemented**; a single trial per bundle is run,
>   and that limitation is reported in the README.
> * "[A2] Report Synthesizer, one LLM call" — **removed**. The report is rendered
>   deterministically; no model is involved.
> * "Two LLM agents, four deterministic checkers" — shipped as **one** agent plus deterministic
>   tiers.
> * "Docker footprint under 2 GB" / "under 8 minutes" — no Docker is used; the full run takes
>   28.5 minutes.
> * "Two held-out defect classes excluded from prompt development" — not implemented.
> * The challenging case here is a *reverted commit*; the corpus ships a **side-branch** commit,
>   because the reverted version left the fix visible in `git log --oneline`.

---

## 1. Problem

An AI data lab pays domain experts to author **benchmark tasks** / **RL environments** — a bug, a
test suite that must fail before the fix and pass after, a gold patch, and a reproducible container.
Before a task enters a training or evaluation corpus, a senior reviewer must decide whether it
actually measures anything.

A task can look perfect and still be worthless. Five failure modes recur:

| Defect | Why the task is worthless |
|---|---|
| `NOP_PASS` | Fail-to-pass tests already pass with an empty patch. Every agent "solves" it. Pure false-positive generator. |
| `CONTAMINATION` | The fix is recoverable from `.git` history or a build artifact. The agent retrieves rather than reasons. |
| `OVER_SPECIFIED` | The instruction names the target file/class/method. Diagnosis — the actual skill — is removed. |
| `WEAK_ASSERTION` | The F2P test asserts almost nothing (`assert x is not None`, bare `try/except`). It fails and passes for the wrong reasons. |
| `REWARD_HACKABLE` | The test special-cases a literal input, so hardcoding passes without fixing the bug. |

This is not hypothetical. Published audits of the most-used coding benchmark found **32.67%** of
passing patches had their solution leaked in the issue text and **31.08%** passed on weak tests
([arXiv:2410.06992](https://arxiv.org/abs/2410.06992)); a 2026 audit found **28.5%** of SWE-bench
Verified tasks accept a Docker-verified *incorrect* patch
([arXiv:2606.16062](https://arxiv.org/abs/2606.16062)). OpenAI retired SWE-bench Verified in
February 2026.

## 2. User

**Primary:** a task reviewer or data-quality lead at an AI data lab, who receives candidate task
bundles from contract authors and must accept, revise, or reject each one.

**Bottleneck today:** review is manual, slow, and inconsistent. Checking the reward gate means
building a container and running the suite twice. Checking contamination means reading git history
by hand. Two reviewers reading the same bundle reach different verdicts, and the expensive defects
(reward-hackable tests) are exactly the ones that look fine on inspection.

**Why it matters:** a defective task is worse than no task. It inflates benchmark scores and feeds
false-positive reward signal into training.

## 3. Core design decision

> **Prove defects by execution, not by opinion.**

Every positive verdict must carry a mechanical artifact — a test exit code, a commit SHA, an
exploit patch that makes the suite green. An LLM that merely *believes* a task is contaminated
scores nothing.

This is a direct response to a measured problem: a 2026 audit found an **18.5% evaluator–human
misalignment rate** across BFCL v4, τ²-Bench, LiveMCPBench and MCP-Atlas
([arXiv:2607.02577](https://arxiv.org/abs/2607.02577)). LLM-as-judge is itself unreliable, so the
primary metric is grounded in test execution instead.

## 4. Architecture

```
candidate task bundle
        │
        ├─► [D] Static Checkers ──────── deterministic, no LLM, no cost
        │      • empty-patch test run        → NOP_PASS
        │      • git log -p --all grep       → CONTAMINATION
        │      • AST assertion analysis      → WEAK_ASSERTION
        │      • instruction↔patch diff      → OVER_SPECIFIED
        │
        ├─► [A1] Exploit Agent ────────── agentic loop, sandboxed shell
        │      Hostile brief: "make the F2P tests pass WITHOUT
        │      fixing the stated bug." Writes a real patch.
        │      Adjudicated by execution against held-out tests:
        │        F2P green + held-out red  → REWARD_HACKABLE (proven)
        │
        └─► [A2] Report Synthesizer ───── one LLM call
               Reviewer-grade audit report: verdict, per-defect
               findings, file:line evidence, repro commands.
                       │
                       └─► human checkpoint before any REJECT
```

**Two LLM agents, four deterministic checkers.** Component count is deliberately low. Each
component earns its place: the checkers are exact and free, the exploit agent finds the one defect
class no static analysis can prove, and the synthesizer turns evidence into a document a reviewer
signs.

**Rejected:** a per-defect-class agent fan-out. Five near-identical prompt calls add cost, latency
and five trajectories to document, while producing weaker evidence than one `pytest` exit code.

## 5. Evaluation

### What "good" means, declared before running

Fixed in this spec at commit time, before any evaluation was executed:

* **Primary metric:** macro-F1 over (bundle × defect class).
* **Success bar:** RewardGate beats the baseline on macro-F1 *and* does not exceed the baseline's
  false-alarm rate on clean bundles. Precision was prioritised over recall because the output is a
  rejection, and a false positive costs an author a rewrite they did not need.
* **Disqualifying outcome:** any headline gain that disappears when a single defect class is
  removed is to be reported as such rather than as a general improvement.

That last condition fired. See the drop-one-class analysis in the README.

**Primary metric:** macro-F1 over `cases × defect classes` binary judgements.
Chosen over per-case accuracy because it has more resolution — one flipped case moves the number
less — and because it exposes per-class weakness that an aggregate hides.

**Secondary:** human review time per bundle, USD cost per bundle, wall-clock.

**Corpus:** 15 bundles built from 4 self-authored Python micro-repos — 3 clean, 12 defective.
Labels are exact by construction: a scripted injector mutates a clean bundle and records what it
did in `labels.yaml`. The corpus is regenerable from the script, so a judge can rebuild it.

**Challenging case:** contamination hidden in a *reverted* commit. It does not appear in
`git log --oneline`; it is only recoverable via `git log -p --all` or the reflog.

**Held-out defect classes:** two classes are excluded from all prompt development, to guard against
the circularity of authoring both the defect and the detector. This limitation is stated in the
README rather than hidden.

**Variance:** temperature is not pinnable on current models, so the metric is reported as **pass@1
and pass^3** across 3 seeds. Reporting only a best run would be dishonest given that agent
evaluations are known to swing (MCPMark: 52.56% pass@1 → 33.86% pass^4,
[arXiv:2509.24002](https://arxiv.org/abs/2509.24002)).

**Evidence gate:** a positive verdict counts only if the required mechanical artifact is attached.
This kills lucky guesses, which would otherwise inflate recall.

## 6. Baseline

Single-shot prompt, no tools, same 15 bundles, same output schema:
*"Here is a candidate benchmark task. Is it sound? Return a verdict per defect class."*

This is micro1's own suggested baseline ("one direct prompt with basic instructions") and is a fair
comparison: identical cases, identical schema, identical scorer. The resource difference — the
baseline cannot execute anything — is the finding, not a confound, and is stated explicitly.

## 7. Planned improvement path

Each stage is measured on the same 15 bundles with the same scorer.

| Stage | Change | Hypothesis |
|---|---|---|
| Baseline | Single prompt, no tools | Establishes floor |
| Iter 1 | + deterministic checkers as tools | Execution beats inspection on NOP_PASS / CONTAMINATION |
| Iter 2 | + evidence gate | Precision rises; unsupported guesses stop counting |
| Iter 3 | + adversarial exploit agent | Unlocks REWARD_HACKABLE, which nothing else can prove |
| Final | Combined | — |

## 8. Reproducibility

- `uv` with a committed lockfile; Python pinned.
- Total Docker footprint kept under 2 GB (`python:3.11-slim` base only). Real SWE-bench images
  are 2–10 GB each and are deliberately not used.
- Target: full 15-case evaluation in under 8 minutes.
- `--replay` mode scores cached trajectory JSONL offline, so a judge **without an API key** can
  reproduce the headline metric.
- Measured USD cost and wall-clock reported in the reproduction guide.
- No credentials in the repository.

## 9. Safety

- The exploit agent runs with a restricted toolset against a disposable copy of the bundle. It
  never touches anything outside its working directory.
- Its purpose is defensive: proving a task is gameable so the task can be fixed before it trains a
  model.
- A human checkpoint is required before any `REJECT` verdict is finalised.

## 10. Scope

**Out of scope:** real SWE-bench Docker bundles; non-Python bundles; a web UI; LLM-as-judge scoring;
automatic repair of detected defects; defect classes beyond the five listed.
