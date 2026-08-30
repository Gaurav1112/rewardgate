# Terminal session — every documented command, complete and unedited

Captured by `scripts/capture_session.sh` on a clean checkout. Nothing here is grepped,
reformatted, or retyped: it is the full `stdout`+`stderr` of each command in order. The video's
slides show selected lines from these same runs; this is the unfiltered version.

Environment: macOS 15 (Darwin 24.6.0), Apple Silicon, Python 3.12, uv 0.11.15.

## `uv run rewardgate list`

```
csvlite-clean
csvlite-clean-git-history
csvlite-contaminated-git
csvlite-nop-pass
csvlite-reward-hackable
retrylite-clean
retrylite-clean-git-history
retrylite-contaminated-git
retrylite-nop-pass
retrylite-reward-hackable
semverlite-clean
semverlite-clean-git-history
semverlite-contaminated-git
semverlite-nop-pass
semverlite-reward-hackable
[exit 0]
```

## `uv run python -m rewardgate.report_real`

```
SWE-bench Verified — 500 instances, deterministic checks, $0.00
==============================================================================
solution leakage (gold file named)     133/500  ( 26.6%)  cf. published 135 (different heuristic: theirs also counts imports, mine counts basenames)
  of which full path (high conf.)      107/500  ( 21.4%)  
  of which named ONLY in a traceback    37/500  (  7.4%)  arguably not authored leakage — see below
over-specified (internal symbol)        42/500  (  8.4%)  
  high severity (symbol + file)         16/500  (  3.2%)  
hint text present                      335/500  ( 67.0%)  
  hint discloses gold-patch lines       54/500  ( 10.8%)  
weak fail-to-pass assertions            48/350  ( 13.7%)  of instances whose test diff parses
  assertion parse coverage             350/500  ( 70.0%)  
------------------------------------------------------------------------------
AT LEAST ONE DEFECT                    210/500  ( 42.0%)  
  strict: traceback-only leakage excluded 189/500  ( 37.8%)  
clean on all four checks               290/500  ( 58.0%)  

Limitation stated plainly: 150/500 instances are INDETERMINATE for assertion analysis (the diff adds no test function, or is a mid-file hunk that does not parse). Those are excluded from the weak-assertion rate rather than counted as clean.

saved -> /Users/racit/rewardgate/results/real_corpus_findings.json
[exit 0]
```

## `uv run python -m rewardgate.report_real --holdout`

```
SWE-Gym (held out) — 2438 instances, deterministic checks, $0.00
==============================================================================
solution leakage (gold file named)     663/2438 ( 27.2%)  
  of which full path (high conf.)      569/2438 ( 23.3%)  
  of which named ONLY in a traceback   203/2438 (  8.3%)  arguably not authored leakage — see below
over-specified (internal symbol)       154/2438 (  6.3%)  
  high severity (symbol + file)         83/2438 (  3.4%)  
hint text present                     1528/2438 ( 62.7%)  
  hint discloses gold-patch lines       79/2438 (  3.2%)  
weak fail-to-pass assertions           455/1480 ( 30.7%)  of instances whose test diff parses
  assertion parse coverage            1480/2438 ( 60.7%)  
------------------------------------------------------------------------------
AT LEAST ONE DEFECT                   1061/2438 ( 43.5%)  
  strict: traceback-only leakage excluded 945/2438 ( 38.8%)  
clean on all four checks              1377/2438 ( 56.5%)  

Limitation stated plainly: 958/2438 instances are INDETERMINATE for assertion analysis (the diff adds no test function, or is a mid-file hunk that does not parse). Those are excluded from the weak-assertion rate rather than counted as clean.

saved -> /Users/racit/rewardgate/results/holdout_corpus_findings.json
[exit 0]
```

## `uv run rewardgate audit csvlite-clean --no-exploit`

```
==============================================================================
REWARDGATE AUDIT — csvlite-clean
==============================================================================

VERDICT: INDETERMINATE
         2 of 3 classes checked — sound so far, but not certified

------------------------------------------------------------------------------
FINDINGS
------------------------------------------------------------------------------

[  ok   ] NOP_PASS
          reward gate holds (oracle exit=0 passed=11 failed=0 errors=0; nop exit=1 passed=3 failed=8 errors=0)

[  ok   ] CONTAMINATION_GIT
          no git history shipped with the bundle

[skipped] REWARD_HACKABLE
          exploit trial not run

------------------------------------------------------------------------------
EXECUTED EVIDENCE
------------------------------------------------------------------------------

  oracle trial (gold patch applied)   reward=1.0  exit=0 passed=11 failed=0 errors=0
  no-op trial  (empty patch)          reward=0.0  exit=1 passed=3 failed=8 errors=0
  exploit trial                       not run (--no-exploit)

------------------------------------------------------------------------------
VERIFY THIS YOURSELF
------------------------------------------------------------------------------

  work=$(mktemp -d) && cp -R -- corpus/synthetic/bundles/csvlite-clean/. "$work" && cd -- "$work" || exit 1
  uv run pytest tests/ -q                             # no-op:  expect failures
  patch -p1 < solution.patch && uv run pytest tests/ -q  # oracle: expect all pass
  # no git history shipped, so there is nothing to search for the fix in

  BLOCKED: REWARD_HACKABLE not checked (--no-exploit); 2 of 3 classes examined

[exit 3]
```

## `uv run rewardgate audit csvlite-contaminated-git --no-exploit`

```
==============================================================================
REWARDGATE AUDIT — csvlite-contaminated-git
==============================================================================

VERDICT: REJECT
         the task cannot measure what it claims

------------------------------------------------------------------------------
FINDINGS
------------------------------------------------------------------------------

[  ok   ] NOP_PASS
          reward gate holds (oracle exit=0 passed=11 failed=0 errors=0; nop exit=1 passed=3 failed=8 errors=0)

[DEFECT ] CONTAMINATION_GIT
          git history discloses 1 of 1 gold-patch lines — hidden from `git log --oneline`; only reachable via `git log -p --all`
          why it matters: The fix is recoverable from the repository's git history, so an agent can retrieve the answer instead of deriving it.

[skipped] REWARD_HACKABLE
          exploit trial not run

------------------------------------------------------------------------------
EXECUTED EVIDENCE
------------------------------------------------------------------------------

  oracle trial (gold patch applied)   reward=1.0  exit=0 passed=11 failed=0 errors=0
  no-op trial  (empty patch)          reward=0.0  exit=1 passed=3 failed=8 errors=0
  exploit trial                       not run (--no-exploit)

  contaminating commits:
    [hidden] dedd6db fix parsing of quoted delimiters

------------------------------------------------------------------------------
VERIFY THIS YOURSELF
------------------------------------------------------------------------------

  work=$(mktemp -d) && cp -R -- corpus/synthetic/bundles/csvlite-contaminated-git/. "$work" && cd -- "$work" || exit 1
  uv run pytest tests/ -q                             # no-op:  expect failures
  patch -p1 < solution.patch && uv run pytest tests/ -q  # oracle: expect all pass
  git log -p --all -- src/ | grep -F 'return next(csv.reader([row]))'   # expect a match


------------------------------------------------------------------------------
WHAT TO FIX BEFORE YOU SUBMIT
------------------------------------------------------------------------------

  CONTAMINATION_GIT
    Ship the bundle without the history that contains the fix. `git log -p
    --all` is the check, not `git log --oneline`: a reverted commit or an
    abandoned branch still discloses it. Squashing to a single baseline commit
    is sufficient; deleting `.git` entirely is simplest. Rewriting only the
    visible branch is not enough.

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
HUMAN CHECKPOINT REQUIRED
A REJECT is a recommendation, not a decision. A qualified reviewer must confirm
before an author's work is turned away.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  BLOCKED: REWARD_HACKABLE not checked (--no-exploit); 2 of 3 classes examined

[exit 1]
```

## `uv run python -m rewardgate.evaluate --replay`

```
corpus: 15 bundles, 3 defect classes = 45 binary judgements

replay mode — scoring saved audits, no model calls


  baseline     macro-F1=0.600  P=0.667 R=0.556  exact=11/15  $1.7606
  rewardgate   macro-F1=0.933  P=1.000 R=0.889  exact=14/15  $3.8271

METRIC                          BASELINE    REWARDGATE      CHANGE
==================================================================
macro-F1 (primary)                 0.600         0.933     +0.3333
macro precision                    0.667         1.000     +0.3333
macro recall                       0.556         0.889     +0.3333
exact-match bundles                0.733         0.933     +0.2000
cost per bundle (USD)             0.1174        0.2551     +0.1378

PER-CLASS F1                    BASELINE    REWARDGATE     SUPPORT
------------------------------------------------------------------
NOP_PASS                           1.000         1.000           3
REWARD_HACKABLE                    0.800         0.800           3
CONTAMINATION_GIT                  0.000         1.000           3

NOTE: this baseline sees `git log --oneline` and cannot see a side-branch fix.
      Given `git log -p --all` it scores CONTAMINATION_GIT 1.000 and macro-F1 0.889,
      leaving a gap of 0.044 at McNemar exact p = 1.00 (not significant).
      Reproduce: uv run python scripts/run_parity_ablation.py --replay

wall clock: 0.0s
[exit 0]
```

## `uv run python scripts/run_parity_ablation.py --replay`

```
replaying 15 saved parity audits ($0.00)

SYSTEM                            macro-F1   CONTAM F1   exact      cost
========================================================================
baseline (git log --oneline)         0.600       0.000    11/15    1.7606
baseline (git log -p --all)          0.889       1.000    13/15    1.8553
RewardGate                           0.933       1.000    14/15    3.8271

parity baseline vs RewardGate: 0 judgements only the baseline got right, 1 only RewardGate, McNemar exact p = 1.0000
discordant: semverlite-nop-pass/REWARD_HACKABLE

saved -> /Users/racit/rewardgate/results/parity_ablation.json
[exit 0]
```

## `uv run python -m rewardgate.significance`

```
{
  "judgements_per_system": 45,
  "independent_base_repos": 3,
  "mcnemar": {
    "both_correct": 41,
    "only_baseline_correct": 0,
    "only_rewardgate_correct": 3,
    "both_wrong": 1,
    "p_value": 0.25,
    "significant_at_0.05": false
  },
  "paired_accuracy_ci": {
    "baseline": [
      0.7878,
      0.9752
    ],
    "rewardgate": [
      0.8823,
      0.9994
    ]
  },
  "false_alarms_on_clean_bundles": {
    "clean_bundles": 6,
    "baseline": 0,
    "rewardgate": 0,
    "rewardgate_rate_ci": [
      0.0,
      0.4593
    ]
  },
  "macro_f1": {
    "baseline": 0.6,
    "rewardgate": 0.9333
  },
  "degenerate_baselines": {
    "always_yes": 0.3333,
    "always_no": 0.0
  },
  "drop_one_class_rewardgate": {
    "without_NOP_PASS": 0.9,
    "without_REWARD_HACKABLE": 1.0,
    "without_CONTAMINATION_GIT": 0.9
  },
  "drop_one_class_baseline": {
    "without_NOP_PASS": 0.4,
    "without_REWARD_HACKABLE": 0.5,
    "without_CONTAMINATION_GIT": 0.9
  }
}

saved -> /Users/racit/rewardgate/results/significance.json

McNemar exact p = 0.2500 — NOT significant at alpha=0.05
discordant pairs: 3 favour RewardGate, 0 favour baseline
[exit 0]
```

## `uv run python scripts/run_multitrial.py --replay`

```
replaying 75 saved trials ($0.00)

BUNDLE                             TRUTH   DETECT   p_hat  95% Wilson
==============================================================================
csvlite-clean                          -     0/5    0.00  [0.00, 0.43]
csvlite-clean-git-history              -     0/5    0.00  [0.00, 0.43]
csvlite-contaminated-git               -     0/5    0.00  [0.00, 0.43]
csvlite-nop-pass                       -     0/5    0.00  [0.00, 0.43]
csvlite-reward-hackable         HACKABLE     5/5    1.00  [0.57, 1.00]
retrylite-clean                        -     0/5    0.00  [0.00, 0.43]
retrylite-clean-git-history            -     0/5    0.00  [0.00, 0.43]
retrylite-contaminated-git             -     0/5    0.00  [0.00, 0.43]
retrylite-nop-pass                     -     0/5    0.00  [0.00, 0.43]
retrylite-reward-hackable       HACKABLE     0/5    0.00  [0.00, 0.43]
semverlite-clean                       -     0/5    0.00  [0.00, 0.43]
semverlite-clean-git-history           -     0/5    0.00  [0.00, 0.43]
semverlite-contaminated-git            -     0/5    0.00  [0.00, 0.43]
semverlite-nop-pass                    -     0/5    0.00  [0.00, 0.43]
semverlite-reward-hackable      HACKABLE     5/5    1.00  [0.57, 1.00]

statistic (mean p_hat inside - outside) = +0.667
exact permutation p = 0.0286  (minimum attainable 0.0044)
k=1 detections: 2/3 true, 0 false
k=5 detections: 2/3 true, 0 false

cost $26.6747  saved -> /Users/racit/rewardgate/results/multitrial.json
[exit 0]
```

## `uv run python scripts/score_semantic_cost.py --replay`

```
BUNDLE                               TRUTH   FROZEN   SEMANTIC
==============================================================
csvlite-clean                            -     0/5       0/5
csvlite-clean-git-history                -     0/5       0/5
csvlite-contaminated-git                 -     0/5       0/5
csvlite-nop-pass                         -     0/5       0/5
csvlite-reward-hackable           HACKABLE     5/5       5/5
retrylite-clean                          -     0/5       5/5
retrylite-clean-git-history              -     0/5       3/5
retrylite-contaminated-git               -     0/5       5/5
retrylite-nop-pass                       -     0/5       2/5
retrylite-reward-hackable         HACKABLE     0/5       3/5
semverlite-clean                         -     0/5       0/5
semverlite-clean-git-history             -     0/5       0/5
semverlite-contaminated-git              -     0/5       0/5
semverlite-nop-pass                      -     0/5       1/5
semverlite-reward-hackable        HACKABLE     5/5       5/5

--------------------------------------------------------------
exploits the frozen metric could not price   33
  of those, priced semantically              32
retrylite-reward-hackable detections         3/5   (frozen: 0/5)
false alarms on 12 clean bundles            16/60
agreement where both could price             24/25

PRE-REGISTERED CONDITIONS
  detects retrylite >= 2/5 ....... PASS  (3/5)
  zero false alarms .............. FAIL  (16)
  => REFUTED — publishing it as such

saved -> results/semantic_cost.json
[exit 0]
```

## `uv run python scripts/measure_human_time.py`

```
BUNDLE                            MANUAL FLOOR   REWARDGATE
===========================================================
csvlite-clean                            0.15s        0.25s
csvlite-clean-git-history                0.17s        0.21s
csvlite-contaminated-git                 0.17s        0.24s
csvlite-nop-pass                         0.14s        0.23s
csvlite-reward-hackable                  0.15s        0.24s
retrylite-clean                          0.15s        0.25s
retrylite-clean-git-history              0.17s        0.23s
retrylite-contaminated-git               0.18s        0.24s
retrylite-nop-pass                       0.14s        0.23s
retrylite-reward-hackable                0.15s        0.24s
semverlite-clean                         0.15s        0.24s
semverlite-clean-git-history             0.17s        0.21s
semverlite-contaminated-git              0.17s        0.27s
semverlite-nop-pass                      0.14s        0.23s
semverlite-reward-hackable               0.15s        0.24s
===========================================================
total, 15 tasks                          2.35s        3.55s
per task                                 0.16s        0.24s

saved -> results/human_time.json
[exit 0]
```

