# ProofPatch

**Do not merely say that a patch works. Show evidence that it works.**

ProofPatch is an evidence-backed verification layer for AI-generated code. A developer
supplies a repository and a bug report; ProofPatch inspects the repo, generates a
candidate patch, generates independent verification tests, runs objective checks on
both the original and patched code, and emits a human-readable **Proof Report** with
the evidence for or against the patch.

> ProofPatch v0.1 is Cline SDK powered: every LLM call in the pipeline runs through the
> [Cline SDK](https://docs.cline.bot/sdk) agent runtime (see
> [the Cline SDK section](#llm-integration-the-cline-sdk)).

> ProofPatch v0.1 is a local developer prototype. Verification commands execute
> repository code on the developer's machine. Use only repositories you trust.

The v0.1 prototype targets **Python** projects in **Git** repositories and is built
as a monorepo: a Python verification **engine**, a **FastAPI** API, a **React + Vite**
dashboard, and a deterministic demo **fixture**.

---

## Quickstart

Requirements: Python 3.10+, Node 22+, Git, `pytest` (installed with the engine).

```bash
make setup          # create .venv, install Python + JS + Cline bridge deps
make test           # 109 engine + API tests (offline, stub provider)
make demo           # run the full fixture demo end-to-end (Cline SDK powered)
```

Expected `make demo` result:

```text
✓ Original issue reproduction established
✓ Candidate resolves explicit reproduction
✓ Generated bug-specific differential evidence
✓ Existing regression suite introduces no new failures
✓ Static/syntax verification introduces no new findings
✓ Patch safety/size policy passes

Evidence score: 100 / 100
Verdict: VERIFIED — Ready for human review
```

## Usage

### CLI (primary integration point for Cline and other coding assistants)

```bash
# from the repo root, with PATH including .venv/bin
proofpatch verify \
  --repo /path/to/repo \
  --issue bug.md \
  --repro "pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry"

proofpatch verify --issue-text "Payments succeed exactly at expires_at." --repo /path --repro "..."
proofpatch report --run pp_01JABCDEF...   # print a stored report
```

Exit codes: `0` = VERIFIED, `2` = NEEDS_REVIEW, `3` = REJECTED, `4` = ERROR.

### API + dashboard

```bash
uvicorn proofpatch_api.main:app --port 8000
# Dashboard (built) → http://127.0.0.1:8000/
# Health            → http://127.0.0.1:8000/health
```

For frontend development:

```bash
make web            # Vite at http://127.0.0.1:5173, proxies /api → :8000
```

API examples:

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"repository":{"path":"/path/to/repo"},"issue":{"title":"..."},"verification":{}}'
curl http://127.0.0.1:8000/api/runs/<run_id>/report.md
```

## How it works

```
React dashboard ──HTTP/SSE──▶ FastAPI API ──▶ Orchestrator
                                                   ├─► LLM subsystem (analyzer / patch / test agents)
                                                   └─► deterministic verification subsystem
                                                         command runner · pytest adapter · patch
                                                         validator · evidence engine · report builder
                                                       ▼
                                            isolated Git worktrees (baseline / candidate)
```

**Core rule: AI proposes; deterministic tooling executes; the evidence engine compares.** The
LLM may suggest a root cause, a patch, or tests — it can never set `VERIFIED`, award points,
or fabricate command results. The patch touches only the isolated candidate worktree; the
source branch is never modified.

Evidence scoring (deterministic weights, skipped checks contribute 0 and are not renormalized):

| Evidence | Weight |
|---|---:|
| Original issue reproduction established | 20 |
| Candidate resolves explicit reproduction | 20 |
| Generated bug-specific differential evidence | 25 |
| Existing regression suite introduces no new failures | 20 |
| Static/syntax verification introduces no new findings | 10 |
| Patch safety/size policy passes | 5 |

## LLM integration: the Cline SDK

ProofPatch v0.1 has **exactly one** LLM integration — the [Cline SDK](https://docs.cline.bot/sdk)
(`@cline/sdk`), the same agent harness that powers Cline. The engine is Python and the SDK is
TypeScript, so a small Node bridge (`packages/cline-bridge`) runs one single-shot agent turn and
returns JSON.

```bash
cd packages/cline-bridge && npm install
proofpatch doctor     # verifies node, the bridge, credentials, and the model
```

Configuration (`.env`, see `.env.example`):

```text
PROOFPATCH_CLINE_PROVIDER_ID=openai-compatible
PROOFPATCH_CLINE_BASE_URL=https://api.cline.bot/api/v1
PROOFPATCH_CLINE_MODEL_ID=anthropic/claude-sonnet-5.5
PROOFPATCH_CLINE_API_KEY=...
```

If the machine is signed in with Cline, the token and model are **auto-discovered** from
`~/.cline/data/settings/providers.json`, so no explicit configuration is needed.

**Trust boundary:** the bridge always runs the agent with `tools: []`, so the model can only
*return text*. It can never read, edit, or execute anything in the repository under
verification — every command ProofPatch runs is chosen by deterministic code.

Because free-text is not a structured output API, the provider appends a strict JSON contract to
the system prompt, parses the reply with `extract_json`, validates it against the Pydantic schema,
and retries once with the validation error (per the plan's LLM rules).

For tests, the engine exposes an injectable provider seam (`Orchestrator(provider=...)`);
tests use an offline stub so the suite never spends money or needs a network.
Copy `.env.example` to `.env` to configure credentials (never commit `.env`).

Real-world validated: ProofPatch produced a **VERIFIED 100/100** run against
`Textualize/rich` at `v13.7.0` for issue #3299 (`Segment._split_cells` wide-character
bug) — a minimal 1-line patch, generated differential tests, 0 new regressions across
the project's suite, source repo untouched. See `IMPLEMENTATION_NOTES.md` (§12–§18).

## Project layout

```text
proofpatch/
├─ apps/api/                 FastAPI (run service, SQLite, SSE, artifacts)
├─ apps/web/                 React + Vite + TypeScript dashboard
├─ packages/engine/          independent verification engine + CLI
├─ packages/cline-bridge/    Node bridge to the Cline SDK agent runtime
├─ fixtures/python-session-bug/  deterministic demo fixture (payment session bug)
├─ scripts/                  dev.sh / demo.sh / reset_demo.sh
└─ stage1plan.md             the implementation plan this prototype follows
```

Each run leaves a self-contained directory at `<data_dir>/runs/<run_id>/` containing
`run.json`, `issue.json`, `root_cause.json`, `patch.json`, `candidate.diff`,
`generated_tests/manifest.json`, `commands/*`, `verification.json`, `report.json`,
`report.md`, and `events.jsonl`.

## Testing

```bash
make test                    # engine + API suites (offline, stub provider)
.venv/bin/ruff check packages/engine apps/api
```

The key integration test runs the complete orchestrator against the fixture with the offline stub
provider and asserts `VERIFIED` plus a full artifact set. Live Cline SDK runs are exercised by
`make demo` and `proofpatch verify`. See `IMPLEMENTATION_NOTES.md` for the
smallest-compatible deviations from the plan discovered during the build.
