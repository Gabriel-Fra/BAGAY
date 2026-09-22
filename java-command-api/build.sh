#!/usr/bin/env bash
# Compile and run the parity check with nothing but a JDK (17+; written and
# tested against OpenJDK 21). No Maven, no network, no dependencies -- see
# README.md for why.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf out
mkdir -p out
javac -d out $(find src/main/java -name '*.java') $(find src/test/java -name '*.java')

VECTORS="${1:-../hash_vectors.json}"
if [ ! -f "$VECTORS" ]; then
  echo "No vectors file at $VECTORS."
  echo "Generate one first: python -m tools.export_hash_vectors hash_vectors.json"
  echo "(run from the repo root, with the project's real dependencies installed)"
  exit 1
fi

java -cp out bagay.chain.ParityCheck "$VECTORS"
