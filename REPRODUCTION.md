# Reproduction Guide

Written for someone starting from a clean machine with nothing installed.

There are two paths. **Path A costs nothing and needs no API key** — it reproduces the deterministic
findings and re-scores the saved audits. **Path B** re-runs the agent trials and costs a few
dollars. Path A is enough to verify every number in the README; Path B is how you confirm the
saved audits were not fabricated.

---

## 0. Prerequisites

| Tool | Version used | Why |
|---|---|---|
| Python | 3.11–3.12 | pinned in `pyproject.toml` (`>=3.11,<3.13`) |
| [uv](https://docs.astral.sh/uv/) | 0.11.15 | dependency resolution from the committed `uv.lock` |
| git | 2.39.5 | corpus history and patch application |
| Claude Code CLI | 2.1.231 | **Path B only** — the agent runtime |

Measured on macOS 15 (Darwin 24.6.0), Apple Silicon, 12 cores, 48 GB RAM.
No Docker image is built. The repository plus corpus is about 6 MB; a populated `.venv`
adds roughly 115 MB (pyarrow dominates), so budget ~120 MB in total.

```bash
git clone https://github.com/Gaurav1112/rewardgate.git rewardgate
cd rewardgate
uv sync                       # installs from uv.lock, ~10s
```

---

## Path A — free, offline, no API key

### A1. Fetch the third-party corpus (~2.0 MB)

```bash
./scripts/fetch_real_corpus.sh
```

Downloads SWE-bench Verified (500 instances, Princeton NLP) and verifies it against a pinned
SHA-256. The SWE-bench *harness* is MIT-licensed; the dataset card carries no explicit licence
tag and instances derive from their upstream projects' licences. The script refuses to continue on a checksum mismatch.

### A2. Build the synthetic corpus

```bash
uv run python corpus/synthetic/build.py
```

Expected output: `built 15 bundles`, listing 3 base repositories × (1 clean + 1 clean-git
control + 3 defect variants).
Ground truth is written to `corpus/synthetic/bundles/labels.yaml` **by the injector that produced
each defect**, so the labels cannot drift from the artifacts.

### A2b. Audit a single task — this is the product

```bash
uv run rewardgate list
uv run rewardgate audit csvlite-contaminated-git --no-exploit
```

Free and offline. Expect `VERDICT: REJECT`, a `CONTAMINATION_GIT` finding naming the hidden commit,
an EXECUTED EVIDENCE block with real exit codes, and a human-checkpoint banner. Exit code 1.
`--no-exploit` skips the paid agent tier; drop it to run the full pipeline on one bundle (~$0.26).

### A3. Run the test suite

```bash
uv run pytest -q
```

Expected: `255 passed`, in roughly 10–16 seconds.

What a green suite does and does not verify. It pins **every third-party-corpus number** — the
133/500 leakage figure, the 42.0% at-least-one-defect rate, and the specific instance *ids*, not
merely their count — so those claims are checked, not asserted. It does **not** pin the synthetic
corpus's headline figures (macro-F1 0.600 / 0.889 / 0.933, the costs, the wall clock); those are
reproduced by replaying the committed audits in **A5** and **A6** instead. An earlier version of
this file claimed the suite pinned "every headline number". It did not, and the difference matters
in a project whose thesis is that unverified numbers are the problem.

### A4. Reproduce the third-party findings

```bash
uv run python -m rewardgate.report_real
```

Runs the four deterministic checkers across all 500 real instances. No model calls, no cost.

Expect these five lines among the output (the full block adds a header, a clean-on-all-checks row, and an INDETERMINATE limitation note):

```
solution leakage (gold file named)     133/500  ( 26.6%)  cf. published 135 (different heuristic: theirs also counts imports, mine counts basenames)
over-specified (internal symbol)        42/500  (  8.4%)
hint discloses gold-patch lines         54/500  ( 10.8%)
weak fail-to-pass assertions            48/350  ( 13.7%)
AT LEAST ONE DEFECT                    210/500  ( 42.0%)
```

### A5. Re-score the saved agent audits

```bash
uv run python -m rewardgate.evaluate --replay
```

Loads `results/baseline_audits.json` and `results/rewardgate_audits.json` and recomputes the
comparison table. This is arithmetic over committed data — it needs no network and no key.

Expected: `baseline macro-F1=0.600` and
`rewardgate macro-F1=0.933`, exact-match
11/15 and 14/15.

### A5b. Check the statistics

```bash
uv run python -m rewardgate.significance
```

Expected: `McNemar exact p = 0.2500 — NOT significant at alpha=0.05`, with 3 discordant pairs.

### A6. Reproduce the ablation that refutes the headline

```bash
uv run python scripts/run_parity_ablation.py --replay
```

Re-scores the committed parity audits. **$0.00, under a second.** This is the most consequential
result in the report, so it has a free path: a judge should not have to take the retraction on
trust any more than the original claim.

Expect these five lines among the output (the full block adds a header, a clean-on-all-checks row, and an INDETERMINATE limitation note):

```
SYSTEM                            macro-F1   CONTAM F1   exact      cost
========================================================================
baseline (git log --oneline)         0.600       0.000    11/15    1.7606
baseline (git log -p --all)          0.889       1.000    13/15    1.8553
RewardGate                           0.933       1.000    14/15    3.8271

parity baseline vs RewardGate: 0 judgements only the baseline got right, 1 only RewardGate, McNemar exact p = 1.0000
discordant: semverlite-nop-pass/REWARD_HACKABLE
```

To regenerate rather than replay, drop `--replay`: 15 fresh model calls, **~$1.86, ~12 minutes**,
and it needs an API key (Path B).

---

## Path B — re-run the agent trials

Requires the Claude Code CLI, authenticated (`claude login`) **or** `ANTHROPIC_API_KEY` exported.
No credits are provided by this project.

### B0. Deterministic tiers only, live — NOTE: this costs money

```bash
uv run python -m rewardgate.evaluate --no-exploit
```

Runs the reward gate and contamination scan live but skips the agent. **This still invokes the
baseline, so it is not free** — it is listed here under Path B rather than Path A for that reason.
Use `--replay` for a strictly free run.


```bash
uv run python -m rewardgate.evaluate
```

This runs both systems over all 15 bundles and overwrites the saved audits.

### What it costs and how long it takes

Measured, not estimated — every figure below comes from the `total_cost_usd` field the CLI returns
per invocation, summed in `results/summary.json`.

| Item | Measured |
|---|---|
| Baseline, per bundle | **$0.1174** |
| RewardGate exploit trial, per bundle | **$0.2551** |
| Full 15-bundle evaluation, both systems | **$5.5877**, 1711.3s |
| Deterministic checkers (all 500 real + 15 synthetic) | **$0.00** |

A single trivial `claude -p` call costs **$0.1967** before doing any work, because the CLI
injects **31,711** tokens of system prompt per fresh session — measured and recorded in
`results/cli_overhead_probe.json`. That overhead is the reason the
architecture pushes every defect class it can onto deterministic checks.

### Expected variation

Model sampling is not pinnable — `temperature` is not exposed on the current models — so the agent
may find a different exploit, or take a different number of turns, between runs. The **verdicts**
have been stable across runs; the exploit patch text and cost vary. If you get a materially
different macro-F1, that is a finding worth reporting, not a setup error.

---

## Layout

```
rewardgate/          the auditor: checkers, reward gate, exploit agent, scorer
corpus/synthetic/    base repos, defect injector, generated bundles
corpus/real/         fetch script for SWE-bench Verified (data not vendored)
results/             saved audits, agent trials, summary
trajectories/        agent trajectory logs
tests/               unit tests plus corpus-level regression tests
docs/specs/          design specification
```

## Troubleshooting

**`Real corpus not found`** — run `./scripts/fetch_real_corpus.sh`.

**`run: uv run python corpus/synthetic/build.py`** in skipped tests — the synthetic corpus has not
been built. Run step A2.

**Agent trial returns `ERROR`** — check `claude -p "hi"` works and is authenticated. The trial has
a 600-second timeout per bundle.

**Different numbers on the real corpus** — the fetch script pins a SHA-256. If it passed, the data
is identical, and any difference is in the code rather than the input.
