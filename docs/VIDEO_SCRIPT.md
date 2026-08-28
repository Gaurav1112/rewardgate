# Solution Video — 5 minute script

Target 4:50, leaving margin under the 5:00 limit. Screen recording with voice-over. Every number spoken is on screen.

---

## 0:00–0:45 — The problem

> "If you author benchmark tasks for an AI lab, you're paid per accepted task. You find out a task
> is broken days later, when a reviewer rejects it. And the base rate of broken is not small —
> OpenAI audited their own SWE-bench tasks and found sixty-eight percent had to be filtered out.
> Thirty-eight percent had underspecified problem statements. Sixty-one percent had tests that
> unfairly fail valid solutions. They retired SWE-bench Verified in 2026 over it."

**Screen:** the OpenAI audit page, then the retirement post. Highlight 68.3% / 38.3% / 61.1%.

> "So the question I'm answering is: can I run the reviewer's gate *before* I submit?"

---

## 0:45–1:30 — The baseline, and why it fails

> "The obvious approach is what the brief suggests: one prompt. Paste the task in, ask if it's
> sound. Here it is on fifteen tasks."

**Screen:** `results/baseline_audits.json`, then the score line.

> "Macro-F1 zero-point-five-two-four. Nine out of fifteen exactly right. This is not a straw man —
> a careful reader solves much of this. Look at the per-class row: on NOP_PASS it scores a perfect
> one-point-zero, same as my system. A test that only asserts a module imports is visibly
> inadequate on the page."

**Screen:** highlight the CONTAMINATION_GIT row — baseline **0.000**.

> "But contamination: zero. It missed all three contaminated tasks — while correctly passing all
> three clean-history controls. It sees git log --oneline, which is innocent, because the fix is on
> a side branch. That is not a reading problem. It needs a command."

---

## 1:30–2:45 — One realistic execution, start to finish

> "Here's RewardGate on a single task. Watch the reward gate first — the check the whole field
> runs. Apply the gold patch: tests pass, reward one-point-zero. Apply an empty patch: tests fail,
> reward zero. By every mechanical criterion in use today, this task is valid."

**Screen:** live `run_reward_gate` output — oracle 1.0, nop 0.0, `gate_holds=True`.

> "It isn't. Now the exploit agent. It gets a hostile brief — make the visible tests pass without
> fixing the bug — a sandboxed copy, and tools limited to reading, editing, and running pytest.
> The held-out tests and the git history are deleted before it starts."

**Screen:** scroll the trajectory: reads instruction, reads the single test, writes the patch.

```python
if row == 'a,"b,c"':
    return ["a", "b,c"]
return row.split(",")
```

> "Three lines. Now the adjudication, and this is the whole project in one frame."

**Screen:** visible suite `exit=0 passed=4` in green; held-out `exit=1 failed=1` in red.

> "The visible suite is green. The held-out suite is red. This task would certify an agent as
> correct while the bug it tests for is untouched — and the reward gate passed it."

---

## 2:45–3:30 — The measured comparison

**Screen:** the comparison table.

> "Same fifteen tasks, same schema, same scorer. Macro-F1 zero-point-five-two-four to
> zero-point-nine-three-three — up seventy-eight percent. Exact-match nine of fifteen to fourteen
> of fifteen. Five dollars fifty-five for the whole run."

> "And where it comes from matters more than the headline. NOP_PASS is a tie. The entire gap is
> contamination, zero to one, and reward hacking. My system wins exactly where a verdict needs a
> command run, and nowhere else. It also costs a hundred and nineteen percent more per task."

---

## 3:30–4:20 — Biggest contributor, and the finding I withdrew

> "The change that contributed most wasn't code. My first exploit detector flagged the *clean*
> task too — a hundred percent false positives — because any finite visible test suite can be
> hardcoded if you write enough branches. 'An exploit exists' isn't a discriminating property."

> "I regraded on exploit *cost*: how many literals the exploit has to special-case. False positives
> went to zero out of three. Same agent, same corpus, same code — only the definition changed."

**Screen:** the changelog table, before and after.

> "And a finding I withdrew. I originally reported that the baseline contradicted itself and
> flagged everything. That was my bug. `bool` of the string `false` is `True` in Python, and my own
> prompt asked for a string. Every negative verdict inverted before scoring. The model was right;
> my parser wasn't. An adversarial audit caught it, I fixed it, re-ran, and the improvement dropped
> from a hundred and thirty-three percent to seventy-eight."

> "This project exists to catch results that pass every check while measuring nothing. I produced
> one about my own work."

---

## 4:20–4:50 — Hot take and reproduction

> "The hot take: reward-hackability is a property of the evaluation protocol, not of the individual
> task. With eight varied test inputs, the agent chose to genuinely fix the bug *even though I told
> it to cheat* — hardcoding eight cases cost more than writing the real implementation. Test-input
> diversity is the defence, and you can measure it before you ship."

> "And I checked my own work against someone else's. My leakage detector measures a hundred and
> thirty-three of five hundred SWE-bench instances leaking the gold file path. An independent paper
> reports a hundred and thirty-five. Two apart, on a corpus I didn't build."

**Screen:** `uv run python -m rewardgate.evaluate --replay` finishing.

> "Replay mode re-scores the saved audits offline. No API key, no cost. You can check the number
> without paying to regenerate it."

---

## Recording notes

- Pre-build the corpus and pre-fetch the dataset; do not record `uv sync`.
- The 1:30–2:45 execution is the segment worth re-taking until clean. Everything else is narration.
- Show the held-out red / visible green frame for a full two seconds. That frame is the argument.
- Do not speed up the exploit-agent run; the real ~60s pace is more convincing than a time-lapse.
