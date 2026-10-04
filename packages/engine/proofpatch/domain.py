"""Strongly typed domain model for ProofPatch.

These Pydantic models are shared by the orchestrator, the API responses, and the
report builder, which is why the plan recommends Pydantic over raw dataclasses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
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


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
class IssueInput(BaseModel):
    title: str
    description: str = ""
    error_log: str | None = None
    expected_behavior: str | None = None
    repro_command: str | None = None


class RepositoryInput(BaseModel):
    path: str
    ref: str | None = None


class VerificationOptions(BaseModel):
    full_test_command: str | None = None
    static_commands: list[str] = Field(default_factory=list)
    timeout_seconds: int = 120
    allow_test_file_changes_in_patch: bool = False
    max_patch_files: int = 8
    max_patch_changed_lines: int = 400


class RunRequest(BaseModel):
    repository: RepositoryInput
    issue: IssueInput
    verification: VerificationOptions = Field(default_factory=VerificationOptions)


# --------------------------------------------------------------------------- #
# Command execution
# --------------------------------------------------------------------------- #
class CommandResult(BaseModel):
    command: str
    cwd: str
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime = Field(default_factory=utcnow)
    duration_ms: int = 0
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        """A command only counts as passed when it actually ran and exited 0."""

        return (not self.timed_out) and self.exit_code == 0

    @property
    def ran(self) -> bool:
        return self.exit_code is not None and not self.timed_out


# --------------------------------------------------------------------------- #
# LLM proposal models
# --------------------------------------------------------------------------- #
class RootCauseAnalysis(BaseModel):
    summary: str
    suspected_files: list[str] = Field(default_factory=list)
    relevant_symbols: list[str] = Field(default_factory=list)
    reasoning_summary: list[str] = Field(default_factory=list)
    test_plan: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    uncertainties: list[str] = Field(default_factory=list)


class PatchProposal(BaseModel):
    summary: str
    why_it_should_work: str = ""
    affected_files: list[str] = Field(default_factory=list)
    unified_diff: str
    risks: list[str] = Field(default_factory=list)


class GeneratedTestFile(BaseModel):
    relative_path: str
    content: str
    purpose: str = ""


class GeneratedTestBundle(BaseModel):
    files: list[GeneratedTestFile] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
class EvidenceItem(BaseModel):
    key: str
    title: str
    status: Literal["pass", "fail", "skip", "error"]
    weight: int
    details: str = ""
    artifact_refs: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    issue_reproduced: bool | None = None
    generated_tests_fail_on_baseline: bool | None = None
    generated_tests_pass_on_candidate: bool | None = None
    repro_passes_on_candidate: bool | None = None
    new_regressions: list[str] = Field(default_factory=list)
    static_new_findings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    score: int = 0
    verdict: Verdict = Verdict.NEEDS_REVIEW
    verdict_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PatchPolicyResult(BaseModel):
    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    touched_files: list[str] = Field(default_factory=list)
    changed_lines: int = 0


class TestOutcome(BaseModel):
    """Parsed outcome of a single JUnit test case."""

    test_id: str
    classname: str = ""
    outcome: Literal["passed", "failed", "error", "skipped"]
    message: str = ""


class TestSuiteResult(BaseModel):
    command: str = ""
    ran: bool = False
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    outcomes: list[TestOutcome] = Field(default_factory=list)

    @property
    def failed_ids(self) -> set[str]:
        return {o.test_id for o in self.outcomes if o.outcome in ("failed", "error")}


class StaticCheckResult(BaseModel):
    command: str = ""
    ran: bool = False
    exit_code: int | None = None
    findings: list[str] = Field(default_factory=list)
    output: str = ""
    tool_available: bool = True


class RunEventModel(BaseModel):
    run_id: str
    sequence: int
    timestamp: datetime = Field(default_factory=utcnow)
    type: str
    step: str | None = None
    status: str | None = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ReproducibilityMetadata(BaseModel):
    proofpatch_version: str = "0.1.0"
    engine_git_sha: str | None = None
    base_repo_sha: str | None = None
    # Set by the orchestrator from the Cline SDK provider metadata.
    llm_provider: str = "cline-sdk"
    llm_model: str = ""
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    python_version: str = ""
    platform: str = ""


__all__ = [
    "CommandResult",
    "EvidenceItem",
    "GeneratedTestBundle",
    "GeneratedTestFile",
    "IssueInput",
    "PatchPolicyResult",
    "PatchProposal",
    "RepositoryInput",
    "ReproducibilityMetadata",
    "RootCauseAnalysis",
    "RunEventModel",
    "RunRequest",
    "RunStatus",
    "StaticCheckResult",
    "StepStatus",
    "TestOutcome",
    "TestSuiteResult",
    "Verdict",
    "VerificationOptions",
    "VerificationResult",
    "utcnow",
]

