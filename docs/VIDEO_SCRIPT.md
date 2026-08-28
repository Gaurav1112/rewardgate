# Solution Video — 5 minute script

Target 4:40, leaving margin. Screen recording with voice-over. Every number spoken is on screen.

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
> sound. Here it is on twelve tasks."

**Screen:** `results/baseline_audits.json`, then the score line.

> "Recall one-point-zero. Looks perfect — until you see precision zero-point-two-five and
> exact-match zero out of twelve. It flagged every defect on every task, including all three clean
> ones. It never once said a task was fine."

**Screen:** highlight the self-contradiction — `CONTAMINATION_GIT: true` beside evidence reading
*"No git history is shipped with the bundle."*

> "It contradicted itself inside one response. A reviewer's tool that rejects everything isn't
> cautious. It's useless — you still have to do the whole review by hand."

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

> "Same twelve tasks, same output schema, same scorer. Macro-F1 zero-point-four to
> zero-point-nine-three-three — up a hundred and thirty-three percent. But the gain isn't recall;
> the baseline already had perfect recall. It's precision — zero-two-five to one-point-zero.
> Exact-match zero out of twelve to eleven out of twelve. Four dollars forty-nine for the whole
> run."

> "And the honest part: RewardGate costs a hundred and twenty-three percent more per task, and
> recall dropped eleven percent from one miss."

---

## 3:30–4:10 — Biggest contributor, and the experiment I removed

> "The change that contributed most wasn't code. My first exploit detector flagged the *clean*
> task too — a hundred percent false positives — because any finite visible test suite can be
> hardcoded if you write enough branches. 'An exploit exists' isn't a discriminating property."

> "I regraded on exploit *cost*: how many literals the exploit has to special-case. False positives
> went to zero out of three. Same agent, same corpus, same code — only the definition changed."

**Screen:** the changelog table, before and after.

> "And the experiment I removed: one agent per defect class. It looks thorough. But for
> contamination, `git log -p --all` returns a commit SHA for zero dollars, while an LLM returns an
> opinion for nineteen cents. I deleted four agents. Fewer agents, stronger evidence."

---

## 4:10–4:40 — Hot take and reproduction

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
