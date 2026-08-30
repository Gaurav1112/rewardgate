# Submission — RewardGate

**Entrant:** Kumar Gaurav · kgauravis016@gmail.com
**Repository:** https://github.com/Gaurav1112/rewardgate
**Coding agents used:** Claude Code (Claude Opus 5) for implementation. The Claude Code CLI in
headless mode is also the adversarial exploit agent *inside* the product.

---

## One paragraph

RewardGate audits a candidate benchmark task before it enters a model-training corpus, and proves
defects by execution rather than by opinion. Pointed at SWE-bench Verified it finds that **210 of
500 instances (42.0%) carry at least one defect**, deterministically, for **$0.00** — and one of
its four checkers lands close to an independently published figure: 133/500 against the 135/500
reported by *The SWE-bench Illusion* ([arXiv:2506.12286](https://arxiv.org/abs/2506.12286)) on a
corpus the author did not build. The two heuristics are not identical — theirs also counts import
statements, mine counts bare filenames — so this is corroboration that the leakage is real and
roughly this common, not a reproduction of their number. Every
positive verdict carries a mechanical artifact: a test exit code, a commit SHA, or an exploit patch
that turns the visible suite green while the bug the task tests for is untouched.

**Requirement-by-requirement mapping:** [REQUIREMENTS.md](REQUIREMENTS.md) — every stated rule
and deliverable against where it is met, with the declared gaps in one place.

## The four deliverables

| # | Item | Where |
|---|---|---|
| 1 | Solution code + Improvement Changelog | the repository; [`IMPROVEMENT_CHANGELOG.md`](IMPROVEMENT_CHANGELOG.md) |
| 2 | Reproduction guide | [`REPRODUCTION.md`](REPRODUCTION.md) — free path, no API key. Complete unedited terminal output for all eleven commands: [`docs/TERMINAL_SESSION.md`](docs/TERMINAL_SESSION.md) |
| 3 | Solution video (≤5 min) | [`rewardgate-demo.mp4`](rewardgate-demo.mp4), 4:46 — script in [`docs/VIDEO_SCRIPT.md`](docs/VIDEO_SCRIPT.md). **The voice is macOS `say`, not a person** — see the note below |
| 4 | Agent trajectories | [`AGENT_TRAJECTORIES.md`](AGENT_TRAJECTORIES.md) and [`trajectories/`](trajectories/) |

### One thing to say before you watch the video

The narration is synthetic — macOS `say`, the `Daniel` voice. You would notice within ten seconds,
so it is better said here.

It covers the voice and nothing else. The script is `docs/VIDEO_SCRIPT.md`, written and read
verbatim. Every frame on screen is output this repository actually produced: `scripts/video/cap/`
holds the captured `stdout` of the real commands and the slides are rendered from those files, so
no number in the video was retyped into a mockup. `scripts/video/build.py` renders it and
`scripts/video/README.md` documents what is and is not generated, including the one transcribed
slide.

A human reading is a better artifact and the tooling for it ships (`record_narration.py` replaces
the twelve clips; `compose.py` re-times the slides to the new pacing). Not doing it before the
deadline was a decision, not an oversight, and this is the trade being made rather than hidden.

## Baseline and advanced solution

**Baseline** (`rewardgate/baseline.py`): one direct prompt, no tools. **Advanced**
(`rewardgate/auditor.py`): two deterministic checkers plus one adversarial agent. Same bundles,
same schema, same scorer. Full comparison and the honest limits are in the README section
["Baseline solution and advanced solution"](README.md#baseline-solution-and-advanced-solution).

## Verify the main result in three commands

```bash
git clone https://github.com/Gaurav1112/rewardgate && cd rewardgate
uv sync && ./scripts/fetch_real_corpus.sh
uv run python -m rewardgate.report_real     # 210/500 (42.0%), $0.00, ~1s
```

Then, if you want the whole thing: `uv run pytest -q` (0 failed) and
`uv run python scripts/run_parity_ablation.py --replay` (the ablation that refuted my own
headline — free, under a second).

## What I would want a judge to check first

1. **Is the 42% real?** Run `report_real`. It is deterministic and third-party; nothing about it
   depends on my synthetic corpus or on trusting me.
2. **Did I grade my own homework?** The synthetic tier is mine and says so. The
   [circularity section](docs/EVALUATION.md#why-these-numbers-are-not-circular) states exactly what the
   third-party anchor does and does not establish.
3. **Is the improvement claim honest?** I ran the ablation that could refute it, and it did: the
   gap against a *fair* baseline is 0.044 at McNemar p = 1.00, not the 0.333 I first measured. Both
   numbers, and why the first was wrong, are in the changelog.

## The code freeze, and why it was lifted

Code was frozen after the fifth adversarial review round, because the measured regression rate on
this repository's security-hardening edits was roughly one in two: two round-4 exploits defeated
round-3 fixes, and four round-5 exploits defeated round-4 fixes. An unverified late fix is worse
than a disclosed bug.

It was then **deliberately and narrowly unfrozen**. That regression rate was measured at 3am under
time pressure; with days remaining and a full suite it is a different bet, and every fix below landed
with a regression test that **reproduces the defect against the pre-fix code** before pinning it.
Four of the five disclosed defects are now fixed. The one left is left on purpose, and the reason
is given.

## Known limitations, stated up front

- **The cost grader cannot price an exploit it has no pattern for.** Measured at k=5 on all 15
  bundles (pre-registered, $26.67): 2 of 3 reward-hackable bundles detect 5/5, the third detects
  0/5, and all 12 others detect 0/5 — every *detection* rate is exactly 0.0 or 1.0. Exploit
  *generation* is not bimodal at all: 9 of the 15 bundles are mixed, and the grader collapses that
  variance to zero. An earlier version of this line read "perfectly bimodal — the agent is
  deterministic, not noisy", which measured the grader and credited the agent. On
  the miss the agent *did* produce a working exploit 4 times out of 5; it wrote the interval
  predicate `if 7 <= attempt <= 39:`, which matches none of `_HARDCODE_PATTERNS`, so the cost came
  back 0 and the verdict degraded to "cost not measurable". It is a **detector-expressiveness**
  limit, not a capability boundary — an earlier version of this line said the cause was unknown.
  Exploit cost is still priced by regex; a semantic measure is not implemented.
- **The semantic cost measure was built and refuted.** Iteration 8 priced exploits with a model
  where the regex could not: 32 of 33 previously unpriceable exploits priced, and the documented
  miss closed (`retrylite` 3/5 against the frozen 0/5). It also raised **16 false alarms on 60
  clean trials**, against the frozen metric's zero, which failed the condition committed in
  `results/semantic_cost_preregistration.json` before the run. It is therefore **not shipped as the
  default** and the frozen metric is untouched. The reason it fails argues for the architecture:
  on the `retrylite` family the honest fix and the cheap exploit both encode one threshold, so cost
  cannot separate them and only held-out execution can.
- **The agent session runs on the host.** `--docker` now contains every *test execution* — the
  no-op trial, the oracle trial and the adjudication — in a container with `--network none`, no
  host path mounted, non-root, capabilities dropped, and it is measured both ways rather than
  asserted (`scripts/prove_containment.py`; network `reachable` → `blocked`, host write `written`
  → `blocked`). The agent session itself is **not** contained and cannot be under `--network none`,
  because that session is an API call. It is bounded by a temp copy, a tool allowlist and an
  environment allowlist instead. `--docker` is also opt-in, so the default path still executes
  agent-written code on the host; the approval banner says so in those words. Both approval gates
  weaken to a printed warning when stdin is not a terminal, so an unattended run has no approval
  step. See [docs/SANDBOXING.md](docs/SANDBOXING.md).
- **28% of the leakage flags come from a stack trace.** In 37/500 the gold file appears *only*
  inside a pasted traceback — a reporting convention, not an authoring error. Both readings are
  published rather than one: leakage 133/500 (26.6%) or **96/500 (19.2%)** strict, and the headline
  42.0% or **37.8%** strict. `uv run python -m rewardgate.report_real` prints both, and both are
  pinned in `tests/test_corpus_rates.py`. Take 37.8% as the conservative number.
- **No capability-matched baseline was run, and "0 executed artifacts" is true by construction.**
  `baseline.py` runs with all tools disallowed — that is the challenge's own suggested baseline —
  and the parity arm fixes only the *information* asymmetry. A tool-enabled baseline was not built
  because `corpus/synthetic/bundles/labels.yaml` is the answer key `evaluate.load_truth()` scores
  against, one directory above every bundle: granting `Bash`/`Read` yields 15/15 by reading it, and
  withholding it reintroduces the asymmetry the parity ablation exists to remove.
- **The permutation p = 0.0286 treats clustered units as independent.** The 15 bundles are 5
  variants of 3 base repositories, so the effective n is nearer 3 than 15 and the p-value is
  optimistic by an amount this design cannot estimate.
- Representative trajectories exist for the three agents that ship inside the product. The
  development-time agents are documented as reconstructions, and labelled as such.
- **One implementation defect, confirmed with an executed reproduction and left unfixed.** Exploit
  cost strips `#` comments but not docstrings, so a planted docstring still inflates the count past
  the threshold and grades a known-bad task "too expensive to game".

  It is left because `results/multitrial_preregistration.json` **freezes the cost metric**, and
  changing it after seeing the trials is exactly the tuning pre-registration exists to prevent —
  the same reason the interval-predicate blind spot in the main failure mode is also left alone.
  The right repair is the semantic cost measure named there, not another regex, and it invalidates
  the pre-registered k=5 result.

  The other four originally listed here are now fixed, each with a regression test that reproduces
  the defect against the pre-fix code first:

  | Was | Now | Reproduction before the fix |
  |---|---|---|
  | Environment allowlist covered the harness, not the agent session | `exploit.agent_env` at all three invocation sites | six secrets asserted absent, `ANTHROPIC_API_KEY` asserted present |
  | `files_in_patch` parsed only `diff --git` | reads `+++ b/...` | POSIX `diff -u` returned `{}`; a rename returned the *old* path |
  | Contamination fingerprint subtracted across every file the patch names | subtracted **per file** | a decoy file took the surviving fingerprint from one line to zero, and a side-branch fix reported clean |
  | A shipped `.gitignore` reading `src/` emptied every captured diff | `git add -f` | measured: 0-byte diff **and** empty `git status`, so it did not even trip the modified-but-no-diff guard |

