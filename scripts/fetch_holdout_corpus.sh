#!/usr/bin/env bash
# Fetch SWE-Gym, the held-out third-party corpus.
#
# The headline finding — 42% of SWE-bench Verified trips at least one defect check — is measured on
# a corpus somebody else built, which is what makes it non-circular. But it is still ONE corpus, and
# "42% of SWE-bench Verified" and "42% of agentic coding benchmarks" are different claims.
#
# SWE-Gym is drawn from a different set of repositories and has ZERO instance overlap with
# SWE-bench Verified (asserted in tests/test_holdout_corpus.py, not assumed). Running the same four
# deterministic checkers over it tests whether the rate is a property of the detectors, of Verified,
# or of the way these benchmarks get built.
#
# Deliberately NOT SWE-bench Lite: 93 of its 300 instances are also in Verified, so calling it
# independent would be false.
set -euo pipefail

DEST="${1:-corpus/real/raw}"
FILE="$DEST/swegym_train.parquet"
URL="https://huggingface.co/datasets/SWE-Gym/SWE-Gym/resolve/main/data/train-00000-of-00001.parquet"
SHA256="60569cea74bb281f7a5579467436a2bc1932c6e0c5f2f7fa0d084392abd9ad97"

mkdir -p "$DEST"

if [[ -f "$FILE" ]] && shasum -a 256 "$FILE" | grep -q "$SHA256"; then
  echo "SWE-Gym already present and verified: $FILE"
  exit 0
fi

echo "Fetching SWE-Gym (2,438 instances, ~44 MB)..."
curl -fL --progress-bar "$URL" -o "$FILE"

if ! shasum -a 256 "$FILE" | grep -q "$SHA256"; then
  echo "CHECKSUM MISMATCH — refusing to continue." >&2
  echo "  expected: $SHA256" >&2
  echo "  got:      $(shasum -a 256 "$FILE" | cut -d' ' -f1)" >&2
  rm -f "$FILE"
  exit 1
fi

echo "Verified. Now run: uv run python -m rewardgate.report_real --holdout"
