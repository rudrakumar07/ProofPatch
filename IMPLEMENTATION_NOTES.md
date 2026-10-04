# Implementation Notes

Per stage1plan.md §56, deviations from the plan are documented here as the
smallest compatible change that keeps the MVP working. Nothing below broadens
scope, adds languages, adds infrastructure, or replaces deterministic checks
with LLM judgement.

## 1. pydantic floor raised on new interpreters

The environment runs Python 3.15. The latest stable `pydantic` (2.13.x) pins
`pydantic-core==2.46.x`, which ships no `cp315` wheel, and the machine has no
Rust toolchain to build it. The first release pair with `cp315` wheels is
`pydantic==2.14.0b1` / `pydantic-core==2.48.0`.

- `packages/engine/pyproject.toml` depends on `pydantic>=2.14.0b1`.
- The constraint asks for a pre-release *only* when no newer release qualifies
  (pip resolves pre-releases only if the specifier names one), so the engine
  upgrades cleanly to future stable `pydantic` once it publishes `cp315` wheels.
- `sqlmodel` was dropped in favour of plain **SQLAlchemy** (explicitly allowed by
  the plan) to avoid its older hard pydantic pins. FastAPI, uvicorn, SQLAlchemy
  and ruff all have `cp315` wheels, so nothing else needed a source build.

## 2. `data_dir` is resolved to an absolute path at settings load

`RepositoryManager` passes worktree target paths to `git -C <repo>`, which
resolves relative paths against the *target repository*, not the ProofPatch
process. A relative `PROOFPATCH_DATA_DIR=.proofpatch` therefore created
worktrees inside the repository under test. `Settings` now resolves `data_dir`
to an absolute path via `_resolve_paths()`. This still defaults to
`.proofpatch` under the process working directory.

## 3. Python commands use `sys.executable`, not bare `python`

`python` may not exist (or may point elsewhere) on the machine, and the command
runner inherits the launching shell's `PATH`. The adapter therefore emits
`sys.executable -m pytest ...` / `sys.executable -m compileall ...` so the same
interpreter that runs ProofPatch executes the checks. The CLI demo script puts
`.venv/bin` first on `PATH` so the documented `pytest ...` repro command works,
exactly as the plan shows.

## 4. Context fallback keys off "no *source* file matched"

Step 4 of context selection adds project metadata (`pyproject.toml`). When only
metadata was selected, the Phase 8 exit criterion ("must include the buggy
source file") failed because the fallback tested "nothing selected". The
fallback now triggers when no `.py` source file was selected.

## 5. Suite "ran" requires at least one collected test

`suite_ran` in the evidence engine is
`baseline_tests is not None and baseline_tests.ran and baseline_tests.total > 0`.
A zero-test collection is reported as *skipped* (not passed) and caps the run
at `NEEDS_REVIEW`, per the plan's "test suite missing" rule.

## 6. Missing reproduction command caps at `NEEDS_REVIEW` under the fixed weights

With no repro command the two repro weights (40) are lost, so the score cannot
reach the `>= 80` mandatory gate even when generated differential evidence is
strong. That matches the plan's exact weights and the explicit gate; calling it
`VERIFIED` instead would have silently re-normalised. A `NEEDS_REVIEW` run in
this shape carries the limitation
`No explicit user-provided reproduction command was available.`

## 7. Timed-out commands are inconclusive, never evidence

A timed-out baseline/candidate command produces a `skip` evidence item and an
explicit limitation (`... timed out; ... is inconclusive`) rather than being
counted as reproduced or resolved.

## 8. Polling fallback and an extra `events.json` endpoint

The plan prefers SSE with polling fallback. The API exposes the SSE stream
`GET /api/runs/{run_id}/events` plus a non-streaming `GET
/api/runs/{run_id}/events.json?after=N` used by the fallback. The dashboard uses
`EventSource` first and polls the JSON endpoint when it is unavailable.

## 9. Built dashboard is served by the API when present

`apps/web/dist` is gitignored. If it exists, the API serves `index.html`,
`/assets/*`, and a SPA fallback from the same origin, so one `uvicorn`
process runs the entire demo. `scripts/dev.sh` still runs the Vite dev proxy for
frontend work.

## 10. Fixture `.gitignore` keeps the source repo clean

Fixture test runs create `__pycache__` and `.pytest_cache`. The fixture ships a
`.gitignore` covering those plus `*.xml` and `.proofpatch_generated_tests/`,
so the strict dirty-repository check stays green across repeated demos.

## 11. Pytest discovery of generated tests

`pytest` skips dot-directories under its default `norecursedirs` (`.*`), so the
default suite command never collects `.proofpatch_generated_tests/`, while an
explicit `pytest .proofpatch_generated_tests` still collects it. The fixture's
`pyproject.toml` also sets `testpaths=["tests"]` and `pythonpath=["src"]`, so the
default suite and the generated tests both resolve the fixture's `src/` layout.

## 12. The Cline SDK is the only LLM integration

Per the v0.1 target, ProofPatch has exactly one LLM integration: the **Cline SDK** (`@cline/sdk`,
Node 22+). The engine is Python, so `packages/cline-bridge` is a small Node process that takes a
JSON request on stdin, runs one single-shot `Agent.run(...)`, and prints one JSON response. The
Python provider (`proofpatch.llm.cline_sdk.ClineSDKProvider`) spawns it via `asyncio.to_thread`.

- Removed the generic OpenAI-compatible provider and the old `PROOFPATCH_LLM_MODE` fake/live
  toggle. There is no user-facing provider switch any more.
- The bridge always constructs the agent with `tools: []`, so the model can only return text —
  it cannot read, edit, or run anything in the repository under verification (plan §12.2 trust
  boundary). It also sets `clientName`-equivalent defaults and suppresses Node warnings so stdout
  stays a single JSON document.
- **Structured output**: the SDK has no structured-output API, so the provider appends an explicit
  per-agent JSON contract to the system prompt, extracts JSON, validates with Pydantic, and
  retries **once** with the validation error — exactly the fallback the plan prescribes.
- **Endpoint choice**: `providerId: "cline"` (Cline usage-billing) routes through
  `ai-gateway.vercel.sh`, which failed repeatedly in this environment
  (`failed to create stream ... giving up after 4 attempts`). The provider therefore defaults to
  `providerId: "openai-compatible"` with `baseUrl: https://api.cline.bot/api/v1` — still driven
  entirely by the Cline SDK, but over Cline's OpenAI-compatible API, which responded reliably.
  Both the endpoint and model come from `PROOFPATCH_CLINE_*` env vars (`.env`).
- **Credential discovery**: if `PROOFPATCH_CLINE_API_KEY`/`MODEL_ID` are absent, credentials and
  the default model are read from `~/.cline/data/settings/providers.json`, so an authenticated
  Cline machine works with zero configuration. `proofpatch doctor` reports readiness.

## 13. Tests never call the live model (plan §39.2/§39.4)

The plan forbids live model calls in unit tests. The stub provider now lives in
`packages/engine/tests/stub_provider.py` and is injected through the existing
`Orchestrator(provider=...)` seam. The API builds its provider internally, so
`apps/api/tests/conftest.py` puts the engine test directory on `sys.path` and the API test fixture
swaps `proofpatch.orchestrator.build_provider` for the stub via `pytest.MonkeyPatch()` (not the
`monkeypatch` fixture, because that fixture is function-scoped and `client` is module-scoped —
pytest raises `ScopeMismatch`).

This keeps the suite offline and free; live Cline SDK runs are exercised by `make demo` and
`proofpatch verify`.

## 14. Interrupted runs no longer leak worktrees (found in real-repo testing)

Worktrees live inside the *source* repository's `.git/worktrees`, so leaving one behind still
pollutes the developer's repository even though its branch is untouched. A first run against the
real `rich` repository was interrupted by a killed shell, and `git worktree list` still showed two
ProofPatch worktrees afterwards.

Fix (all in `proofpatch/repo/manager.py`):

- Every created worktree is registered in a module-level registry immediately after creation.
- An `atexit` hook plus a `SIGTERM`/`SIGINT` handler (installed only on the main thread, so the
  API's worker threads are unaffected) removes any still-registered worktrees at exit.
- `RepositoryManager.cleanup()` unregisters, and `keep_worktrees=True` intentionally unregisters

## 16. Context exclusions use repository-relative paths

`ContextBuilder._python_files` filtered on components of the **absolute** path. Because ProofPatch
always creates its worktrees under `<data_dir>/runs/<id>/worktrees/...` — inside the artifact
directory literally named `.proofpatch` — the exclusion for `.proofpatch/` silently dropped
**every** Python file in every worktree. Symbol search, the source-file fallback, and
(inevitably) any import-following heuristic could never contribute; only files named explicitly by
path were ever included. It went unnoticed on the fixture (canned diff ignores context) and on
`rich` (the issue named `rich/segment.py` directly).

Fixed: only *repository-relative* components are excluded. Regression test
`test_files_found_when_repo_sits_inside_proofpatch` reproduces the worktree nesting.

## 17. Context follows imports from selected tests

Bug reports often name only a reproduction *test* (like `bug.md` naming
`tests/test_session.py`). The builder now parses `import`/`from … import` statements out of any
selected test file and adds the matching local modules (e.g. `from payment.session import …` →
`src/payment/session.py`), so the patch agent sees the actual buggy source instead of guessing it
from prose. The Phase 8 fallback was also tightened to require a *non-test* source file, not just
any `.py` file.

## 18. Patcher prompt demands verbatim context

Real-model runs showed the agent occasionally normalising identifiers when writing the diff (e.g.
`session_expires_at` → `expires_at`), which fails `git apply`. The patcher system prompt now
requires every context line, signature, and identifier to be copied verbatim from the supplied file
contents, and hunk line numbers to be real. This complements (not replaces) the validator /
`git apply --check` / retry / fail-closed pipeline.

  too, so deliberately kept worktrees survive.
- A new `proofpatch cleanup --repo <path>` command removes leftovers from a *previous* hard kill;
  it only touches paths containing `/.proofpatch/runs/`, so unrelated developer worktrees are safe.

Verified: `kill -TERM` mid-run now leaves `0` orphan worktrees.

## 15. Real-repository validation: Textualize/rich v13.7.0, issue #3299

The prototype was re-run against a real third-party repository (cloned to `targets/rich`, which is
gitignored), not only the demo fixture.

| | |
|---|---|
| Repository | `Textualize/rich` at tag `v13.7.0` (`fd98182`) |
| Bug | [#3299](https://github.com/Textualize/rich/issues/3299) — `Segment._split_cells` non-unit characters |
| Model | `anthropic/claude-sonnet-5.5` via the Cline SDK bridge |
| Verdict | **VERIFIED, evidence score 100/100** |
| Patch | 1 line: `pos = int((cut / cell_length) * (len(text) - 1))` → `pos = 0` |
| Evidence | repro `1 → 0`; generated tests `3 failing → 0`; regressions `21 → 21` (0 new); static clean |
| Integrity | source repo clean, HEAD unchanged, no leftover worktrees, no artifacts written into it |

Environment prerequisites for that target (installed beforehand — never during a run):

- `attrs` and `setuptools<81`, without which `tests/test_pretty.py` and `tests/test_syntax.py`
  fail to *import* on Python 3.15 (`pkg_resources` was removed in setuptools 84).
- The suite then runs in ~4s with **21 pre-existing failures** on Python 3.15. ProofPatch's
  regression rule (`candidate_failed - baseline_failed`) correctly reports **0 new failures**, and
  the report lists the 21 pre-existing ones explicitly — the plan's "the repository was already
  failing" nuance, demonstrated on a real project.

Two things this run surfaced, both fixed: the interrupted-run worktree leak (note 14), and an
incorrect requirement I had originally written into the issue text (that the two halves must
concatenate back to the original `text`). rich's own `Segment.split_cells` docstring specifies that
a straddling wide character is replaced by *two spaces* to preserve display **width**, so the
correct invariants are "first half is exactly `cut` cells" and "total cell length preserved".
The issue text and reproduction command were corrected to match the real contract; the model's
first patch already satisfied them.

