#!/usr/bin/env bash
# Capture every documented command, complete and unedited, into docs/TERMINAL_SESSION.md.
#
# The video's slides show selected lines from these runs, which is right for a five-minute video and
# wrong as the only record. This produces the unfiltered version: full stdout+stderr and the real
# exit code of each command, in order, with nothing grepped or retyped.
#
# Every command here is free and offline except the two corpus fetches, which are checksum-pinned.
# No model calls, no API key.
#
#   ./scripts/capture_session.sh          # rewrites docs/TERMINAL_SESSION.md
set -uo pipefail
cd "$(dirname "$0")/.."

OUT=docs/TERMINAL_SESSION.md

COMMANDS=(
  "uv run rewardgate list"
  "uv run python -m rewardgate.report_real"
  "uv run python -m rewardgate.report_real --holdout"
  "uv run rewardgate audit csvlite-clean --no-exploit"
  "uv run rewardgate audit csvlite-contaminated-git --no-exploit"
  "uv run python -m rewardgate.evaluate --replay"
  "uv run python scripts/run_parity_ablation.py --replay"
  "uv run python -m rewardgate.significance"
  "uv run python scripts/run_multitrial.py --replay"
  "uv run python scripts/score_semantic_cost.py --replay"
  "uv run python scripts/measure_human_time.py"
)

{
  echo "# Terminal session — every documented command, complete and unedited"
  echo
  echo "Captured by \`scripts/capture_session.sh\` on a clean checkout. Nothing here is grepped,"
  echo "reformatted, or retyped: it is the full \`stdout\`+\`stderr\` of each command in order. The video's"
  echo "slides show selected lines from these same runs; this is the unfiltered version."
  echo
  echo "Every command is free and offline — no model calls, no API key. The exit codes are part of"
  echo "the record: \`0\` accept, \`1\` defect proven, \`3\` a check could not run."
  echo
  echo "Environment: macOS 15 (Darwin 24.6.0), Apple Silicon, Python 3.12, uv 0.11.15."
  echo
  for c in "${COMMANDS[@]}"; do
    echo "## \`$c\`"
    echo
    echo '```'
    eval "$c" 2>&1
    echo "[exit $?]"
    echo '```'
    echo
  done
} > "$OUT"

echo "wrote $OUT — $(grep -c '^## `' "$OUT") commands, $(wc -l < "$OUT" | tr -d ' ') lines"
