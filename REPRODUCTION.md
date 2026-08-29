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
an EXECUTED EVIDENCE block with real exit codes, and a human checkpoint. **In a terminal this
prompts for `confirm` / `override` / `defer`** and exits 1 / 0 / 3 accordingly; piped or scripted
it prints the banner and exits 1. Pass `--yes` to skip the prompt.
`--no-exploit` skips the paid agent tier; drop it to run the full pipeline on one bundle (~$0.26). **That tier executes agent-written code
on this machine**, so in a terminal it first requires you to type `yes`; `--yes` skips the gate.

### A3. Run the test suite

```bash
uv run pytest -q
```

Expected: **0 failed**, in roughly 10–20 seconds.

How many tests *run* depends on optional prerequisites, so the pass count is not a single
number and this guide will not pretend it is. All three of these were observed:

| State | Skipped |
|---|---|
| Clean clone, nothing else fetched | **7** — 4 container, 3 held-out corpus |
| After A4b fetches the held-out corpus | **4** — container only |
| After A8 builds `rewardgate-sandbox:1` | **0** |

Skips are quoted rather than pass counts on purpose: the skip count depends on which optional
prerequisites you have, which is the thing that actually varies, while a pass count also moves
every time a test is added. Documenting the moving number is how this guide got it wrong three
times, and `tests/test_docs_match_artifacts.py` now fails the suite if any document disagrees with
the real total.

Run `uv run pytest -q -rs` to see which are skipped and why; every skip names the command that
enables it. **No configuration produces a failure** — that is the claim to hold this to. An earlier
version of this file asserted a flat pass count, which was only reachable with a container image
the guide had not told you to build.

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

Expect these lines among the output:

```
solution leakage (gold file named)     133/500  ( 26.6%)  cf. published 135 (different heuristic: theirs also counts imports, mine counts basenames)
over-specified (internal symbol)        42/500  (  8.4%)
hint discloses gold-patch lines         54/500  ( 10.8%)
weak fail-to-pass assertions            48/350  ( 13.7%)
AT LEAST ONE DEFECT                    210/500  ( 42.0%)
```

### A4b. Replicate the finding on a held-out corpus

```bash
./scripts/fetch_holdout_corpus.sh          # SWE-Gym, ~44 MB, checksum-pinned
uv run python -m rewardgate.report_real --holdout
```

The same four checkers, unchanged, on 2,438 instances from a different set of repositories with
**zero overlap** with SWE-bench Verified. Expect `AT LEAST ONE DEFECT 1061/2438 (43.5%)` against
Verified's 42.0%, and leakage 27.2% against 26.6%. **$0.00, a few seconds.**

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

Expected: JSON containing `"p_value": 0.25` and 3 discordant pairs — not significant at
alpha = 0.05. The module prints the machine-readable form; the interpretation is in the README.

### A6. Reproduce the ablation that refutes the headline

```bash
uv run python scripts/run_parity_ablation.py --replay
```

Re-scores the committed parity audits. **$0.00, under a second.** This is the most consequential
result in the report, so it has a free path: a judge should not have to take the retraction on
trust any more than the original claim.

Expect these lines among the output:

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

### A8. Verify the sandbox actually sandboxes — optional, needs a container engine

Still no API key, but this one needs Docker (or a compatible engine) and one image build, so it is
last in Path A rather than first.

```bash
docker build -t rewardgate-sandbox:1 docker/      # ~40s, needs network once
uv run python scripts/prove_containment.py        # $0.00, ~15s
```

The script builds a bundle whose test module tries three things an exploit patch would try, runs it
**on the host and in the container**, and prints the difference. Expect:

```
PROBE             HOST                              CONTAINED
==========================================================================
network           reachable                         blocked (OSError)
host_write        written                           blocked (FileNotFoundError)
uid               501                               1000
is_root           False                             False
canary_on_disk    True                              False
secrets_visible   []                                []
```

`uid` will differ on your machine — it is whatever your account is. The rows that matter are
`network` and `canary_on_disk`, and they must differ between the two columns; if the host row also
reads `blocked`, the script says so rather than claiming a result it did not demonstrate.

Then use it for real:

```bash
uv run rewardgate audit csvlite-clean --no-exploit --docker
```

If the engine or image is missing this exits **2** with the build command rather than falling back
to host execution. Nothing about `--docker` is asserted from flags alone —
[docs/SANDBOXING.md](docs/SANDBOXING.md) states what it does and does not cover.

---

## Path B — re-run the agent trials

Requires the Claude Code CLI, authenticated (`claude login`) **or** `ANTHROPIC_API_KEY` exported.
No credits are provided by this project.

### A7. Reproduce the k-trial experiment

```bash
uv run python scripts/run_multitrial.py --replay
```

Re-scores 75 saved exploit trials. **$0.00, under a second.** This is the project's only
statistically significant result, and the pre-registration that fixed its decision rule before any
trial ran is in [`results/multitrial_preregistration.json`](results/multitrial_preregistration.json).

Expected: every *detection* rate exactly 0.0 or 1.0, zero detections on the other 12, statistic
**+0.667**, exact permutation **p = 0.0286**.

To regenerate rather than replay, drop `--replay`: 75 live agent trials, **~$27, ~2.5 hours**,
needs an API key (Path B).

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
