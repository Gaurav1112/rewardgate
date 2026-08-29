#!/usr/bin/env bash
# Fetches the real held-out corpus: SWE-bench Verified (500 instances, text only, ~2.0 MB).
#
# This corpus is NOT authored by this project. It is the third-party ground truth used to
# demonstrate that RewardGate's detectors are not tuned to defects the author planted.
#
# Licence: The SWE-bench harness is MIT-licensed by Princeton NLP. The dataset card carries no explicit
# licence tag, and instances derive from their upstream projects' licences -- see LICENSE.
# Source:  https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified
set -euo pipefail

DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/corpus/real/raw"
FILE="$DEST/swebench_verified.parquet"
URL="https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/resolve/main/data/test-00000-of-00001.parquet"
SHA256="a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd"

mkdir -p "$DEST"

if [[ -f "$FILE" ]] && shasum -a 256 "$FILE" | grep -q "$SHA256"; then
  echo "corpus already present and checksum matches: $FILE"
  exit 0
fi

echo "downloading SWE-bench Verified (~2.0 MB)..."
curl -fsSL -o "$FILE" "$URL"

echo "verifying checksum..."
if ! shasum -a 256 "$FILE" | grep -q "$SHA256"; then
  echo "CHECKSUM MISMATCH — refusing to continue." >&2
  echo "  expected: $SHA256" >&2
  echo "  actual:   $(shasum -a 256 "$FILE" | cut -d' ' -f1)" >&2
  exit 1
fi

echo "ok: $FILE"
