# ProofPatch v0.1 — Detailed Implementation Plan

> **Primary goal:** Build a working hackathon-grade ProofPatch prototype that takes a software bug + repository, produces an AI-generated patch, creates independent verification tests, runs objective checks on the baseline and patched versions, and emits a human-readable **Proof Report** showing the evidence for or against the patch.
>
> **Intended reader:** a small LLM coding agent. This document is deliberately explicit. Follow it in order. Do not silently redesign the architecture, broaden scope, or skip acceptance tests.

---

# 1. Product definition

ProofPatch is not another autocomplete or code-generation product. Its defining job is to reduce the trust gap around AI-generated code by attaching evidence to a proposed patch.

The end-to-end product behavior for the first prototype is:

1. A developer supplies a repository and bug description.
2. ProofPatch inspects the repository and relevant failure information.
3. ProofPatch generates a candidate patch.
4. ProofPatch generates additional tests focused on the reported bug, edge cases, failure paths, and likely regressions.
5. ProofPatch runs verification checks against both the original code and patched code.
6. ProofPatch creates a report that says what was changed, why it should solve the issue, what evidence was observed, what failed or was skipped, and whether the patch is ready for human review.

The central product promise is:

**Do not merely say that a patch works. Show evidence that it works.**

The first version must therefore optimize for traceability and reproducibility rather than maximum autonomous coding power.

---

# 2. Deliberate MVP narrowing decisions

The product idea is language-agnostic, but a hackathon prototype built by a small coding agent needs a narrow first target.

For **v0.1**, make these implementation decisions and do not broaden them unless all acceptance criteria are already passing:

- Support **Git repositories only**.
- Implement first-class verification for **Python projects** only.
- Use **FastAPI** for the backend API.
- Use **React + Vite + TypeScript** for the developer dashboard.
- Use **SQLite** for run metadata and event persistence.
- Use the local filesystem for run artifacts, diffs, logs, generated tests, and reports.
- Use an **OpenAI-compatible LLM provider interface** configured with environment variables so the actual model/provider can be swapped.
- Expose a **CLI** as the primary integration point for Cline or another coding assistant. Cline can call the CLI from a terminal without requiring a custom extension in v0.1.
- Do not automatically merge or modify the developer's original branch. All changes happen in isolated worktrees.
- Do not claim probabilistic correctness. The displayed number is an **evidence score**, not a calibrated probability of correctness.
- Do not build embeddings, a vector database, multi-repository indexing, autonomous deployment, or PR creation in v0.1.

These constraints exist to maximize the chance of finishing a convincing working system rather than a broad but unreliable demo.

---

# 3. MVP user story

## 3.1 Primary user story

As a developer, I want to give ProofPatch a repository and a bug report, so that it can propose a fix and show concrete evidence that the proposed fix resolves the bug without introducing obvious regressions.

## 3.2 Concrete demo story

The demo should be able to run something like:

```bash
proofpatch verify \
  --repo ./demo-repo \
  --issue ./bug.md \
  --repro "pytest -q tests/test_session.py::test_payment_after_session_timeout"
```

Expected high-level output:

```text
[ProofPatch]
Run: pp_01J...
Base commit: 84fe5d...
Issue: Payment failure after session timeout

✓ Repository prepared
✓ Original issue reproduced
✓ Root cause identified
✓ Candidate patch generated
✓ Verification tests generated and locked
✓ Bug-specific tests fail on baseline
✓ Candidate patch applied
✓ Bug-specific tests pass on candidate
✓ Existing regression suite passed
✓ Static checks introduced no new issues

Evidence score: 94 / 100
Verdict: VERIFIED — Ready for Review
Report: .proofpatch/runs/pp_01J.../report.md
```

The web dashboard should show the same run with a progress timeline, patch diff, generated tests, evidence checklist, logs, score, verdict, and report.

---

# 4. Success criteria

The MVP is complete only when all of the following are true.

## 4.1 Functional success criteria

1. The system accepts a local Git repository, issue description, and reproduction command.
2. It records the current base commit and never modifies the original working branch.
3. It creates isolated baseline and candidate worktrees.
4. It runs the reproduction command on baseline and records whether the bug was actually reproduced.
5. It collects a compact repository context for the LLM.
6. It asks the LLM for a root-cause analysis in structured JSON.
7. It asks the LLM for a candidate patch as a unified diff.
8. It validates the patch before applying it.
9. It rejects path traversal, binary patches, modifications outside the repository, and disallowed file changes.
10. It generates bug-focused verification tests.
11. It locks generated test contents before final verification and stores a SHA-256 manifest.
12. It runs generated tests against the baseline version.
13. It applies the patch only to the candidate worktree.
14. It runs the same locked generated tests against the candidate version.
15. It runs existing tests on baseline and candidate and detects new failures.
16. It runs at least one static/syntax check.
17. It computes an evidence score using explicit deterministic rules.
18. It emits one of: `VERIFIED`, `NEEDS_REVIEW`, `REJECTED`, or `ERROR`.
19. It generates JSON and Markdown proof reports.
20. The web UI can create a run and render its live state.
21. The CLI can create a run and stream progress.
22. The full demo can be run from a clean checkout with documented setup commands.

## 4.2 Trust success criteria

The MVP must make these distinctions explicit:

- `The issue was reproduced` versus `the issue description was merely provided`.
- `A generated regression test failed on baseline and passed on candidate` versus `a generated test only passed on candidate`.
- `No new existing-test failures` versus `the entire repository was already clean`.
- `Static analysis produced no new findings` versus `no static analyzer was available`.
- `VERIFIED` versus `mathematically proven correct`.

Never describe an unexecuted or skipped check as passed.

---

# 5. Non-goals for v0.1

Do not implement the following until the core demo passes end-to-end:

- GitHub App installation flow.
- Automatic PR creation.
- Automatic merge.
- JavaScript/TypeScript verification.
- Java/Go/Rust support.
- Container orchestration across multiple hosts.
- Kubernetes.
- Celery, Kafka, RabbitMQ, Redis queues.
- Vector databases.
- Long-term repository indexing.
- Organization accounts, RBAC, billing, SSO.
- Learning from historical fixes.
- Continuous monitoring of every commit.
- Security vulnerability scanning beyond simple patch safety checks.
- Production-grade multi-tenant sandboxing.
- Automatic deployment.

The architecture may leave extension points for these, but do not build them now.

---

# 6. System architecture

Use this architecture:

```text
+-----------------------------+
| React Developer Dashboard   |
| - submit run                |
| - progress timeline         |
| - diff/tests/evidence       |
| - proof report              |
+--------------+--------------+
               |
               | HTTP + SSE
               v
+-----------------------------+
| FastAPI API                 |
|                             |
| Run API                     |
| Event stream                |
| Artifact endpoints          |
+--------------+--------------+
               |
               v
+-----------------------------+
| ProofPatch Orchestrator     |
|                             |
| 1. repository preparation   |
| 2. baseline execution       |
| 3. context collection       |
| 4. root-cause analysis      |
| 5. patch generation         |
| 6. test generation          |
| 7. candidate verification   |
| 8. scoring/reporting        |
+------+----------+-----------+
       |          |
       |          +-------------------------+
       |                                    |
       v                                    v
+----------------------+        +-------------------------+
| LLM subsystem        |        | Verification subsystem  |
| - provider           |        | - command runner        |
| - analyzer agent     |        | - pytest adapter        |
| - patch agent        |        | - static checks         |
| - test agent         |        | - baseline comparison   |
| - critic agent opt.  |        | - evidence engine       |
+----------------------+        +-------------------------+
       |
       v
+-----------------------------+
| Isolated Git Worktrees      |
| baseline / candidate        |
+-----------------------------+
```

The main architectural rule is that **LLM output is a proposal; verification state is produced by deterministic code**.

The LLM may suggest root cause, patch, or tests. It must never directly set `VERIFIED`, directly award score, or fabricate command results.

---

# 7. Monorepo layout

Create this exact repository structure unless a minor change is necessary for tooling:

```text
proofpatch/
├─ README.md
├─ .env.example
├─ .gitignore
├─ Makefile
├─ docker-compose.yml                 # optional; only if useful for demo
├─ apps/
│  ├─ api/
│  │  ├─ pyproject.toml
│  │  ├─ alembic.ini                  # optional; skip migrations if overkill
│  │  ├─ proofpatch_api/
│  │  │  ├─ __init__.py
│  │  │  ├─ main.py
│  │  │  ├─ settings.py
│  │  │  ├─ db.py
│  │  │  ├─ models.py
│  │  │  ├─ schemas.py
│  │  │  ├─ routes/
│  │  │  │  ├─ runs.py
│  │  │  │  └─ artifacts.py
│  │  │  └─ services/
│  │  │     └─ run_service.py
│  │  └─ tests/
│  └─ web/
│     ├─ package.json
│     ├─ vite.config.ts
│     ├─ tsconfig.json
│     ├─ src/
│     │  ├─ main.tsx
│     │  ├─ app.tsx
│     │  ├─ api.ts
│     │  ├─ types.ts
│     │  ├─ pages/
│     │  │  ├─ NewRunPage.tsx
│     │  │  └─ RunPage.tsx
│     │  ├─ components/
│     │  │  ├─ RunTimeline.tsx
│     │  │  ├─ EvidenceChecklist.tsx
│     │  │  ├─ DiffViewer.tsx
│     │  │  ├─ CommandResult.tsx
│     │  │  └─ VerdictCard.tsx
│     │  └─ styles.css
│     └─ public/
├─ packages/
│  └─ engine/
│     ├─ pyproject.toml
│     ├─ proofpatch/
│     │  ├─ __init__.py
│     │  ├─ cli.py
│     │  ├─ config.py
│     │  ├─ domain.py
│     │  ├─ orchestrator.py
│     │  ├─ events.py
│     │  ├─ artifacts.py
│     │  ├─ repo/
│     │  │  ├─ manager.py
│     │  │  ├─ context.py
│     │  │  └─ patch.py
│     │  ├─ llm/
│     │  │  ├─ provider.py
│     │  │  ├─ schemas.py
│     │  │  ├─ analyzer.py
│     │  │  ├─ patcher.py
│     │  │  ├─ test_generator.py
│     │  │  └─ prompts.py
│     │  ├─ verification/
│     │  │  ├─ runner.py
│     │  │  ├─ python_adapter.py
│     │  │  ├─ pytest_parser.py
│     │  │  ├─ static.py
│     │  │  ├─ evidence.py
│     │  │  └─ score.py
│     │  └─ report/
│     │     ├─ builder.py
│     │     └─ templates.py
│     └─ tests/
├─ fixtures/
│  └─ python-session-bug/
│     ├─ pyproject.toml
│     ├─ src/...
│     ├─ tests/...
│     ├─ bug.md
│     └─ README.md
└─ scripts/
   ├─ dev.sh
   ├─ demo.sh
   └─ reset_demo.sh
```

Keep the **engine package independent of FastAPI**. The API should call the engine; the engine should not import API code.

---

# 8. Core domain model

Implement strongly typed domain models before writing orchestration logic.

Use Python `Enum` + Pydantic models or dataclasses. Prefer Pydantic because the same schemas will be serialized into API responses and reports.

## 8.1 Run status

```python
class RunStatus(str, Enum):
    CREATED = "CREATED"
    PREPARING = "PREPARING"
    BASELINE_RUNNING = "BASELINE_RUNNING"
    ANALYZING = "ANALYZING"
    PATCH_GENERATING = "PATCH_GENERATING"
    TEST_GENERATING = "TEST_GENERATING"
    VERIFYING = "VERIFYING"
    REPORTING = "REPORTING"
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"
    ERROR = "ERROR"
```

## 8.2 Step status

```python
class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
```

## 8.3 Verdict

```python
class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"
    ERROR = "ERROR"
```

## 8.4 Issue input

```python
class IssueInput(BaseModel):
    title: str
    description: str
    error_log: str | None = None
    expected_behavior: str | None = None
    repro_command: str | None = None
```

## 8.5 Repository input

For v0.1, only local repositories are required:

```python
class RepositoryInput(BaseModel):
    path: str
    ref: str | None = None
```

A future `source_type` may support Git URL cloning, but do not make network clone support a blocker for the hackathon.

## 8.6 Verification options

```python
class VerificationOptions(BaseModel):
    full_test_command: str | None = None
    static_commands: list[str] = []
    timeout_seconds: int = 120
    allow_test_file_changes_in_patch: bool = False
    max_patch_files: int = 8
    max_patch_changed_lines: int = 400
```

## 8.7 Command result

```python
class CommandResult(BaseModel):
    command: str
    cwd: str
    exit_code: int | None
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    timed_out: bool = False
```

Never represent a command as passed if it did not execute.

## 8.8 Root-cause result

```python
class RootCauseAnalysis(BaseModel):
    summary: str
    suspected_files: list[str]
    relevant_symbols: list[str]
    reasoning_summary: list[str]
    test_plan: list[str]
    confidence: Literal["low", "medium", "high"]
    uncertainties: list[str]
```

Do not store hidden chain-of-thought. `reasoning_summary` should be a short, user-facing rationale produced by the model.

## 8.9 Patch proposal

```python
class PatchProposal(BaseModel):
    summary: str
    why_it_should_work: str
    affected_files: list[str]
    unified_diff: str
    risks: list[str]
```

## 8.10 Generated verification tests

```python
class GeneratedTestFile(BaseModel):
    relative_path: str
    content: str
    purpose: str

class GeneratedTestBundle(BaseModel):
    files: list[GeneratedTestFile]
    scenarios: list[str]
    assumptions: list[str]
```

Generated test files must be placed under a ProofPatch-owned path such as:

```text
.proofpatch_generated_tests/
```

inside each worktree for the duration of the run. Do not overwrite existing repository test files.

## 8.11 Evidence item

```python
class EvidenceItem(BaseModel):
    key: str
    title: str
    status: Literal["pass", "fail", "skip", "error"]
    weight: int
    details: str
    artifact_refs: list[str] = []
```

## 8.12 Verification result

```python
class VerificationResult(BaseModel):
    issue_reproduced: bool | None
    generated_tests_fail_on_baseline: bool | None
    generated_tests_pass_on_candidate: bool | None
    repro_passes_on_candidate: bool | None
    new_regressions: list[str]
    static_new_findings: list[str]
    evidence: list[EvidenceItem]
    score: int
    verdict: Verdict
    verdict_reasons: list[str]
    limitations: list[str]
```

---

# 9. Run state machine

Use a monotonic state machine. A run may fail, reject, or error, but must not jump arbitrarily between states.

Normal path:

```text
CREATED
  -> PREPARING
  -> BASELINE_RUNNING
  -> ANALYZING
  -> PATCH_GENERATING
  -> TEST_GENERATING
  -> VERIFYING
  -> REPORTING
  -> VERIFIED | NEEDS_REVIEW | REJECTED
```

Any operational exception may transition to `ERROR`.

Important semantic distinction:

- `REJECTED` means the system completed enough verification to conclude that the patch should not be trusted.
- `ERROR` means the verification workflow itself did not complete reliably.

Examples:

- Candidate patch causes test failures -> `REJECTED`.
- LLM API unavailable -> `ERROR`.
- Patch cannot be applied -> usually `REJECTED` with reason `invalid patch`, unless the failure was infrastructure related.
- Static analyzer missing -> not `ERROR`; mark check `SKIPPED`.

Persist every state transition as an event.

---

# 10. Artifact directory contract

Every run gets a self-contained artifact directory:

```text
.proofpatch/
└─ runs/
   └─ <run_id>/
      ├─ run.json
      ├─ issue.json
      ├─ root_cause.json
      ├─ patch.json
      ├─ candidate.diff
      ├─ generated_tests/
      │  ├─ ...
      │  └─ manifest.json
      ├─ commands/
      │  ├─ 001-baseline-repro.json
      │  ├─ 002-baseline-generated-tests.json
      │  ├─ 003-candidate-repro.json
      │  └─ ...
      ├─ verification.json
      ├─ report.json
      ├─ report.md
      └─ events.jsonl
```

Artifacts are part of the trust model. The user should be able to inspect exactly what ProofPatch executed and exactly what the LLM proposed.

Use atomic file writes where practical:

1. Write to `file.tmp`.
2. Flush.
3. Rename to final path.

---

# 11. Repository preparation

Implement `RepositoryManager` in `packages/engine/proofpatch/repo/manager.py`.

## 11.1 Responsibilities

`RepositoryManager` must:

- Resolve the supplied repository path.
- Confirm it exists.
- Confirm it is inside a Git work tree.
- Record repository root.
- Record `HEAD` commit SHA.
- Record current branch name if available.
- Detect dirty working-tree state.
- Refuse to modify the original branch.
- Create isolated worktrees:
  - `baseline`
  - `candidate`
- Clean them up at the end unless `PROOFPATCH_KEEP_WORKTREES=1`.

## 11.2 Dirty source repository behavior

For v0.1, default to refusing a dirty repository because the base state would be ambiguous.

Error message:

```text
Source repository has uncommitted changes. Commit or stash them before running ProofPatch, or rerun with --allow-dirty in development mode.
```

If `--allow-dirty` is later implemented, copy the repository rather than using Git worktrees. It is not required for MVP.

## 11.3 Worktree creation

Conceptually:

```bash
git -C <repo> worktree add --detach <run>/worktrees/baseline <base_sha>
git -C <repo> worktree add --detach <run>/worktrees/candidate <base_sha>
```

Store actual worktree paths in run metadata.

## 11.4 Cleanup

Always use `try/finally` around orchestration cleanup.

Cleanup failures must be logged but should not overwrite a valid report verdict.

---

# 12. Command runner

Implement a reusable `CommandRunner`.

## 12.1 Requirements

Every external command must:

- Execute with an explicit `cwd`.
- Have a configurable timeout.
- Capture stdout.
- Capture stderr.
- Capture exit code.
- Capture start/end timestamps.
- Kill child processes on timeout if possible.
- Truncate extremely large output in memory while preserving the complete raw log on disk.
- Return a structured `CommandResult`.

## 12.2 Shell behavior

For v0.1, because users provide commands such as pytest invocations, the runner may use the system shell. Treat this as local-developer mode and document that arbitrary commands are executed.

However:

- Never interpolate untrusted LLM text directly into shell commands.
- LLMs may propose file content and patches, not executable verification commands.
- Only run:
  - user-provided reproduction command;
  - commands selected by deterministic adapters;
  - commands explicitly configured in ProofPatch settings.

This is a major trust boundary.

## 12.3 Future sandbox boundary

Design an interface now:

```python
class ExecutionBackend(Protocol):
    def run(self, command: str, cwd: Path, timeout_seconds: int) -> CommandResult: ...
```

Implement `LocalExecutionBackend` first.

Add a TODO for `DockerExecutionBackend` with network isolation. Do not block the hackathon on production sandboxing.

---

# 13. Python project adapter

Implement `PythonProjectAdapter` so the orchestration layer does not contain Python-specific command logic.

## 13.1 Interface

```python
class ProjectAdapter(Protocol):
    def matches(self, repo: Path) -> bool: ...
    def collect_project_metadata(self, repo: Path) -> dict: ...
    def default_test_command(self, repo: Path) -> str | None: ...
    def static_commands(self, repo: Path) -> list[str]: ...
    def syntax_check_command(self, repo: Path) -> str: ...
```

## 13.2 Detection

Match Python if any of these exist:

- `pyproject.toml`
- `setup.py`
- `setup.cfg`
- `requirements.txt`

## 13.3 Default test command

If pytest appears to be available/configured, default to:

```bash
pytest -q --junitxml=.proofpatch_pytest.xml
```

If no tests directory or pytest config can be detected, mark existing test suite check as skipped.

## 13.4 Static checks

Mandatory lightweight check:

```bash
python -m compileall -q .
```

Optional checks when project configuration suggests they exist:

- `ruff check . --output-format=json`
- `mypy ...`

Do not install tools automatically during a verification run.

## 13.5 Test result parsing

Use JUnit XML from pytest.

Parse:

- test case ID
- classname/path
- passed/failed/error/skipped
- failure message

This enables comparison between baseline failures and candidate failures.

The regression rule is:

```text
new_failures = candidate_failed_test_ids - baseline_failed_test_ids
```

A candidate can still be `VERIFIED` if the baseline repository already had unrelated failures, provided no new failures are introduced and mandatory bug-specific evidence passes. The report must clearly list pre-existing failures.

---

# 14. Repository context collection

Do not send the entire repository to the LLM.

Implement a deterministic context builder.

## 14.1 Inputs

- Issue title and description.
- Error log/stack trace.
- Reproduction command.
- Repository tree.
- Relevant source files.
- Relevant tests.

## 14.2 Repository tree

Build a tree with these exclusions:

```text
.git/
node_modules/
.venv/
venv/
dist/
build/
coverage/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.proofpatch/
```

Limit depth to a reasonable value, e.g. 5.

## 14.3 File selection heuristic

Use simple heuristics before any embeddings:

1. Extract file paths from stack traces.
2. Extract likely Python symbols from exception lines and issue text.
3. Search repository text using `rg`/`grep` for those symbols.
4. Include files directly referenced by matching tests.
5. Include nearby test files with related names.
6. Include project metadata: `pyproject.toml`, relevant config.
7. Cap total text by character/token budget.

## 14.4 Context item format

```python
class ContextFile(BaseModel):
    path: str
    content: str
    reason: str
    truncated: bool
```

Log why each file was included.

## 14.5 Context limits

Suggested defaults:

- Max 20 files.
- Max 12,000 characters per file.
- Max roughly 80,000 total characters for initial analysis.

If the LLM context window is smaller, reduce further.

---

# 15. LLM provider abstraction

Create a provider interface so the rest of the engine is provider-neutral.

## 15.1 Environment variables

```text
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=90
LLM_MAX_RETRIES=2
```

Support an OpenAI-compatible chat/completions or responses-style endpoint through one implementation.

## 15.2 Provider interface

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        temperature: float = 0.0,
    ) -> BaseModel: ...
```

Prefer structured JSON outputs if the selected provider supports them. Otherwise:

1. Ask for JSON only.
2. Parse JSON.
3. Validate with Pydantic.
4. On validation failure, retry once with the validation errors.
5. If still invalid, fail that agent step.

Do not silently accept malformed responses.

## 15.3 LLM logging

For each call, store:

- agent name
- model name
- timestamp
- prompt hash
- response hash
- latency
- token counts if available
- parsing/validation result

Do not store API keys.

---

# 16. Agent separation

Use separate agent modules for separate responsibilities. Do not use one giant prompt that analyzes, patches, generates tests, and self-verifies in one response.

Required agents:

1. `AnalyzerAgent`
2. `PatchAgent`
3. `TestGeneratorAgent`

Optional after MVP works:

4. `PatchCriticAgent`

The deterministic verification engine, not an LLM agent, decides the final verdict.

---

# 17. Analyzer agent

## 17.1 Goal

Produce a compact, inspectable root-cause hypothesis and test plan.

## 17.2 System prompt requirements

The analyzer system prompt should say, in substance:

```text
You are the root-cause analysis component of ProofPatch.
Your job is to inspect the supplied issue, error output, repository tree,
and selected files, then produce a concise root-cause hypothesis.

Do not propose a code diff.
Do not claim that a hypothesis is proven.
Separate observed facts from assumptions.
Reference repository-relative file paths and symbols.
Output only the requested structured schema.
```

## 17.3 Required output

Use `RootCauseAnalysis`.

The root-cause object should contain:

- likely source of failure
- likely files/symbols
- a user-facing explanation
- test scenarios that would distinguish the bug from the expected behavior
- uncertainty notes

## 17.4 Acceptance test

Provide a fixture where the bug is obvious and verify that:

- returned file path exists;
- output validates;
- no unified diff appears in analyzer output;
- no final verification verdict is present.

---

# 18. Patch agent

## 18.1 Goal

Generate the smallest reasonable patch that addresses the root-cause hypothesis.

## 18.2 Inputs

Provide:

- issue
- root-cause analysis
- relevant source files
- relevant existing tests
- coding constraints

Do **not** let the patch agent modify verification artifacts.

## 18.3 System prompt requirements

```text
You are the patch-generation component of ProofPatch.
Generate the smallest code change that addresses the supplied issue and
root-cause hypothesis.

Constraints:
- Return a unified diff against the provided base revision.
- Do not edit .git, .proofpatch, generated verification tests, lock files,
  vendored dependencies, or unrelated files.
- Do not disable tests, delete assertions, broadly catch exceptions, or
  suppress errors merely to make tests pass.
- Do not change public behavior outside the described issue unless required.
- Explain risks separately from the diff.
- Output only the requested structured schema.
```

## 18.4 Patch validation pipeline

Before applying the diff:

1. Parse touched paths.
2. Reject absolute paths.
3. Reject paths containing `..`.
4. Reject `.git/**`.
5. Reject `.proofpatch/**`.
6. Reject `.proofpatch_generated_tests/**`.
7. Reject binary diffs.
8. Reject file count greater than `max_patch_files`.
9. Reject changed line count greater than `max_patch_changed_lines`.
10. Unless explicitly allowed, reject changes to repository test files.
11. Run `git apply --check` in candidate worktree.
12. If validation passes, store the raw candidate diff as an artifact.

Why reject existing test-file modifications by default: the patch generator should not be able to make the existing tests easier merely to obtain a green result.

## 18.5 Patch retry behavior

If `git apply --check` fails:

- Provide the patch agent the exact apply error and relevant files.
- Retry at most one time.
- Revalidate.
- If it still fails, mark patch generation failed and end with `REJECTED` or `ERROR` depending on the failure type.

Do not loop indefinitely.

---

# 19. Verification test generator

## 19.1 Goal

Generate tests that encode the behavior described by the bug report and likely edge cases.

## 19.2 Independence rule

The strongest practical design for v0.1 is:

- The patch is generated first, preserving the product's visible flow.
- The test generator is **not shown the patch diff**.
- It receives the issue, root-cause analysis, public interfaces, relevant source context, and existing tests.
- Therefore it cannot simply mirror the exact patch implementation.

## 19.3 Test categories

Ask for:

1. Reproduction/regression test for the reported bug.
2. At least one edge-case test.
3. At least one nearby behavior test when appropriate.

Keep the count small, usually 2–5 tests total.

## 19.4 Test file restrictions

Generated test paths must be under:

```text
.proofpatch_generated_tests/
```

Reject any output path elsewhere.

## 19.5 Locking tests

After generation:

1. Validate syntax.
2. Write the same generated test files to baseline and candidate worktrees.
3. Create a manifest containing every relative path and SHA-256 hash.
4. Store the manifest in the run artifact directory.
5. Do not allow the patch phase to run again after test locking unless the run explicitly resets the test phase.

Example manifest:

```json
{
  "algorithm": "sha256",
  "files": [
    {
      "path": ".proofpatch_generated_tests/test_session_bug.py",
      "sha256": "..."
    }
  ]
}
```

Before each generated-test execution, recalculate hashes and fail if they changed.

## 19.6 Baseline differential requirement

A generated regression test provides meaningful evidence only if at least one of the following is true:

- it fails on baseline and passes on candidate; or
- the explicit user reproduction command fails on baseline and passes on candidate.

A test that passes on both baseline and candidate does not prove the bug was fixed. It may still be useful as an edge-case check, but it gets no bug-fix differential weight.

---

# 20. Baseline verification

The baseline is not merely a before screenshot. It is required to establish causal evidence.

Run baseline checks before applying the patch to candidate.

## 20.1 Baseline reproduction command

If `repro_command` exists:

- Run it in baseline.
- Expected result for a real bug is non-zero exit code or observable failing test.
- Record stdout/stderr.

Set:

```text
issue_reproduced = True
```

only if the command fails in the expected bug direction.

For v0.1, simply interpret non-zero as reproduced. The report must state that this is command-level evidence, not semantic interpretation.

If the repro command unexpectedly passes:

- continue the run;
- mark `issue_reproduced=False`;
- cap the final verdict at `NEEDS_REVIEW` unless generated differential tests independently demonstrate the failure.

## 20.2 Baseline existing tests

Run the configured full test command if available.

Record all failing test IDs. These are pre-existing failures.

## 20.3 Baseline static checks

Run syntax/static commands and store findings. Candidate static results will later be compared against this baseline.

---

# 21. Candidate verification

After patch validation and generated-test locking:

1. Apply the diff to candidate worktree.
2. Recalculate generated-test hashes.
3. Run user reproduction command on candidate.
4. Run generated tests on candidate.
5. Run existing test suite on candidate.
6. Run static/syntax checks on candidate.
7. Compare candidate results against baseline.

The candidate must never be tested using a different generated-test version from baseline.

---

# 22. Regression comparison

## 22.1 Existing tests

Use JUnit XML to compare exact failing test IDs.

```python
preexisting_failures = set(baseline.failed_ids)
candidate_failures = set(candidate.failed_ids)
new_failures = candidate_failures - preexisting_failures
resolved_preexisting = preexisting_failures - candidate_failures
```

New failures are regressions.

Resolved pre-existing failures may be mentioned positively, but do not award extra verification points because they may be unrelated.

## 22.2 Static analysis

Where structured output exists, compare issue fingerprints.

For ruff, a fingerprint can be:

```text
<code>|<path>|<row>|<message>
```

Report only new candidate findings as regressions.

For `compileall`, any candidate syntax error is a hard failure.

---

# 23. Evidence scoring

Name the UI field **Evidence Score**, not Confidence Probability.

Use deterministic weights.

Recommended v0.1 scoring:

| Evidence | Weight | Pass condition |
|---|---:|---|
| Original issue reproduction established | 20 | repro command fails on baseline, or equivalent baseline failing test evidence |
| Candidate resolves explicit reproduction | 20 | same repro command succeeds on candidate |
| Generated bug-specific differential evidence | 25 | at least one locked generated test fails baseline and passes candidate |
| Existing regression suite introduces no new failures | 20 | `new_failures` is empty |
| Static/syntax verification introduces no new findings | 10 | no new static findings; syntax check passes |
| Patch safety/size policy passes | 5 | all patch safety guards pass |
| **Total** | **100** | |

Skipped checks contribute `0`; do not renormalize to 100.

## 23.1 Mandatory gates

A run may be `VERIFIED` only if all mandatory gates are true:

1. Candidate patch applied successfully.
2. Patch safety policy passed.
3. No new existing-test regressions.
4. No candidate syntax failure.
5. There is at least one causal bug-fix signal:
   - explicit repro fails baseline and passes candidate; **or**
   - generated bug-specific test fails baseline and passes candidate.
6. Evidence score is at least 80.

## 23.2 Verdict rules

### VERIFIED

All mandatory gates pass and score >= 80.

### NEEDS_REVIEW

Use when:

- patch appears plausible;
- no hard regression was found;
- but evidence is incomplete, missing, or score < 80.

Examples:

- no reproduction command and generated test passes on both baseline/candidate;
- test suite missing;
- static tools skipped;
- score 65.

### REJECTED

Use when:

- candidate reproduction still fails;
- generated regression test still fails on candidate;
- new existing-test regressions appear;
- syntax check fails;
- patch violates safety rules;
- patch cannot be applied after retry.

### ERROR

Use only for workflow/infrastructure failures:

- unexpected exception;
- database unavailable;
- LLM API unavailable after retry;
- worktree creation failure;
- command runner crashes.

---

# 24. Proof Report contract

Generate both JSON and Markdown.

The Markdown report should have this exact conceptual structure:

```markdown
# ProofPatch Verification Report

## Run Summary
- Run ID
- Repository
- Base commit
- Issue
- Started / completed
- Verdict
- Evidence score

## Issue Evidence
- Reproduction command
- Baseline result
- Candidate result

## Root Cause Analysis
- Summary
- Relevant files/symbols
- Assumptions and uncertainties

## Candidate Patch
- Summary
- Why it should work
- Files changed
- Risk notes
- Diff artifact reference

## Generated Verification Tests
- Scenarios
- Test files
- Test manifest hash
- Baseline outcomes
- Candidate outcomes

## Existing Regression Suite
- Baseline failures
- Candidate failures
- New regressions

## Static / Syntax Verification
- Baseline findings
- Candidate findings
- New findings

## Evidence Checklist
- each evidence item, status, weight, detail

## Verdict
- VERIFIED / NEEDS_REVIEW / REJECTED / ERROR
- Reasons

## Limitations
- skipped checks
- environment assumptions
- anything not proven
```

## 24.1 Example summary

```text
Issue: Payment failure after session timeout
Verdict: VERIFIED
Evidence score: 94 / 100

✓ Original issue reproduced
✓ Candidate resolves reproduction command
✓ Generated regression test fails on baseline and passes on candidate
✓ Existing regression suite introduces no new failures
✓ Static checks introduce no new findings

Result: Ready for human review
```

Do not write `Safe to Deploy` in v0.1. The strongest wording should be `Ready for human review`.

---

# 25. Orchestrator algorithm

Implement the orchestrator only after repository, runner, adapter, LLM, patch validation, and evidence modules exist independently.

Pseudocode:

```python
async def execute_run(request: RunRequest) -> RunResult:
    run = create_run_record(request)

    try:
        transition(run, PREPARING)
        repo = repo_manager.prepare(request.repository, run.id)
        adapter = adapter_registry.detect(repo.baseline)
        artifact_store.write_run_metadata(...)

        transition(run, BASELINE_RUNNING)
        baseline_repro = maybe_run_repro(request.issue.repro_command, repo.baseline)
        baseline_tests = maybe_run_existing_tests(adapter, repo.baseline)
        baseline_static = run_static_checks(adapter, repo.baseline)

        transition(run, ANALYZING)
        context = context_builder.build(repo.baseline, request.issue)
        root_cause = await analyzer.analyze(request.issue, context)
        artifact_store.write_root_cause(root_cause)

        transition(run, PATCH_GENERATING)
        patch = await patch_agent.generate(request.issue, root_cause, context)
        patch_policy = patch_validator.validate(patch, repo.candidate)
        if not patch_policy.allowed:
            return finalize_rejected(...)
        artifact_store.write_patch(patch)

        transition(run, TEST_GENERATING)
        test_context = context_builder.for_test_generation(
            issue=request.issue,
            root_cause=root_cause,
            repo=repo.baseline,
            include_patch=False,
        )
        tests = await test_agent.generate(test_context)
        generated_tests.validate_paths()
        generated_tests.write_to(repo.baseline)
        generated_tests.write_to(repo.candidate)
        manifest = generated_tests.lock_manifest()

        baseline_generated = run_generated_tests(repo.baseline)

        patch_applier.apply(patch, repo.candidate)

        transition(run, VERIFYING)
        assert_generated_test_hashes(repo.candidate, manifest)
        candidate_repro = maybe_run_repro(..., repo.candidate)
        candidate_generated = run_generated_tests(repo.candidate)
        candidate_tests = maybe_run_existing_tests(adapter, repo.candidate)
        candidate_static = run_static_checks(adapter, repo.candidate)

        verification = evidence_engine.evaluate(
            baseline_repro=baseline_repro,
            candidate_repro=candidate_repro,
            baseline_generated=baseline_generated,
            candidate_generated=candidate_generated,
            baseline_tests=baseline_tests,
            candidate_tests=candidate_tests,
            baseline_static=baseline_static,
            candidate_static=candidate_static,
            patch_policy=patch_policy,
        )

        transition(run, REPORTING)
        report = report_builder.build(...)
        artifact_store.write_report(report)
        persist_final_state(verification.verdict)
        return report

    except KnownRejectedPatch as exc:
        return finalize_rejected(...)
    except Exception as exc:
        return finalize_error(...)
    finally:
        repo_manager.cleanup_if_configured()
```

Do not let exceptions erase artifacts already produced.

---

# 26. API design

The API should be thin. It validates requests, stores run records, starts the orchestrator, and serves state/artifacts.

## 26.1 `POST /api/runs`

Request:

```json
{
  "repository": {
    "path": "/absolute/path/to/repo"
  },
  "issue": {
    "title": "Payment failure after session timeout",
    "description": "...",
    "error_log": "...",
    "expected_behavior": "...",
    "repro_command": "pytest -q tests/test_session.py::test_payment_after_session_timeout"
  },
  "verification": {
    "full_test_command": "pytest -q --junitxml=.proofpatch_pytest.xml",
    "static_commands": [],
    "timeout_seconds": 120
  }
}
```

Response `202 Accepted`:

```json
{
  "run_id": "pp_01J...",
  "status": "CREATED"
}
```

Run the orchestrator as an in-process background task for MVP.

Do not add Celery.

## 26.2 `GET /api/runs/{run_id}`

Return run metadata:

```json
{
  "run_id": "...",
  "status": "VERIFYING",
  "current_step": "existing_tests_candidate",
  "started_at": "...",
  "updated_at": "...",
  "score": null,
  "verdict": null
}
```

## 26.3 `GET /api/runs/{run_id}/events`

Use Server-Sent Events.

Event payload:

```json
{
  "sequence": 14,
  "timestamp": "...",
  "type": "step_completed",
  "step": "baseline_reproduction",
  "status": "PASSED",
  "message": "Original issue reproduced"
}
```

## 26.4 `GET /api/runs/{run_id}/report`

Return the JSON report.

## 26.5 `GET /api/runs/{run_id}/report.md`

Return Markdown with `text/markdown` content type.

## 26.6 `GET /api/runs/{run_id}/diff`

Return candidate diff as text.

## 26.7 `GET /api/runs/{run_id}/artifact/{path}`

Avoid arbitrary filesystem reads.

Use artifact IDs or validate that normalized paths stay within the run artifact directory.

---

# 27. Database design

Use SQLite with SQLModel, SQLAlchemy, or a minimal equivalent.

Do not store large logs/diffs in database blobs. Store artifact paths.

## 27.1 `runs`

Suggested columns:

```text
id TEXT PRIMARY KEY
status TEXT NOT NULL
verdict TEXT NULL
score INTEGER NULL
repo_path TEXT NOT NULL
base_commit TEXT NULL
issue_title TEXT NOT NULL
issue_description TEXT NOT NULL
repro_command TEXT NULL
artifact_dir TEXT NOT NULL
created_at DATETIME NOT NULL
updated_at DATETIME NOT NULL
completed_at DATETIME NULL
error_message TEXT NULL
```

## 27.2 `run_events`

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
run_id TEXT NOT NULL
sequence INTEGER NOT NULL
created_at DATETIME NOT NULL
event_type TEXT NOT NULL
step TEXT NULL
status TEXT NULL
message TEXT NOT NULL
payload_json TEXT NULL
```

Index `(run_id, sequence)`.

This is enough for MVP.

---

# 28. CLI design

The CLI is important because it makes ProofPatch immediately usable from Cline or any terminal-centric AI coding workflow.

Use Typer or Click. Typer is recommended.

## 28.1 Command

```bash
proofpatch verify [OPTIONS]
```

Required:

```text
--repo PATH
--issue FILE or --issue-text TEXT
```

Recommended:

```text
--repro COMMAND
--full-test COMMAND
--timeout SECONDS
--keep-worktrees
--json
```

## 28.2 CLI behavior

- Create a run.
- Stream events as they occur.
- Print final evidence summary.
- Print report location.
- Return meaningful exit codes.

Suggested exit codes:

```text
0 = VERIFIED
2 = NEEDS_REVIEW
3 = REJECTED
4 = ERROR
```

This lets other agents/tools make decisions without parsing English text.

---

# 29. Web dashboard

The UI exists to make the verification evidence understandable in a hackathon demo. It should not become a large frontend project.

## 29.1 Page: New Run

Fields:

- Repository path
- Issue title
- Issue description
- Error log, optional
- Expected behavior, optional
- Reproduction command, strongly recommended
- Full test command, optional advanced field
- Start Verification button

After creation, navigate to `/runs/:runId`.

## 29.2 Page: Run Detail

Header:

```text
ProofPatch Verification
Issue: ...
Status: VERIFYING
Base commit: 84fe5d...
```

Main sections:

1. Timeline
2. Evidence score/verdict
3. Root cause
4. Patch
5. Generated tests
6. Verification results
7. Logs
8. Final report

## 29.3 Timeline steps

Display:

```text
Repository prepared
Baseline issue reproduction
Root-cause analysis
Patch generated
Verification tests generated
Baseline verification tests
Candidate patch applied
Candidate verification tests
Regression suite
Static analysis
Proof report
```

Each is pending/running/pass/fail/skip.

## 29.4 Verdict card

Examples:

```text
VERIFIED
Evidence Score: 94 / 100
Ready for Review
```

or

```text
NEEDS REVIEW
Evidence Score: 65 / 100
The patch did not introduce new test failures, but the original bug could not be reproduced.
```

## 29.5 Diff viewer

For MVP, a simple `<pre>` unified diff is acceptable.

Do not spend time integrating Monaco unless everything else already works.

## 29.6 Live updates

Preferred: SSE.

Fallback: poll `GET /api/runs/{id}` every 2 seconds.

If SSE becomes a time sink, use polling. Verification quality matters more than streaming sophistication.

---

# 30. Event system

Implement a tiny event publisher used by both CLI and API.

Event types:

```text
run_created
run_status_changed
step_started
step_completed
artifact_created
warning
run_completed
run_error
```

An event should contain:

```python
class RunEvent(BaseModel):
    run_id: str
    sequence: int
    timestamp: datetime
    type: str
    step: str | None
    status: str | None
    message: str
    payload: dict = {}
```

Events are persisted before being broadcast to listeners.

This guarantees the UI can reconnect and reconstruct history.

---

# 31. Patch safety policy

The patch validator is central to the product's credibility.

Reject:

- absolute paths
- `../` traversal
- `.git/` modifications
- ProofPatch artifact modifications
- generated-test modifications
- binary patches
- symlink creation in v0.1
- file deletion unless explicitly enabled
- changes to more than 8 files by default
- more than 400 changed lines by default
- changes to existing tests by default

Warn, but do not necessarily reject:

- changes to dependency manifests
- changes to public API signatures
- changes to configuration
- exception swallowing

For the last categories, v0.1 can use simple textual heuristics and report warnings instead of attempting deep semantic security analysis.

---

# 32. LLM prompt templates

Keep prompts in files/functions with version strings.

Every prompt should include:

```text
Prompt version: proofpatch-<agent>-v1
```

This should be stored in artifacts so report runs are reproducible.

## 32.1 Analyzer user prompt skeleton

```text
ISSUE
Title: {title}
Description:
{description}

Expected behavior:
{expected_behavior}

Error / stack trace:
{error_log}

Reproduction command:
{repro_command}

REPOSITORY TREE
{tree}

SELECTED FILES
--- {path_1} ---
{content_1}
...

Produce the required RootCauseAnalysis JSON.
```

## 32.2 Patch prompt skeleton

```text
ISSUE
...

ROOT CAUSE HYPOTHESIS
{root_cause_json}

RELEVANT FILES
...

PATCH POLICY
- max files: 8
- max changed lines: 400
- no existing test modification
- no generated-test modification
- no unrelated refactor

Return PatchProposal JSON with a valid unified diff.
```

## 32.3 Test generator prompt skeleton

Important: do not include the patch diff.

```text
ISSUE
...

ROOT CAUSE HYPOTHESIS
...

PUBLIC/RELEVANT SOURCE CONTEXT
...

EXISTING TEST PATTERNS
...

Generate 2-5 verification tests.
At least one should specifically reproduce the reported bug.
Prefer black-box behavior over implementation-detail assertions.
Do not modify existing tests.
Place every generated file under .proofpatch_generated_tests/.
Return GeneratedTestBundle JSON.
```

---

# 33. Generated-test execution

The main complication is importability from `.proofpatch_generated_tests/`.

For Python, support running:

```bash
pytest -q .proofpatch_generated_tests --junitxml=.proofpatch_generated.xml
```

If the repository uses a `src/` layout, use the same environment that its existing tests use.

The generated tests should import public modules whenever possible.

If imports fail because the project requires installation, report this as a generated-test execution failure or environment limitation; do not automatically install dependencies from the internet in v0.1.

---

# 34. Handling missing reproduction commands

The product should strongly encourage a reproduction command but should not hard-require one.

If absent:

1. Analyzer still runs.
2. Patch and generated tests still run.
3. Generated differential evidence becomes especially important.
4. Add limitation: `No explicit user-provided reproduction command was available.`
5. `VERIFIED` is allowed only if a generated bug-specific test clearly fails baseline and passes candidate and all other mandatory checks pass.

Do not let an LLM invent a shell command and then treat it as user-authorized execution.

---

# 35. Handling flaky tests

Flaky tests can undermine verification credibility.

For v0.1 implement a simple optional rerun rule:

- If a mandatory generated test fails candidate unexpectedly, rerun it once.
- If outcomes differ, mark it flaky and force `NEEDS_REVIEW`.
- Do not retry until green.

For existing full-suite regressions:

- rerun newly failing test IDs once when possible;
- if result changes, label the test flaky and force `NEEDS_REVIEW` rather than `VERIFIED`.

Keep retry count fixed and visible in the report.

---

# 36. Failure handling matrix

Implement predictable behavior.

| Failure | System behavior |
|---|---|
| Repo path missing | ERROR before run starts |
| Not a Git repo | ERROR |
| Dirty repo | ERROR with actionable message |
| Unsupported project | ERROR/NEEDS_REVIEW; for MVP reject with clear unsupported-language message |
| Baseline repro passes | Continue; evidence weakened |
| LLM analysis invalid JSON | Retry once, then ERROR |
| Patch malformed | Retry once, then REJECTED |
| Patch violates safety policy | REJECTED |
| Test generator invalid JSON | Retry once, then ERROR |
| Generated tests syntactically invalid | Retry test generation once, then ERROR/NEEDS_REVIEW |
| Generated bug test passes baseline | Continue; no bug-differential credit |
| Candidate repro still fails | REJECTED |
| New existing-test failures | REJECTED |
| Static tool missing | SKIPPED |
| Candidate syntax failure | REJECTED |
| UI disconnects | Run continues server-side |
| Report generation fails | ERROR but keep previous artifacts |

---

# 37. Security model for the hackathon prototype

Be transparent: local repository verification executes code.

## 37.1 v0.1 statement

Document this prominently:

> ProofPatch v0.1 is a local developer prototype. Verification commands execute repository code on the developer's machine. Use only repositories you trust.

## 37.2 Minimum command safety

- No LLM-generated shell commands.
- Explicit timeouts.
- Explicit working directories.
- Limit captured output size.
- Do not read files outside repo/run directories when collecting context.
- Do not send `.env`, SSH keys, credential files, or obvious secrets to the LLM.

## 37.3 Context secret filtering

Exclude or redact files matching patterns such as:

```text
.env
.env.*
*.pem
*.key
id_rsa
id_ed25519
credentials.json
secrets.*
```

Also exclude Git ignored files by default where possible.

## 37.4 Future production direction

Later use a container/VM sandbox with:

- no network by default
- CPU/memory limits
- filesystem isolation
- ephemeral workspace
- dependency cache/proxy controls

This is future scope, not a blocker for the demo.

---

# 38. Demo fixture repository

A deterministic fixture is essential. Do not rely on an unknown public repository during the live demo.

Create `fixtures/python-session-bug`.

## 38.1 Fixture goals

The fixture should:

- be fewer than ~300 lines total;
- have one obvious but non-trivial bug;
- include 6–10 existing tests;
- include one failing reproduction test or command;
- have no external runtime dependencies beyond pytest;
- allow a 1–5 line patch;
- support meaningful edge-case generation;
- complete all tests in under 2 seconds.

## 38.2 Suggested fixture behavior

Build a tiny payment-session domain because it aligns with the product's example narrative.

Example API:

```python
def can_process_payment(session_expires_at: datetime, now: datetime) -> bool:
    ...
```

Introduce a boundary bug such as treating a session as valid at exactly the expiry timestamp when product semantics require it to be expired.

Buggy implementation:

```python
return now <= session_expires_at
```

Expected behavior:

```python
return now < session_expires_at
```

Existing tests cover:

- before expiry -> allowed
- after expiry -> denied
- unrelated session properties

Known failing reproduction test covers:

- exactly at expiry -> should be denied

This is intentionally simple enough for a deterministic hackathon demo while still demonstrating:

- root-cause analysis
- small patch
- generated edge cases
- baseline failure
- candidate pass
- regression suite pass

## 38.3 Fixture bug report

`bug.md`:

```markdown
# Payment allowed at exact session expiry

A payment session should no longer be usable once its expiry timestamp is reached.
Currently a payment attempted exactly at `expires_at` is accepted.

Expected: `now >= expires_at` should be treated as expired.
Actual: equality is treated as valid.
```

## 38.4 Reproduction command

```bash
pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry
```

---

# 39. Testing strategy for ProofPatch itself

Do not only test the fixture. Test the engine.

## 39.1 Unit tests

### Repository manager

- rejects non-Git directory
- rejects dirty repo
- records base SHA
- creates baseline/candidate worktrees
- cleanup works

### Patch validator

- accepts normal source diff
- rejects absolute path
- rejects `../`
- rejects `.git`
- rejects generated-test edits
- rejects existing test edits by default
- rejects too many files
- rejects too many lines

### Pytest parser

Use small fixture JUnit XML files:

- all pass
- one fail
- error
- skip

### Evidence engine

Table-driven tests for:

- full verified case
- no repro but generated differential evidence
- new regression -> rejected
- static skipped -> score reduced
- generated tests pass baseline and candidate -> no differential credit
- syntax failure -> rejected

### Report builder

- every check appears
- skipped checks not shown as pass
- verdict reasons present

## 39.2 LLM agent tests

Do not call a live model in unit tests.

Create `FakeLLMProvider` that returns fixed valid models.

Test:

- valid responses parse
- invalid response triggers retry
- patch retry path
- test generation path

## 39.3 Integration test

Run full orchestrator against the deterministic fixture using `FakeLLMProvider` with a known patch and test bundle.

Assert final verdict is `VERIFIED` and score meets threshold.

## 39.4 Optional live-model smoke test

Mark with `@pytest.mark.live_llm`.

Do not run in default CI.

---

# 40. Fake LLM outputs for deterministic development

Before integrating a real LLM, implement fake outputs so the verification pipeline can be built and tested deterministically.

For the demo fixture:

## 40.1 Fake root cause

```json
{
  "summary": "The expiry boundary uses <=, so equality is incorrectly treated as valid.",
  "suspected_files": ["src/payment/session.py"],
  "relevant_symbols": ["can_process_payment"],
  "reasoning_summary": [
    "The bug occurs exactly at the expiry timestamp.",
    "The session validity condition includes equality."
  ],
  "test_plan": [
    "Verify before expiry is allowed.",
    "Verify exact expiry is rejected.",
    "Verify after expiry is rejected."
  ],
  "confidence": "high",
  "uncertainties": []
}
```

## 40.2 Fake patch

A normal unified diff changing `<=` to `<`.

## 40.3 Fake generated tests

Create 2–3 tests under `.proofpatch_generated_tests/`.

This fake mode allows the entire product to be demoed even if an external LLM is temporarily unavailable. The UI should clearly show `Provider: fake` when this mode is used.

---

# 41. Configuration

Use a single settings class.

Suggested environment variables:

```text
PROOFPATCH_DATA_DIR=.proofpatch
PROOFPATCH_DATABASE_URL=sqlite:///./.proofpatch/proofpatch.db
PROOFPATCH_KEEP_WORKTREES=0
PROOFPATCH_DEFAULT_TIMEOUT=120
PROOFPATCH_MAX_PATCH_FILES=8
PROOFPATCH_MAX_PATCH_LINES=400
PROOFPATCH_LLM_MODE=live          # live | fake

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=90
```

Validate settings at startup.

If `PROOFPATCH_LLM_MODE=live` and LLM credentials are missing, fail clearly.

---

# 42. Logging

Use structured logs.

Every log entry should include when available:

```text
run_id
step
event
```

Never log:

- API keys
- full environment
- secret files

It is acceptable to log repository-relative paths and command exit codes.

---

# 43. Observability in the report

A user should be able to answer these questions from one report:

1. What exact commit was tested?
2. What bug did ProofPatch believe it was fixing?
3. Was the original issue reproduced?
4. What did the AI think the root cause was?
5. What exact code changed?
6. What tests did AI add?
7. Did those tests fail before the patch?
8. Did the same tests pass after the patch?
9. Did existing tests regress?
10. Did static/syntax checks regress?
11. Why was the score assigned?
12. Why was the final verdict assigned?
13. What was not checked?

If the report cannot answer these, it is not complete.

---

# 44. Step-by-step implementation phases

The coding agent should execute these phases in order. Each phase ends with acceptance criteria. Do not start major UI work before the engine integration test passes.

---

## Phase 0 — Scaffold the monorepo

### Tasks

1. Create directory structure.
2. Create root README.
3. Create Python package for engine.
4. Create FastAPI package.
5. Create React/Vite TypeScript app.
6. Create `.env.example`.
7. Create root `Makefile` or scripts.
8. Configure Python formatting/linting if easy.
9. Configure pytest.

### Suggested Python dependencies

Engine/API:

```text
pydantic
pydantic-settings
fastapi
uvicorn
httpx
typer
sqlmodel or sqlalchemy
python-multipart (only if later needed)
```

Development:

```text
pytest
pytest-asyncio
ruff
```

Keep dependencies small.

### Exit criteria

- `python -m pytest` executes.
- FastAPI `/health` returns `{"ok": true}`.
- React dev app renders `ProofPatch`.
- Engine imports successfully.

Commit label suggestion:

```text
chore: scaffold proofpatch monorepo
```

---

## Phase 1 — Domain models and artifact store

### Tasks

1. Implement enums and Pydantic models.
2. Implement run ID generation, preferably ULID-like or UUID.
3. Implement artifact directory creation.
4. Implement atomic JSON write helper.
5. Implement JSONL event append helper.
6. Add unit tests.

### Exit criteria

- Creating a run object serializes/deserializes cleanly.
- Artifact store creates run directory.
- Event append produces valid JSONL.
- Unit tests pass.

---

## Phase 2 — Command runner

### Tasks

1. Implement `ExecutionBackend` protocol.
2. Implement local backend.
3. Support timeout.
4. Capture stdout/stderr/exit code/duration.
5. Save command results as artifacts.
6. Add tests using simple commands.
7. Add timeout test.

### Exit criteria

- `python -c "print('ok')"` is captured as pass.
- failing command captures non-zero exit.
- timeout produces `timed_out=True`.
- no uncaught subprocess exception leaks.

---

## Phase 3 — Repository manager

### Tasks

1. Git detection.
2. Dirty repo detection.
3. Base SHA capture.
4. Baseline/candidate worktree creation.
5. Cleanup.
6. Tests using temporary Git repo.

### Exit criteria

- source repo remains unchanged.
- two detached worktrees point to same base SHA.
- cleanup removes worktrees.

---

## Phase 4 — Python adapter and pytest parser

### Tasks

1. Implement project detection.
2. Implement default test command.
3. Implement syntax check.
4. Implement JUnit XML parser.
5. Implement baseline/candidate failure comparison.
6. Unit tests.

### Exit criteria

- fixture tests can run through adapter.
- failing test IDs are parsed exactly.
- new failures are computed correctly.

---

## Phase 5 — Patch validator and applier

### Tasks

1. Parse paths from unified diff.
2. Count touched files and lines.
3. Enforce deny rules.
4. Run `git apply --check`.
5. Apply to candidate only.
6. Unit tests for malicious/invalid paths.

### Exit criteria

- valid diff applies.
- existing test edits rejected by default.
- path traversal rejected.
- source repo and baseline stay unchanged.

---

## Phase 6 — Deterministic demo fixture

Build the fixture now, before LLM integration.

### Tasks

1. Create tiny Python package.
2. Add bug.
3. Add existing tests.
4. Add known failing repro test.
5. Confirm baseline repro fails.
6. Manually create expected patch and confirm candidate passes.

### Exit criteria

Before continuing, these commands must be deterministic:

```bash
pytest -q fixtures/python-session-bug
```

with known expected baseline status, and after applying the known diff, all tests pass.

---

## Phase 7 — Fake LLM provider

### Tasks

1. Implement provider interface.
2. Implement fake provider.
3. Return known analyzer/patch/test objects for fixture.
4. Add tests.

### Exit criteria

No external network/model is needed to obtain valid structured agent outputs.

---

## Phase 8 — Context builder

### Tasks

1. Build repository tree.
2. Exclude secret/cache paths.
3. Parse likely file paths from error log.
4. Search issue terms/symbols.
5. Select relevant files.
6. Enforce size limits.
7. Unit tests.

### Exit criteria

For fixture, selected context must include the buggy source file and relevant test file without including `.git` or unrelated cache files.

---

## Phase 9 — Analyzer, patch, and test agents

### Tasks

1. Implement prompt templates.
2. Implement schema-validation wrapper.
3. Implement analyzer.
4. Implement patcher.
5. Implement test generator.
6. Use fake provider tests.
7. Enforce patch-hidden test generation.

### Exit criteria

Each agent can be called independently and returns a typed model.

---

## Phase 10 — Generated-test manifest and execution

### Tasks

1. Validate generated paths.
2. Write same tests to baseline/candidate.
3. Create SHA-256 manifest.
4. Recalculate before execution.
5. Execute generated tests on baseline.
6. Execute generated tests on candidate.
7. Parse results.

### Exit criteria

For fixture:

- at least one generated test fails on baseline;
- identical test hash is used on candidate;
- candidate passes after patch.

---

## Phase 11 — Evidence engine and score

### Tasks

1. Implement evidence item construction.
2. Implement regression comparison.
3. Implement scoring table.
4. Implement mandatory gates.
5. Implement verdict rules.
6. Add table-driven tests.

### Exit criteria

Test at least these scenarios:

- ideal verified run;
- candidate regression -> rejected;
- missing repro but generated differential -> potentially verified;
- no causal evidence -> needs review;
- syntax failure -> rejected;
- infrastructure exception -> error handled elsewhere.

---

## Phase 12 — Full orchestrator

### Tasks

1. Wire phases together.
2. Add event emission.
3. Persist artifacts after every step.
4. Implement error/finally handling.
5. Write integration test using fake LLM provider and fixture.

### Exit criteria

One function call on fixture produces:

```text
root_cause.json
candidate.diff
generated_tests/manifest.json
verification.json
report.json
report.md
```

and final verdict is `VERIFIED`.

This is the most important milestone. Do not proceed if this is unreliable.

---

## Phase 13 — Live LLM provider

### Tasks

1. Implement OpenAI-compatible provider.
2. Add retry/backoff.
3. Add structured JSON validation.
4. Add prompt/response artifact metadata.
5. Keep `fake` mode.
6. Add optional live smoke test.

### Exit criteria

A live model can solve the demo fixture at least several times without manual intervention.

If model reliability is weak, improve prompts and context selection before adding more product features.

---

## Phase 14 — Markdown/JSON report builder

### Tasks

1. Implement final report schema.
2. Render Markdown.
3. Include limitations.
4. Include exact evidence weights.
5. Link artifact filenames.

### Exit criteria

A developer can read `report.md` without using the web UI and understand exactly why the patch received its verdict.

---

## Phase 15 — CLI

### Tasks

1. Add `proofpatch verify`.
2. Stream events.
3. Render final checklist.
4. Support fake/live provider config.
5. Use defined exit codes.

### Exit criteria

The fixture demo works from one command.

Create `scripts/demo.sh` that resets fixture and runs this command.

---

## Phase 16 — API

### Tasks

1. SQLite run/event tables.
2. POST run endpoint.
3. GET run endpoint.
4. report endpoint.
5. diff endpoint.
6. SSE events or polling-ready endpoint.
7. Background task execution.

### Exit criteria

`curl` can start a run and retrieve final report.

---

## Phase 17 — Web dashboard

### Tasks

1. New Run form.
2. Run Detail page.
3. Poll/SSE updates.
4. Timeline.
5. Evidence checklist.
6. Verdict card.
7. Root-cause display.
8. Diff display.
9. Generated-test display.
10. Report display.

### Exit criteria

A hackathon judge can use the web UI without terminal knowledge and understand the before/after verification story.

---

## Phase 18 — Demo hardening

### Tasks

1. Make reset script deterministic.
2. Test on a clean machine/environment.
3. Add sample `.env` documentation.
4. Add fake-provider fallback.
5. Ensure logs are readable.
6. Ensure no stale run artifacts pollute the demo.
7. Add screenshots/GIF later if desired.

### Exit criteria

Run the entire demo three consecutive times without manual file editing.

---

# 45. API-to-engine boundary

Use a simple service call. The API should create a `RunRequest` and invoke:

```python
await orchestrator.execute_run(run_request, event_sink=...)
```

Do not duplicate verification logic in routes.

The CLI should call the same orchestrator.

This guarantees the dashboard and CLI show the same behavior.

---

# 46. Concurrency

For v0.1, allow only a small number of concurrent runs.

Implement a simple in-process semaphore, e.g. 2 runs.

Why:

- local command execution is resource-heavy;
- worktrees consume disk;
- LLM calls may be rate-limited.

If the semaphore is full, API runs can remain `CREATED`/queued or reject with 429. A tiny queue is acceptable.

Do not add distributed workers.

---

# 47. Run reproducibility metadata

Add this to every run:

```json
{
  "proofpatch_version": "0.1.0",
  "engine_git_sha": "...",
  "base_repo_sha": "...",
  "llm_provider": "...",
  "llm_model": "...",
  "prompt_versions": {
    "analyzer": "proofpatch-analyzer-v1",
    "patcher": "proofpatch-patcher-v1",
    "test_generator": "proofpatch-test-v1"
  },
  "python_version": "...",
  "platform": "..."
}
```

This reinforces the product theme of evidence and traceability.

---

# 48. UI copy guidelines

Use disciplined wording.

Prefer:

- `Original issue reproduced`
- `Candidate resolves reproduction command`
- `Generated regression test failed on baseline and passed on candidate`
- `No new existing-test failures detected`
- `Ready for human review`

Avoid:

- `Definitely correct`
- `Guaranteed safe`
- `100% secure`
- `Production ready`
- `AI proved the patch`

The product is about stronger evidence, not impossible guarantees.

---

# 49. Minimal example report JSON schema

Use a structure like:

```json
{
  "run_id": "pp_...",
  "repository": {
    "path": "...",
    "base_commit": "84fe5d..."
  },
  "issue": {
    "title": "..."
  },
  "root_cause": {
    "summary": "...",
    "suspected_files": ["..."]
  },
  "patch": {
    "summary": "...",
    "affected_files": ["..."]
  },
  "verification": {
    "evidence_score": 94,
    "verdict": "VERIFIED",
    "evidence": [
      {
        "key": "issue_reproduced",
        "status": "pass",
        "weight": 20,
        "details": "Reproduction command exited 1 on baseline."
      }
    ],
    "limitations": []
  }
}
```

---

# 50. Agent-facing implementation rules

The coding agent building this system should follow these rules exactly.

1. **Work in the phase order above.**
2. **Do not redesign the product midway.**
3. **Do not replace deterministic checks with LLM judgments.**
4. **Do not add framework complexity unless needed for an acceptance criterion.**
5. **Keep the engine independent from FastAPI and React.**
6. **Write tests for each core subsystem before wiring orchestration.**
7. **Use fake LLM mode to make development deterministic.**
8. **Do not allow LLM-generated shell commands to execute.**
9. **Never modify the source repository during verification.**
10. **Never let patch generation alter the generated verification tests.**
11. **Never report a skipped check as passed.**
12. **Persist enough artifacts to explain every verdict.**
13. **Fail closed on malformed patches.**
14. **Use one retry at most for malformed LLM output/patch application.**
15. **Keep the demo fixture deterministic and tiny.**
16. **Prefer polling over complex realtime architecture if SSE slows progress.**
17. **Prefer plain diff rendering over a complex editor if UI work slows progress.**
18. **Do not auto-install arbitrary repository dependencies.**
19. **Document local-code-execution risk.**
20. **Stop adding features once the end-to-end proof loop works; harden the demo instead.**

---

# 51. Definition of Done

ProofPatch v0.1 is done when a judge or developer can:

1. Open the dashboard or use the CLI.
2. Point ProofPatch at the supplied demo repository.
3. Provide the bug report/reproduction command.
4. Start verification.
5. Watch ProofPatch reproduce the issue on baseline.
6. See a concise root-cause explanation.
7. See a candidate diff.
8. See generated verification tests.
9. See evidence that at least one bug-specific test fails before the patch.
10. See the same locked test pass after the patch.
11. See existing regression tests compared baseline vs candidate.
12. See syntax/static checks.
13. Receive an evidence score and verdict.
14. Open a report containing all evidence and limitations.
15. Confirm the original repository branch was not modified.

The demo should make the message obvious:

**AI generated the fix, but ProofPatch did not ask the user to trust the AI's claim. It collected evidence.**

---

# 52. Suggested hackathon demo script

A polished demo can be 3–5 minutes.

## Step 1 — Show the bug

Run:

```bash
pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry
```

Show failure.

## Step 2 — Start ProofPatch

Use UI or CLI.

Provide issue + repo + repro command.

## Step 3 — Show analysis

Highlight:

- repository context found;
- root-cause hypothesis;
- suspect function/file.

## Step 4 — Show patch

Display tiny diff.

Do not dwell on generation. The innovation is verification.

## Step 5 — Show generated tests

Show that the tests are locked and have hashes.

## Step 6 — Show baseline/candidate difference

Most important moment:

```text
Generated regression test:
Baseline: FAIL
Candidate: PASS
```

## Step 7 — Show regressions/static checks

```text
Existing test regressions: none
New static findings: none
```

## Step 8 — Show Proof Report

```text
VERIFIED
Evidence Score: 94 / 100
Ready for Review
```

End on the principle:

**Do not trust an AI patch because the AI says it works; verify it with reproducible evidence.**

---

# 53. Stretch goals after the MVP is complete

Only implement these after the full Definition of Done passes.

## Stretch 1 — Docker execution backend

Run repository tests in an ephemeral container with:

- network disabled
- CPU/memory limits
- timeout
- mounted candidate worktree

## Stretch 2 — GitHub Pull Request integration

On a PR:

- fetch PR head
- run ProofPatch
- post a check summary/comment
- attach report

Do not auto-approve merge initially.

## Stretch 3 — Continuous verification

Trigger on commit push or CI.

## Stretch 4 — JavaScript/TypeScript adapter

Implement:

- npm/pnpm/yarn detection
- Jest/Vitest parser
- eslint/tsc checks

## Stretch 5 — Patch critic

A second LLM reviews the proposed patch for:

- unnecessary scope
- suspicious error suppression
- public API changes
- likely edge cases

This critic may add warnings but must still not determine final verification status.

## Stretch 6 — Historical learning

Store anonymized/internal run patterns and previously validated fixes. This aligns with the longer-term concept of learning from previous fixes, but it is far outside hackathon scope.

---

# 54. Future roadmap mapping

A sensible roadmap after hackathon:

### v0.1 — Local verification prototype

- CLI
- dashboard
- Python
- local Git worktrees
- AI patch + tests
- evidence report

### v0.2 — Pull request integration

- GitHub PR trigger
- CI-compatible execution
- report comment/check

### v0.3 — Continuous verification

- commit hooks
- CI/CD trigger
- status checks
- historical run comparison

### v0.4 — Code quality monitoring

- static analysis trends
- regression history
- repository health dashboard

### v1.0 — Enterprise verification platform

- hardened sandbox
- access controls
- policy checks
- security scanning
- organization-level audit log
- supported language adapters
- configurable verification policies

---

# 55. Final build priority

If time becomes limited, preserve this order:

1. Repository isolation.
2. Baseline reproduction.
3. Patch generation.
4. Generated test creation.
5. Baseline/candidate differential execution.
6. Existing regression comparison.
7. Evidence engine.
8. Proof report.
9. CLI.
10. Basic web UI.
11. Live streaming polish.
12. Stretch integrations.

The unique value of ProofPatch is steps 2–8. Do not sacrifice them for frontend polish.

---

# 56. One-shot instruction to give a small coding agent

Copy the following instruction together with this document if you want a coding agent to execute the plan:

> Build ProofPatch v0.1 exactly according to `ProofPatch_Implementation_Plan.md`. Work phase by phase in the documented order. Before coding a phase, inspect the current repository and existing tests. After coding a phase, run its acceptance checks and fix failures before continuing. Do not redesign the architecture, add unsupported languages, add distributed infrastructure, or replace deterministic verification with LLM judgment. Keep a deterministic fake-LLM mode operational at all times. Treat the end-to-end fixture integration test as the primary milestone. The original repository under verification must never be modified; all candidate changes must occur in isolated worktrees. Persist artifacts and logs after each step. If an assumption in the plan cannot be implemented as written, make the smallest compatible change, document it in `IMPLEMENTATION_NOTES.md`, and continue without broadening scope.

---

# 57. First concrete task for the coding agent

Start with this exact task, not the UI:

```text
PHASE 0 + PHASE 1 ONLY

1. Scaffold the monorepo exactly as described.
2. Implement the engine domain models.
3. Implement the artifact store and JSONL event writer.
4. Add tests for serialization and artifact creation.
5. Add a minimal FastAPI /health endpoint.
6. Add a minimal React page that only renders "ProofPatch".
7. Run tests and show the final file tree.
8. Do not implement LLM calls, Git worktrees, patching, verification, or dashboard features yet.
```

Once that phase is stable, move to Phase 2.

---

# 58. Final engineering principle

The architecture should continuously enforce this separation:

```text
AI proposes.
Deterministic tooling executes.
Evidence engine compares.
Human receives proof-oriented context.
```

That separation is what turns ProofPatch from another AI coding agent into a verification layer for AI-assisted development.
