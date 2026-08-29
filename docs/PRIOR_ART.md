# Prior art, and what is different here

Summarised in the README; this is the full version, including the pieces that cut against this
project.

**Two pieces of prior art I had cited in my own design spec and then left out of this section.**
An adversarial review caught the omission, and it matters because both are closer to this project
than anything else listed below.

* **[arXiv:2606.16062](https://arxiv.org/abs/2606.16062), *Auditing Reward Hackability in Code RL
  Training Environments*.** Per-task auditing of code-RL environments, a Docker-verified
  incorrect-patch pipeline, and an oracle "gold-sanity gate". That is this project's stated framing
  almost exactly. I cited it in `docs/specs/` for its 28.5% figure and never brought it into the
  comparison.
* **[RewardHackBench](https://github.com/islo-labs/reward-hack-bench).** Its contributor workflow
  already mandates "oracle + nop smoke tests — oracle must succeed and the nop must fail". That is
  the reward gate, as a documented submission requirement, before this project existed.

So the reward gate is not novel, and neither is per-task auditing of RL environments. What I have
not found published is the pair that does the actual work here: **adjudicating an exploit
mechanically by held-out execution with no human in the loop** (Terminal-Bench uses author
inspection), and **grading on exploit *cost* — the count of literal special-cases — rather than on
whether an exploit exists at all.** The second is what turned a detector with a 100% false-positive
rate into one with zero false alarms across six clean bundles.

**The closest prior art is Terminal-Bench 2.0** ([arXiv:2601.11868](https://arxiv.org/abs/2601.11868)),
and the overlap is substantial enough that it needs stating first rather than buried. Its §2.3 and
Appendix B describe a pre-merge task QA pipeline that already runs, verbatim:

> "an automated workflow ran the task's oracle solution to ensure solvability… other checks
> verified the absence of common failure modes (e.g., a no-op 'dummy' agent should fail the task)."

> "**B.4 Adversarial Exploit Agent.** During task auditing, we run an adversarial exploit agent to
> attempt to pass the tests by cheating without actually looking at the tests and oracle solutions."

That is oracle + no-op + adversarial exploit agent + git-history hygiene, run by the contributor
before merge. **It is this project's core loop, published first.** Anyone assessing this work
should know that before reading further.

What is actually different, and it is narrower than "a new idea":

1. **Terminal-Bench adjudicates its exploit agent by human inspection** ("manually inspected and
   verified by an author"). Here adjudication is mechanical — held-out execution — so it needs no
   reviewer in the loop to decide whether an exploit counts.
2. **Its git check is an LLM lint over the Dockerfile.** This runs `git log -p --all` matched
   against gold-patch lines, which is what catches a fix parked on a side branch.
3. **Detection rates for this pipeline *have* been published — I was wrong to imply otherwise.**
   *Hardening Agent Benchmarks with Adversarial Hacker-Fixer Loops*
   ([arXiv:2606.08960](https://arxiv.org/abs/2606.08960)) reports **323 of 1,968 tasks (16%)
   hackable across five benchmarks, including 13/89 of Terminal-Bench 2.0**, and
   *Terminal Wrench* ([arXiv:2604.17596](https://arxiv.org/abs/2604.17596)) ships 331
   reward-hackable environments with 3,632 exploit trajectories. What is still different here is
   narrower: those papers measure **how many tasks are hackable**; this measures **the detector** —
   with clean negative controls, a reported false-alarm rate, and a significance test that comes
   back negative.
4. **Exploit *cost* rather than exploit *existence*.** Terminal-Bench flags that a cheat was found.
   Grading on existence gave a 100% false-positive rate here; counting how many literals the cheat
   must special-case is what made the signal usable. I could not find prior work formalising this.

Also relevant: **SpecBench** ([arXiv:2605.21384](https://arxiv.org/abs/2605.21384)) uses the same
visible-versus-held-out pass-rate gap, though to grade agents rather than tasks.
**BenchJack** ([arXiv:2605.12673](https://arxiv.org/abs/2605.12673)) is an automated red-teaming
system that drives coding agents to audit benchmarks, extended into a discover-and-patch loop:
219 flaws found, hackable-task ratio driven from ~100% to under 10% on the four benchmarks without
fatal design flaws (10 were audited). That is substantially more than "bulk research", and an
earlier draft of this section understated it. **SWE-Bench+**
([arXiv:2410.06992](https://arxiv.org/abs/2410.06992)) and **UTBoost**
([arXiv:2506.09289](https://arxiv.org/abs/2506.09289)) precede the leakage and weak-assertion
checks. The **ABC** paper ([arXiv:2507.02825](https://arxiv.org/abs/2507.02825)) gives the
checklist this implements an executable subset of.

**A finding that cuts against this project's design:** **EvilGenie**
([arXiv:2511.21654](https://arxiv.org/abs/2511.21654)) reports that an LLM judge detected reward
hacking *highly effectively*, while held-out tests added little lift. This project bets the
opposite way — execution over judgement — on the basis of the 18.5% evaluator-misalignment figure.
Both can be true in different regimes, and I have not tested an LLM judge here, so treat the
anti-judge stance as a design choice with contrary evidence rather than a settled result.
