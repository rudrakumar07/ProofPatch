#!/usr/bin/env bash
# One-command demo: reset, then run the full ProofPatch verification against the
# deterministic fixture and print the proof report location.
#
# ProofPatch v0.1 uses the Cline SDK as its only LLM integration. The Cline
# account is auto-discovered from ~/.cline; you may also set
# PROOFPATCH_CLINE_API_KEY / PROOFPATCH_CLINE_MODEL_ID in .env (see .env.example).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"

if [ ! -x "$VENV/bin/proofpatch" ]; then
  echo "Missing $VENV/bin/proofpatch. Run 'make setup' first." >&2
  exit 1
fi

# The fixture's repro command is 'pytest ...', so make sure the venv binaries
# (pytest, python) are first on PATH. The Cline bridge needs node on PATH too.
export PATH="$VENV/bin:$PATH"

"$ROOT/scripts/reset_demo.sh"

echo
echo "[ProofPatch] running verification on the demo fixture"
echo

set +e
"$VENV/bin/proofpatch" verify \
  --repo "$ROOT/fixtures/python-session-bug" \
  --issue "$ROOT/fixtures/python-session-bug/bug.md" \
  --repro "pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry" \
  --timeout 300
CODE=$?
set -e

echo
echo "[ProofPatch] exit code: $CODE  (0=VERIFIED 2=NEEDS_REVIEW 3=REJECTED 4=ERROR)"
echo "[ProofPatch] read the report with: $VENV/bin/proofpatch report --run <run_id>"
exit "$CODE"
