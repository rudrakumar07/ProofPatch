#!/usr/bin/env bash
# Recreate the deterministic demo fixture git repository.
# The fixture's own .git directory is intentionally NOT committed to this repo;
# run this once after cloning so ProofPatch has a clean Git repository to verify.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$ROOT/fixtures/python-session-bug"

if [ -d "$FIXTURE/.git" ]; then
  echo "[ProofPatch] fixture git repo already exists at $FIXTURE/.git"
  exit 0
fi

echo "[ProofPatch] initializing fixture git repo at $FIXTURE"
git -C "$FIXTURE" init -q .
git -C "$FIXTURE" config user.email "demo@proofpatch.local"
git -C "$FIXTURE" config user.name "ProofPatch Demo"
git -C "$FIXTURE" add -A
git -C "$FIXTURE" commit -qm "Initial commit: payment session fixture with known boundary bug"
git -C "$FIXTURE" log --oneline -1
echo "[ProofPatch] fixture repo ready."
