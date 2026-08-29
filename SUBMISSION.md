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
| 2 | Reproduction guide | [`REPRODUCTION.md`](REPRODUCTION.md) — free path, no API key |
| 3 | Solution video (≤5 min) | [`rewardgate-demo.mp4`](rewardgate-demo.mp4) (in this repo), script in [`docs/VIDEO_SCRIPT.md`](docs/VIDEO_SCRIPT.md) |
| 4 | Agent trajectories | [`AGENT_TRAJECTORIES.md`](AGENT_TRAJECTORIES.md) and [`trajectories/`](trajectories/) |

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

Then, if you want the whole thing: `uv run pytest -q` (255 tests) and
`uv run python scripts/run_parity_ablation.py --replay` (the ablation that refuted my own
headline — free, under a second).

## What I would want a judge to check first

1. **Is the 42% real?** Run `report_real`. It is deterministic and third-party; nothing about it
   depends on my synthetic corpus or on trusting me.
2. **Did I grade my own homework?** The synthetic tier is mine and says so. The
   [circularity section](README.md#why-these-numbers-are-not-circular) states exactly what the
   third-party anchor does and does not establish.
3. **Is the improvement claim honest?** I ran the ablation that could refute it, and it did: the
   gap against a *fair* baseline is 0.044 at McNemar p = 1.00, not the 0.333 I first measured. Both
   numbers, and why the first was wrong, are in the changelog.

## Code freeze

Code frozen after the fifth adversarial review round. Defects found after the freeze are
**documented below rather than fixed**, because the measured regression rate on this repository's
security-hardening edits was roughly one in two: two round-4 exploits defeated round-3 fixes, and
four round-5 exploits defeated round-4 fixes. An unverified late fix is worse than a disclosed bug.

## Known limitations, stated up front

- **The exploit agent has an unexplained capability boundary.** Measured at k=5 on all 15 bundles
  (pre-registered, $26.67): 2 of 3 reward-hackable bundles detect 5/5, the third detects 0/5, and
  all 12 others detect 0/5. Perfectly bimodal — the agent is deterministic, not noisy, so the miss
  is a blind spot and not sampling. I do not know whether the cause is the brief, the cost grader,
  or the task shape. Exploit cost is still priced by regex; a semantic measure is not implemented.
- The sandbox is a temp directory, **not a container**. An interactive confirmation now gates the
  exploit tier and names the risk, but approval is not isolation. A REJECT likewise prompts the
  reviewer for confirm/override/defer. Both gates weaken to a printed warning when stdin is not a
  terminal, so an unattended run has no approval step at all. The agent writes a patch and the harness
  executes it, so module-scope code in that patch runs on the host. Disclosed, not mitigated.
- Representative trajectories exist for the three agents that ship inside the product. The
  development-time agents are documented as reconstructions, and labelled as such.
- **Five implementation defects in the detector family, confirmed with executed reproductions and
  left unfixed.** They share one cause: fingerprinting and cost-pricing are done by matching source
  text, which is too literal an instrument for the question being asked.
  (i) The environment allowlist covers the harness, not the agent session — `exploit._run_agent`
  and `baseline.audit_bundle` invoke the CLI with no `env=`.
  (ii) The contamination scope set is read from the audited patch, so a planted decoy file erases
  the fingerprint.
  (iii) Exploit cost ignores `#` comments but not docstrings.
  (iv) `files_in_patch` parses only the `diff --git` header form, silently disabling (ii)'s guard.
  (v) A bundle shipping a `.gitignore` containing `src/` makes every captured diff empty, so every
  exploit reports as "RESISTED".

  Documented rather than patched: the measured regression rate on this repository's
  security-hardening edits ran at roughly one in two across two review rounds, so an unverified late
  fix is worth less than a disclosed defect. The right repair is the semantic cost measure named in
  the main failure mode, not five more regexes.

