#!/usr/bin/env bash
# Reset the demo environment: remove run artifacts, prune stray worktrees, and
# make sure the fixture repository is clean and at its original commit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$ROOT/fixtures/python-session-bug"

echo "[ProofPatch] clearing run artifacts in $ROOT/.proofpatch"
rm -rf "$ROOT/.proofpatch"

echo "[ProofPatch] pruning fixture worktrees"
git -C "$FIXTURE" worktree prune >/dev/null 2>&1 || true

echo "[ProofPatch] cleaning fixture working tree"
rm -rf "$FIXTURE/.proofpatch" "$FIXTURE/.pytest_cache" "$FIXTURE/.proofpatch_generated_tests"
find "$FIXTURE" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# Remove any leftover run worktrees that may have been created inside the repo.
if [ -d "$FIXTURE/.proofpatch/runs" ]; then
  rm -rf "$FIXTURE/.proofpatch"
fi

echo "[ProofPatch] fixture status:"
git -C "$FIXTURE" status --porcelain
echo "[ProofPatch] reset complete."
