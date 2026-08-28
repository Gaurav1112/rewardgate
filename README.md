# RewardGate

Audits a candidate benchmark / RL-environment task **before** it enters a training corpus — and
proves defects by execution rather than by opinion.

> Status: in development for the micro1 Agentic Workflows Hackathon (closes 2026-08-31 18:00 UTC).
> This README is a stub; the full write-up, improvement changelog and measured results land before
> submission.

See [`docs/specs/2026-08-28-rewardgate-design.md`](docs/specs/2026-08-28-rewardgate-design.md) for
the design.

## Quick check

```bash
uv sync
./scripts/fetch_real_corpus.sh     # ~2.0 MB, checksum-pinned
uv run pytest -q
```
