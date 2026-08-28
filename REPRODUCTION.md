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
No Docker image is built. Total disk footprint is under 50 MB including the corpus.

```bash
git clone <repository-url> rewardgate
cd rewardgate
uv sync                       # installs from uv.lock, ~10s
```

---

## Path A — free, offline, no API key

### A1. Fetch the third-party corpus (~2.0 MB)

```bash
./scripts/fetch_real_corpus.sh
```

Downloads SWE-bench Verified (500 instances, MIT licence, Princeton NLP) and verifies it against a
pinned SHA-256. The script refuses to continue on a checksum mismatch.

### A2. Build the synthetic corpus

```bash
uv run python corpus/synthetic/build.py
```

Expected output: `built 12 bundles`, listing 3 base repositories × (1 clean + 3 defect variants).
Ground truth is written to `corpus/synthetic/bundles/labels.yaml` **by the injector that produced
each defect**, so the labels cannot drift from the artifacts.

### A3. Run the test suite

```bash
uv run pytest -q
```

Expected: all tests pass in a few seconds. This includes the corpus-level regression tests that
pin every headline number, so a green suite *is* verification of the static claims — including
that the solution-leakage detector still measures 133/500 on SWE-bench Verified.

### A4. Reproduce the third-party findings

```bash
uv run python -m rewardgate.report_real
```

Runs the four deterministic checkers across all 500 real instances. No model calls, no cost.

### A5. Re-score the saved agent audits

```bash
uv run python -m rewardgate.evaluate --replay
```

Loads `results/baseline_audits.json` and `results/rewardgate_audits.json` and recomputes the
comparison table. This is arithmetic over committed data — it needs no network and no key.

### A6. Deterministic tiers only, live

```bash
uv run python -m rewardgate.evaluate --no-exploit
```

Runs the reward gate and contamination scan live but skips the agent. Note this still invokes the
baseline, which does cost money; use `--replay` for a strictly free run.

---

## Path B — re-run the agent trials

Requires the Claude Code CLI, authenticated (`claude login`) **or** `ANTHROPIC_API_KEY` exported.
No credits are provided by this project.

```bash
uv run python -m rewardgate.evaluate
```

This runs both systems over all 12 bundles and overwrites the saved audits.

### What it costs and how long it takes

Measured, not estimated — every figure below comes from the `total_cost_usd` field the CLI returns
per invocation, summed in `results/summary.json`.

| Item | Measured |
|---|---|
| Baseline, per bundle | ~$0.18 |
| RewardGate exploit trial, per bundle | ~$0.28 |
| Full 12-bundle evaluation, both systems | see `results/summary.json` |
| Deterministic checkers (all 500 real + 12 synthetic) | **$0.00** |

A single trivial `claude -p` call costs ~$0.19 before doing any work, because the CLI injects
roughly 31,000 tokens of system prompt per fresh session. That overhead is the reason the
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
