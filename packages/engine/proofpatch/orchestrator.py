"""ProofPatch orchestrator.

Wires the deterministic pipeline together: repository preparation, baseline
execution, analysis, patch generation, test generation, candidate verification,
and reporting. It emits events, persists artifacts after every step, and never
lets an exception erase artifacts already produced.

The orchestrator is async only where it awaits the LLM provider. Blocking
repository/command work runs inline; the API executes each run in its own thread
with its own event loop so this cannot stall the server.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .artifacts import ArtifactStore
from .config import Settings
from .domain import (
    CommandResult,
    EvidenceItem,
    PatchPolicyResult,
    ReproducibilityMetadata,
    RunRequest,
    RunStatus,
    StaticCheckResult,
    StepStatus,
    TestSuiteResult,
    Verdict,
    VerificationResult,
    utcnow,
)
from .events import EventListener, EventPublisher
from .ids import new_run_id
from .llm.analyzer import AnalyzerAgent
from .llm.factory import build_provider, provider_metadata
from .llm.patcher import PatchAgent
from .llm.prompts import PROMPT_VERSIONS
from .llm.provider import LLMError
from .llm.test_generator import GeneratedTestError, TestGeneratorAgent
from .repo.context import ContextBuilder
from .repo.manager import (
    DirtyRepository,
    NotAGitRepository,
    RepositoryError,
    RepositoryManager,
    RepoWorkspace,
)
from .repo.patch import (
    PatchApplicationError,
    PatchApplier,
    PatchValidator,
    check_apply,
)
from .report.builder import ProofReport, ReportBuilder
from .report.templates import render_markdown
from .verification.evidence import EvidenceEngine
from .verification.generated_tests import (
    lock_manifest,
    manifest_digest,
    verify_manifest,
    write_bundle,
)
from .verification.pytest_parser import parse_junit_xml
from .verification.python_adapter import PythonProjectAdapter
from .verification.runner import CommandRunner, LocalExecutionBackend
from .verification.score import TITLES, WEIGHTS
from .verification.static import run_static_checks


class RunResult(BaseModel):
    run_id: str
    status: RunStatus
    verdict: Verdict
    score: int = 0
    report: ProofReport | None = None
    report_markdown: str = ""
    artifact_dir: str = ""
    error: str | None = None


class Orchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        backend=None,
        listener: EventListener | None = None,
        provider=None,
    ) -> None:
        self.settings = settings or Settings()
        self.backend = backend or LocalExecutionBackend()
        self.listener = listener
        self.provider = provider

    # -- helpers ------------------------------------------------------------ #
    @staticmethod
    def _read_junit(repo: Path, rel: str, command: str) -> TestSuiteResult | None:
        path = Path(repo) / rel
        if not path.exists():
            return None
        return parse_junit_xml(path.read_text(encoding="utf-8", errors="replace"), command)


    def _error_verification(
        self, message: str, verdict: Verdict = Verdict.ERROR
    ) -> VerificationResult:
        """Build a verification result for a run that did not complete.

        Every evidence item is explicitly ``skip`` so the report can never claim
        a check passed when it never ran.
        """

        evidence = [
            EvidenceItem(
                key=key,
                title=TITLES[key],
                status="skip",
                weight=WEIGHTS[key],
                details="Not evaluated because the run did not complete.",
            )
            for key in WEIGHTS
        ]
        return VerificationResult(
            evidence=evidence,
            score=0,
            verdict=verdict,
            verdict_reasons=[message],
            limitations=[message],
        )

    def _reproducibility(self, workspace: RepoWorkspace, provider) -> ReproducibilityMetadata:
        from . import __version__

        name, model = provider_metadata(provider)
        return ReproducibilityMetadata(
            proofpatch_version=__version__,
            engine_git_sha=None,
            base_repo_sha=workspace.base_commit,
            llm_provider=name,
            llm_model=model,
            prompt_versions=dict(PROMPT_VERSIONS),
            python_version=sys.version.split()[0],
            platform=platform.platform(),
        )

    # -- main entry point --------------------------------------------------- #
    async def execute_run(
        self,
        request: RunRequest,
        *,
        run_id: str | None = None,
        listener: EventListener | None = None,
    ) -> RunResult:
        run_id = run_id or new_run_id()
        store = ArtifactStore.create(self.settings.data_dir, run_id)
        publisher = EventPublisher(run_id, persist=store.append_event)
        active_listener = listener or self.listener
        if active_listener is not None:
            publisher.subscribe(active_listener)
        started_at = utcnow()

        options = request.verification
        timeout = options.timeout_seconds or self.settings.default_timeout

        runner = CommandRunner(self.backend)
        adapter = PythonProjectAdapter()
        validator = PatchValidator(options)
        applier = PatchApplier()
        context_builder = ContextBuilder()
        repo_manager = RepositoryManager(
            self.settings.data_dir, keep_worktrees=self.settings.keep_worktrees
        )
        evidence_engine = EvidenceEngine()
        report_builder = ReportBuilder()

        publisher.emit("run_created", f"Run {run_id} created", payload={"issue": request.issue.title})

        workspace: RepoWorkspace | None = None
        provider = None
        root_cause = None
        patch = None
        generated_bundle = None
        manifest: dict | None = None
        baseline_repro = candidate_repro = None
        baseline_tests = candidate_tests = None
        baseline_generated = candidate_generated = None
        baseline_static: list[StaticCheckResult] = []
        candidate_static: list[StaticCheckResult] = []
        verification: VerificationResult | None = None
        counter = {"n": 0}

        def next_index() -> int:
            counter["n"] += 1
            return counter["n"]

        def _suite_label(result: TestSuiteResult | None) -> str:
            if result is None or not result.ran:
                return "not run"
            if result.total == 0:
                return "ran, no tests collected"
            return f"{result.total} tests: {result.passed} passed, {result.failed} failed"

        def _cmd_label(result: CommandResult | None) -> str:
            if result is None:
                return None
            if result.timed_out:
                return "timed out (inconclusive)"
            return f"exit code {result.exit_code}"

        run_meta: dict[str, Any] = {}

        def finish(ver: VerificationResult) -> RunResult:
            completed_at = utcnow()
            repo_info = {
                "path": request.repository.path,
                "base_commit": workspace.base_commit if workspace else None,
                "branch": workspace.branch if workspace else None,
                "repo_root": str(workspace.repo_root) if workspace else None,
            }
            repro = (
                self._reproducibility(workspace, provider)
                if workspace and provider
                else ReproducibilityMetadata()
            )
            patch_info = (
                {
                    "summary": patch.summary,
                    "why_it_should_work": patch.why_it_should_work,
                    "affected_files": patch.affected_files,
                    "risks": patch.risks,
                    "unified_diff": patch.unified_diff,
                    "diff_artifact": "candidate.diff",
                }
                if patch
                else None
            )
            gen_info = (
                {
                    "files": [f.relative_path for f in generated_bundle.files],
                    "scenarios": generated_bundle.scenarios,
                    "assumptions": generated_bundle.assumptions,
                    "manifest_digest": manifest_digest(manifest) if manifest else None,
                    "baseline_outcomes": _suite_label(baseline_generated),
                    "candidate_outcomes": _suite_label(candidate_generated),
                }
                if generated_bundle and manifest
                else None
            )
            report = report_builder.build(
                run_id=run_id,
                verification=ver,
                repository=repo_info,
                issue={"title": request.issue.title, "description": request.issue.description},
                reproducibility=repro,
                root_cause=root_cause.model_dump() if root_cause else None,
                patch=patch_info,
                generated_tests=gen_info,
                issue_evidence={
                    "repro_command": request.issue.repro_command,
                    "baseline_result": _cmd_label(baseline_repro),
                    "candidate_result": _cmd_label(candidate_repro),
                },
                regression={
                    "baseline_failures": sorted(baseline_tests.failed_ids)
                    if baseline_tests and baseline_tests.ran
                    else "not run",
                    "candidate_failures": sorted(candidate_tests.failed_ids)
                    if candidate_tests and candidate_tests.ran
                    else "not run",
                    "new_regressions": ver.new_regressions,
                },
                static={
                    "baseline_findings": sum(len(r.findings) for r in baseline_static),
                    "candidate_findings": sum(len(r.findings) for r in candidate_static),
                    "new_findings": ver.static_new_findings,
                },
                started_at=started_at,
                completed_at=completed_at,
                artifact_dir=str(store.run_dir),
            )
            markdown = render_markdown(report)
            store.write_json("report.json", report)
            store.write_text("report.md", markdown)

            status_map = {
                Verdict.VERIFIED: RunStatus.VERIFIED,
                Verdict.NEEDS_REVIEW: RunStatus.NEEDS_REVIEW,
                Verdict.REJECTED: RunStatus.REJECTED,
                Verdict.ERROR: RunStatus.ERROR,
            }
            final_status = status_map[ver.verdict]
            store.write_json(
                "run.json",
                {
                    **run_meta,
                    "status": final_status.value,
                    "verdict": ver.verdict.value,
                    "score": ver.score,
                    "completed_at": completed_at,
                },
            )
            publisher.emit(
                "run_completed",
                f"Run completed with verdict {ver.verdict.value}",
                status=final_status.value,
                payload={"score": ver.score, "verdict": ver.verdict.value},
            )
            publisher.emit(
                "run_status_changed", final_status.value, status=final_status.value
            )
            return RunResult(
                run_id=run_id,
                status=final_status,
                verdict=ver.verdict,
                score=ver.score,
                report=report,
                report_markdown=markdown,
                artifact_dir=str(store.run_dir),
                error=ver.verdict_reasons[0] if ver.verdict == Verdict.ERROR else None,
            )

        try:
            # ---- PREPARING -------------------------------------------------
            publisher.emit("run_status_changed", "PREPARING", status=RunStatus.PREPARING.value)
            workspace = repo_manager.prepare(request.repository, run_id)
            run_meta = {
                "run_id": run_id,
                "status": RunStatus.PREPARING.value,
                "repo_root": str(workspace.repo_root),
                "repo_path": request.repository.path,
                "base_commit": workspace.base_commit,
                "branch": workspace.branch,
                "issue_title": request.issue.title,
                "issue_description": request.issue.description,
                "repro_command": request.issue.repro_command,
                "artifact_dir": str(store.run_dir),
                "started_at": started_at,
            }
            store.write_json("run.json", run_meta)
            store.write_json("issue.json", request.issue)
            if not adapter.matches(workspace.baseline):
                raise RepositoryError(
                    "Unsupported project: ProofPatch v0.1 provides first-class verification "
                    "for Python projects only."
                )
            publisher.emit(
                "step_completed",
                "Repository prepared (isolated baseline/candidate worktrees)",
                step="repository_prepared",
                status="PASSED",
                payload={"base_commit": workspace.base_commit, "branch": workspace.branch},
            )

            provider = self.provider or build_provider(
                self.settings,
                recorder=lambda rec: store.append_jsonl("llm_calls.jsonl", rec),
            )

            # ---- BASELINE --------------------------------------------------
            publisher.emit(
                "run_status_changed", "BASELINE_RUNNING", status=RunStatus.BASELINE_RUNNING.value
            )

            if request.issue.repro_command:
                baseline_repro = runner.run(request.issue.repro_command, workspace.baseline, timeout)
                store.write_command_result(next_index(), "baseline-repro", baseline_repro)
                publisher.emit(
                    "step_completed",
                    "Baseline reproduction command executed",
                    step="baseline_reproduction",
                    status="PASSED" if not baseline_repro.passed else "FAILED",
                    payload={
                        "exit_code": baseline_repro.exit_code,
                        "timed_out": baseline_repro.timed_out,
                    },
                )
            else:
                publisher.emit(
                    "step_completed",
                    "No reproduction command provided",
                    step="baseline_reproduction",
                    status="SKIPPED",
                )

            full_cmd = request.verification.full_test_command or adapter.default_test_command(
                workspace.baseline
            )
            if full_cmd:
                result = runner.run(full_cmd, workspace.baseline, timeout)
                store.write_command_result(next_index(), "baseline-existing-tests", result)
                baseline_tests = self._read_junit(
                    workspace.baseline, ".proofpatch_pytest.xml", full_cmd
                )
                publisher.emit(
                    "step_completed",
                    "Baseline existing test suite executed",
                    step="baseline_existing_tests",
                    status="PASSED" if result.passed else "FAILED",
                    payload={"exit_code": result.exit_code},
                )
            else:
                publisher.emit(
                    "step_completed",
                    "No existing test suite detected",
                    step="baseline_existing_tests",
                    status="SKIPPED",
                )

            static_cmds = request.verification.static_commands or adapter.static_commands(
                workspace.baseline
            )
            baseline_static = run_static_checks(runner, workspace.baseline, static_cmds, timeout)
            store.write_json(
                "commands/baseline-static.json", [r.model_dump() for r in baseline_static]
            )
            publisher.emit(
                "step_completed",
                "Baseline static/syntax checks executed",
                step="baseline_static",
                status="PASSED" if all(not r.findings for r in baseline_static) else "FAILED",
            )


            # ---- ANALYZING -------------------------------------------------
            publisher.emit("run_status_changed", "ANALYZING", status=RunStatus.ANALYZING.value)
            context = context_builder.build(workspace.baseline, request.issue)
            store.write_json(
                "context.json",
                {
                    "tree": context.tree,
                    "files": [
                        {"path": f.path, "reason": f.reason, "truncated": f.truncated}
                        for f in context.files
                    ],
                },
            )
            analyzer = AnalyzerAgent(provider)
            root_cause = await analyzer.analyze(request.issue, context)
            store.write_json("root_cause.json", root_cause)
            publisher.emit(
                "step_completed",
                "Root cause analyzed",
                step="root_cause_analysis",
                status="PASSED",
                payload={"suspected_files": root_cause.suspected_files},
            )

            # ---- PATCH GENERATING ------------------------------------------
            publisher.emit(
                "run_status_changed", "PATCH_GENERATING", status=RunStatus.PATCH_GENERATING.value
            )
            patch_agent = PatchAgent(provider)

            async def generate_patch(feedback: str | None = None):
                return await patch_agent.generate(
                    issue=request.issue,
                    root_cause=root_cause,
                    context=context,
                    max_files=options.max_patch_files,
                    max_lines=options.max_patch_changed_lines,
                    feedback=feedback,
                )

            patch = await generate_patch()
            policy = validator.validate(patch.unified_diff)
            applied_ok, apply_msg = (False, "patch rejected by safety policy")
            if policy.allowed:
                applied_ok, apply_msg = check_apply(patch.unified_diff, workspace.candidate)
                if not applied_ok:
                    # One corrective retry, feeding the exact apply error back.
                    patch = await generate_patch(feedback=apply_msg)
                    policy = validator.validate(patch.unified_diff)
                    if policy.allowed:
                        applied_ok, apply_msg = check_apply(
                            patch.unified_diff, workspace.candidate
                        )
                    else:
                        applied_ok, apply_msg = False, "patch rejected by safety policy"

            if not policy.allowed:
                policy = policy.model_copy(update={"allowed": False})
            elif not applied_ok:
                policy = policy.model_copy(
                    update={"allowed": False, "reasons": [f"Patch could not be applied: {apply_msg}"]}
                )

            store.write_json("patch.json", patch)
            store.write_json("patch_policy.json", policy)
            store.write_text("candidate.diff", patch.unified_diff)
            publisher.emit(
                "step_completed",
                "Candidate patch generated",
                step="patch_generated",
                status="PASSED" if policy.allowed else "FAILED",
                payload={"files": policy.touched_files, "allowed": policy.allowed},
            )


            if policy.allowed:
                # ---- TEST GENERATING ------------------------------------------
                publisher.emit(
                    "run_status_changed",
                    "TEST_GENERATING",
                    status=RunStatus.TEST_GENERATING.value,
                )
                test_agent = TestGeneratorAgent(provider)
                test_context = context_builder.for_test_generation(
                    workspace.baseline, request.issue, root_cause
                )
            
                async def generate_tests():
                    return await test_agent.generate(
                        issue=request.issue, root_cause=root_cause, context=test_context
                    )

                try:
                    generated_bundle = await generate_tests()
                except GeneratedTestError:
                    # One retry for malformed/invalid generated tests.
                    generated_bundle = await generate_tests()

                write_bundle(workspace.baseline, generated_bundle)
                write_bundle(workspace.candidate, generated_bundle)
                manifest = lock_manifest(workspace.baseline, generated_bundle)
                store.write_json("generated_tests/manifest.json", manifest)
                store.write_json(
                    "generated_tests/bundle.json", generated_bundle.model_dump(mode="json")
                )
                publisher.emit(
                    "step_completed",
                    "Verification tests generated and locked",
                    step="tests_generated",
                    status="PASSED",
                    payload={
                        "files": [f.relative_path for f in generated_bundle.files],
                        "manifest_digest": manifest_digest(manifest),
                    },
                )

                # ---- baseline generated tests --------------------------------
                gen_cmd = adapter.generated_tests_command()
                gen_result = runner.run(gen_cmd, workspace.baseline, timeout)
                store.write_command_result(next_index(), "baseline-generated-tests", gen_result)
                baseline_generated = self._read_junit(
                    workspace.baseline, ".proofpatch_generated.xml", gen_cmd
                )
                publisher.emit(
                    "step_completed",
                    "Baseline verification tests executed",
                    step="baseline_generated_tests",
                    status="PASSED"
                    if baseline_generated and not baseline_generated.failed_ids
                    else "FAILED",
                )

                # ---- apply patch to candidate --------------------------------
                applier.apply(patch.unified_diff, workspace.candidate)
                publisher.emit(
                    "step_completed",
                    "Candidate patch applied to isolated worktree",
                    step="candidate_patch_applied",
                    status="PASSED",
                )


                # ---- VERIFYING ---------------------------------------------
                publisher.emit(
                    "run_status_changed", "VERIFYING", status=RunStatus.VERIFYING.value
                )
                problems = verify_manifest(workspace.candidate, manifest)
                if problems:
                    raise RepositoryError(
                        "Generated test integrity check failed: " + "; ".join(problems)
                    )
                publisher.emit(
                    "step_completed",
                    "Generated test hashes verified on candidate",
                    step="generated_tests_verified",
                    status="PASSED",
                )

                if request.issue.repro_command:
                    candidate_repro = runner.run(
                        request.issue.repro_command, workspace.candidate, timeout
                    )
                    store.write_command_result(next_index(), "candidate-repro", candidate_repro)
                    publisher.emit(
                        "step_completed",
                        "Candidate reproduction command executed",
                        step="candidate_reproduction",
                        status="PASSED" if candidate_repro.passed else "FAILED",
                        payload={"exit_code": candidate_repro.exit_code},
                    )

                cand_gen_result = runner.run(gen_cmd, workspace.candidate, timeout)
                store.write_command_result(
                    next_index(), "candidate-generated-tests", cand_gen_result
                )
                candidate_generated = self._read_junit(
                    workspace.candidate, ".proofpatch_generated.xml", gen_cmd
                )
                publisher.emit(
                    "step_completed",
                    "Candidate verification tests executed",
                    step="candidate_generated_tests",
                    status="PASSED"
                    if candidate_generated and not candidate_generated.failed_ids
                    else "FAILED",
                )

                if full_cmd:
                    cand_test_result = runner.run(full_cmd, workspace.candidate, timeout)
                    store.write_command_result(
                        next_index(), "candidate-existing-tests", cand_test_result
                    )
                    candidate_tests = self._read_junit(
                        workspace.candidate, ".proofpatch_pytest.xml", full_cmd
                    )
                    publisher.emit(
                        "step_completed",
                        "Candidate existing test suite executed",
                        step="candidate_existing_tests",
                        status="PASSED" if cand_test_result.passed else "FAILED",
                        payload={"exit_code": cand_test_result.exit_code},
                    )

                candidate_static = run_static_checks(runner, workspace.candidate, static_cmds, timeout)
                store.write_json(
                    "commands/candidate-static.json",
                    [r.model_dump() for r in candidate_static],
                )
                publisher.emit(
                    "step_completed",
                    "Candidate static/syntax checks executed",
                    step="candidate_static",
                    status="PASSED"
                    if all(not r.findings for r in candidate_static)
                    else "FAILED",
                )


            # ---- EVIDENCE ----------------------------------------------------
            verification = evidence_engine.evaluate(
                baseline_repro=baseline_repro,
                candidate_repro=candidate_repro,
                baseline_generated=baseline_generated,
                candidate_generated=candidate_generated,
                baseline_tests=baseline_tests,
                candidate_tests=candidate_tests,
                baseline_static=baseline_static,
                candidate_static=candidate_static,
                patch_policy=policy,
            )
            store.write_json("verification.json", verification)

            # ---- REPORTING ---------------------------------------------------
            publisher.emit("run_status_changed", "REPORTING", status=RunStatus.REPORTING.value)
            publisher.emit(
                "step_completed",
                "Proof report generated",
                step="proof_report",
                status="PASSED",
                payload={
                    "verdict": verification.verdict.value,
                    "score": verification.score,
                },
            )
            return finish(verification)

        except (RepositoryError, NotAGitRepository, DirtyRepository) as exc:
            publisher.emit("run_error", str(exc), status=RunStatus.ERROR.value)
            store.write_json("error.json", {"type": type(exc).__name__, "message": str(exc)})
            return finish(self._error_verification(str(exc)))

        except LLMError as exc:
            message = f"LLM provider failed after retry: {exc}"
            publisher.emit("run_error", message, status=RunStatus.ERROR.value)
            store.write_json("error.json", {"type": "LLMError", "message": str(exc)})
            return finish(self._error_verification(message))

        except PatchApplicationError as exc:
            message = f"Patch could not be applied: {exc}"
            publisher.emit("run_error", message, status=RunStatus.REJECTED.value)
            store.write_json("error.json", {"type": "PatchApplicationError", "message": str(exc)})
            if patch is not None:
                rejected_policy = PatchPolicyResult(allowed=False, reasons=[message])
                verification = evidence_engine.evaluate(
                    baseline_repro=baseline_repro,
                    candidate_repro=candidate_repro,
                    baseline_generated=baseline_generated,
                    candidate_generated=candidate_generated,
                    baseline_tests=baseline_tests,
                    candidate_tests=candidate_tests,
                    baseline_static=baseline_static,
                    candidate_static=candidate_static,
                    patch_policy=rejected_policy,
                )
                return finish(verification)
            return finish(self._error_verification(message, verdict=Verdict.REJECTED))

        except Exception as exc:  # noqa: BLE001 - top-level failure boundary
            message = f"{type(exc).__name__}: {exc}"
            publisher.emit("run_error", message, status=RunStatus.ERROR.value)
            store.write_json("error.json", {"type": type(exc).__name__, "message": str(exc)})
            return finish(self._error_verification(message))

        finally:
            # Cleanup must never overwrite a valid verdict.
            if workspace is not None:
                try:
                    repo_manager.cleanup(workspace)
                except Exception as cleanup_exc:  # noqa: BLE001
                    publisher.emit(
                        "warning",
                        f"Worktree cleanup failed: {cleanup_exc}",
                        status=StepStatus.SKIPPED.value,
                    )

