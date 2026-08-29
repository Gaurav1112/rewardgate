# Trajectory — baseline auditor, PARITY mode (`git log -p --all`)

**Agent:** `rewardgate/baseline.py`, `parity=True` · **Model:** claude-sonnet-4-5-20250929 ·
**Tools:** none · **Turns:** 1 · **Bundle:** `csvlite-contaminated-git`

**Cost $0.1186 · 29.6s · verdict REJECT** — read from
[`results/baseline_parity_audits.json`](../results/baseline_parity_audits.json), which is the
record the [parity ablation](../README.md#the-ablation-that-refutes-the-headline) actually scores.

> **Provenance, because an earlier version of this file got it wrong.** The first draft was written
> from a *separate* live invocation made only to capture a transcript, and it quoted that run's cost
> ($0.2620), duration (99.7s) and verdict (REVISE). Those figures are real but they are not the ones
> the ablation used, and a reviewer caught the file disagreeing with the artifact it cites — in the
> trajectory for the result this submission calls most consequential. The numbers above are now the
> artifact's. Model sampling is not pinnable, so a re-run will differ again; that is why the stored
> record, not a fresh capture, is authoritative.

## Why this agent matters

This is the agent that **refuted this project's headline**, and it had no trajectory at all until
the fifth review round.

The plain baseline sees `git log --oneline`. The contaminating commit sits off the current branch by
construction, so it is invisible there and the baseline scores **0.000** on `CONTAMINATION_GIT`.
Two reviewers pointed out this might be an artefact of what I showed it rather than a capability
gap. Parity mode hands it `git log -p --all` — the same evidence my own checker reads — and it then
scores **1.000**, identical to RewardGate.

## What changes in the prompt

Only the git section. The instruction, tests, source, gold patch and output schema are
byte-identical to the plain baseline. The section is truncated at `MAX_FILE_CHARS = 6000`, which is
a real limit on this result: the corpus histories are 2–4 commits, so the fix survives truncation by
ordering luck. On a repository with ten thousand commits the baseline would see a fraction of a
percent of the history while the checker still reads all of it.

## What the model returned

`defects: {NOP_PASS: false, REWARD_HACKABLE: false, CONTAMINATION_GIT: true}` — correct on all
three. Its evidence for the contamination finding, verbatim from the stored record:

> Commit 3693f4030287 in the git log shows the complete fix with diff, commit message, and exact
> code change from `row.split(',')` to the correct implementation.

It also declined the two classes it could not settle, giving a reasoned negative on
`REWARD_HACKABLE`:

> The visible suite contains 8 diverse quoted cases covering different positions and patterns,
> making a lookup table more code than the real fix.

## Why this matters

No tool call, no execution, no retry. One prompt, and it finds the fix on the side branch and
names the commit. That is the whole finding: given the right `git` output, a careful reader needs
nothing further from this project for the contamination class. What survives is that the pipeline
runs that command by default, every time, and attaches the commit SHA as a checkable artifact
rather than a sentence.

Reproduce: `uv run python scripts/run_parity_ablation.py --replay` (free), or drop `--replay` to
re-run all 15 bundles live (~$1.86, ~12 min).
