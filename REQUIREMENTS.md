# Requirement → implementation

Every stated requirement of the micro1 Frontier Engineering Challenge, mapped to where it is met
and where it is not. Written so a judge can verify completeness without reading the whole
repository, and so the gaps are declared rather than discovered.

Verified against the working tree; every path below exists.

---

## Qualification gate

> *"A submission is scored only after it passes eligibility, completeness, integrity, trace and
> reproducibility checks. A project that cannot be run or verified may be disqualified before
> rubric scoring."*

| Gate item | Where | Status |
|---|---|---|
| Repository obtainable | `github.com/Gaurav1112/rewardgate`, public | **PASS** |
| Archive | built on demand with `git archive --format=zip --prefix=rewardgate/ HEAD -o rewardgate-submission.zip`; last build verified to run standalone (`uv sync && pytest` inside the extracted copy) | **PASS (built at submission time, not committed)** |
| Tests | `uv run pytest -q` → **294 collected, 0 failed**, ~14s, no API key. Pass count depends on optional prerequisites: `287 passed, 7 skipped` on a clean clone, `290/4` with the held-out corpus, `294 passed` after the sandbox image is built. Every skip names the command that enables it | **PASS** |
| README | [README.md](README.md) — user, bottleneck, why it matters | **PASS** |
| Agent-use evidence | [AGENT_TRAJECTORIES.md](AGENT_TRAJECTORIES.md), [`trajectories/`](trajectories/) | **PASS** |
| Demo video | [`rewardgate-demo.mp4`](rewardgate-demo.mp4), 4:46, tracked in-repo | **PASS** |
| Reproducibility | [REPRODUCTION.md](REPRODUCTION.md); clean-clone run reproduces byte-identical results | **PASS** |

---

## Deliverables

| # | Requirement | Implementation | Status |
|---|---|---|---|
| 1 | Full project + everything to run it | the repository; `uv.lock` pinned | ✅ |
| 1 | **The instructions that shape each agent** | `EXPLOIT_BRIEF` (`rewardgate/exploit.py`), `PREAMBLE` (`rewardgate/baseline.py`); both reproduced verbatim in `trajectories/*.md` | ✅ |
| 1 | README introduces user, bottleneck, value | [README.md § Who has this problem](README.md#who-has-this-problem) | ✅ |
| 1 | **Clearly labelled** Improvement Changelog | [IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md) | ✅ |
| 1 | Changelog in the prescribed 4-column structure | `## Summary` table: STAGE / WHAT I TRIED AND WHY / EVIDENCE / DECISION / LEARNING, 9 rows | ✅ |
| 1 | An entry per meaningful iteration, tied to evidence | Baseline + Iterations 1–6 + 2 Removed + 1 Withdrawn, each with a measured Evidence block | ✅ |
| 1 | Experiments later removed, and what they taught | `## Removed — a per-defect-class agent fan-out`, `## Removed — relying on conftest.py`, `## Withdrawn — a finding that was my own bug` | ✅ |
| 1 | **Close with main failure mode and hot take** | `## Main failure mode` then `## Hot take`, final two sections | ✅ |
| 2 | Clean-environment setup | [REPRODUCTION.md § 0](REPRODUCTION.md) — prerequisites table with pinned versions and host specs | ✅ |
| 2 | Exact commands for solution, baseline **and** evaluation | A2b solution · B0/`evaluate` baseline · A5/A5b/A6 evaluation | ✅ |
| 2 | Which data is required | A1, SHA-256-pinned fetch that refuses on mismatch | ✅ |
| 2 | What output to expect | verbatim expected blocks at each step | ✅ |
| 2 | Versions, runtime, cost | prerequisites table; measured cost table (`$0.1174` / `$0.2551` / bundle) | ✅ |
| 3 | Video ≤ 5 minutes | 4:46 (286.2s, ffprobe), 1920×1080 | ✅ |
| 3 | Problem and simple baseline first | 0:00–1:28 | ✅ |
| 3 | One realistic execution start to finish | 1:28–2:34, reward gate → exploit patch → adjudication | ✅ |
| 3 | Final comparison | 2:34–3:22, the parity ablation | ✅ |
| 3 | Briefly explain the changelog | 3:22–4:01 | ✅ |
| 3 | Highlight the biggest contributor | 4:01, regrading exploits on **cost** rather than existence | ✅ |
| 3 | One experiment you removed | 4:20, the five-agent fan-out | ✅ |
| 4 | Trajectories for **every agent you used** | 3 shipping agents, all covered — see the roster below | ⚠️ **partial** |
| 4 | Instructions → tool calls → tool responses | `trajectories/exploit-agent-*.md` + `.jsonl` | ✅ |
| 4 | Feedback that shaped the next step | same transcripts, per-turn | ✅ |
| 4 | Retries **and human checkpoints** | no retries exist and this is stated; a permission denial appears in both exploit transcripts | ⚠️ |

### Agent roster

| Agent | Invoked at | Trajectory |
|---|---|---|
| Adversarial exploit agent | `rewardgate/exploit.py` | ✅ 2 transcripts + raw JSONL |
| Baseline auditor | `rewardgate/baseline.py` | ✅ `trajectories/baseline-csvlite-nop-pass.md` |
| Baseline, **parity mode** | `rewardgate/baseline.py`, `parity=True` | ✅ `trajectories/baseline-parity-csvlite-contaminated-git.md` |
| Development-time agents (research, design panel, implementation) | not shipped | ⚠️ prose reconstructions, labelled as such |

---

## Rule book

| # | Rule | Status | Evidence |
|---|---|---|---|
| 1 | Build with tools you know | ✅ | stdlib + pytest + pyyaml + pyarrow; agent is the Claude Code CLI |
| 2 | Clear what pre-existed vs what you added | ✅ | 47+ commits, all inside the window; SWE-bench fetched not vendored; 15 papers cited |
| 3 | Licences and service terms | ✅ | MIT `LICENSE`; dataset fetched at runtime, never redistributed |
| 4 | Consequential actions sandboxed; human approval | ✅ | **Sandboxed:** `--docker` runs every test execution in a container with `--network none`, non-root, capabilities dropped and no host path mounted — measured against the uncontained run by `scripts/prove_containment.py`, not asserted. **Approval:** interactive sessions must type `yes` before the exploit tier runs, and the warning has two variants so the contained one still names what it does *not* cover. Non-interactive callers are warned and proceed, a stated weakening. `--no-exploit` needs no approval because it executes nothing. Remaining gap: the agent session cannot be contained under `--network none` (it is an API call), and `--docker` is opt-in. |
| 5 | Qualified human reviewer in the loop | ✅ | An interactive REJECT now requires the reviewer to record **confirm / override / defer**, and the decision is printed into the report and sets the exit code. `override` exits 0: a reviewer who has read the evidence outranks the tool. `defer` exits 3, because undecided must not read as accepted. |
| 6 | Legal and ethical use case | ✅ | `LICENSE` bounds intended use to pre-submission auditing |
| 7 | Data you are allowed to share | ✅ | public SWE-bench Verified + self-authored synthetic corpus |
| 8 | Credentials and private info excluded | ✅ | zero secrets in tree or history; host paths scrubbed |
| 9 | Every claim connected to evidence | ✅ | see below |
| 10 | Judges can run it and reproduce | ✅ | public repo, free path, no API key |

---

## Declared gaps

Listed here rather than left to be found. All are confirmed with executed reproductions; see
[SUBMISSION.md](SUBMISSION.md) for the full text.

1. **The agent session is not contained.** `--docker` contains every *test execution* under
   `--network none` with no host path mounted, measured both ways by
   `scripts/prove_containment.py`. The agent session cannot be — it is an API call — and `--docker`
   is opt-in, so the default path still runs agent-written code on the host.
   See [docs/SANDBOXING.md](docs/SANDBOXING.md).
2. **Exploit cost is not invariant to docstrings.** Comment stripping handles `#`, not `"""`. Left
   unfixed on purpose: `results/multitrial_preregistration.json` freezes the cost metric.
3. **Two further paths reach ACCEPT with the held-out suite unmeasured.**
4. **The primary metric is a null result.** macro-F1 0.933 against a fair baseline's 0.889 — one
   discordant judgement in 45, McNemar exact **p = 1.00**. Established by
   [the author's own ablation](docs/EVALUATION.md#the-ablation-that-refutes-the-headline).
5. **Development-time agent trajectories are prose reconstructions**, not transcripts.

Four defects previously listed here have been fixed, each with a regression test that reproduces
the defect against the pre-fix code before pinning it: the environment allowlist at all three
invocation sites, `files_in_patch` reading `+++ b/...`, per-file contamination subtraction, and
`git add -f` past a shipped `.gitignore`. See [SUBMISSION.md](SUBMISSION.md) for the table.

---

## Claim → evidence

| Claim | Verify with |
|---|---|
| 210/500 (42.0%) carry a defect | `uv run python -m rewardgate.report_real` |
| Replicates at 43.5% on a zero-overlap held-out corpus | `./scripts/fetch_holdout_corpus.sh && uv run python -m rewardgate.report_real --holdout` |
| 133/500 leakage; cf. published 135 | same command — **different heuristics, corroboration not replication** |
| 37/500 leakage flags come only from a stack trace; strict headline 189/500 (37.8%) | `uv run python -m rewardgate.report_real` — both figures printed |
| Human time per task: manual floor 0.17s vs RewardGate 0.26s (the tool is *slower*) | `uv run python scripts/measure_human_time.py` |
| macro-F1 0.600 baseline / 0.933 RewardGate | `uv run python -m rewardgate.evaluate --replay` |
| Parity: 0.889 vs 0.933, gap 0.044, p = 1.00 | `uv run python scripts/run_parity_ablation.py --replay` |
| McNemar p = 0.2500, 3 discordant | `uv run python -m rewardgate.significance` |
| Every third-party corpus number is pinned | `uv run pytest -q` → 294 collected, 0 failed |
| Cost $0.1174 / $0.2551 per bundle | `results/summary.json` |
| CLI overhead $0.1967 before any work | `results/cli_overhead_probe.json` |
| `--docker` blocks the network and the host filesystem | `docker build -t rewardgate-sandbox:1 docker/ && uv run python scripts/prove_containment.py` |

Every command above is free, offline, and needs no API key — except the last, which needs a
container engine and one image build.
