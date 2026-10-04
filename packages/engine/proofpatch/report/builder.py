"""Report builder: assembles the JSON ProofReport from run state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..domain import ReproducibilityMetadata, Verdict, VerificationResult


class ProofReport(BaseModel):
    run_id: str
    repository: dict[str, Any] = Field(default_factory=dict)
    issue: dict[str, Any] = Field(default_factory=dict)
    status: str = ""
    verdict: str = Verdict.NEEDS_REVIEW.value
    evidence_score: int = 0
    verdict_summary: str = ""
    reproducibility: ReproducibilityMetadata = Field(default_factory=ReproducibilityMetadata)
    root_cause: dict[str, Any] | None = None
    patch: dict[str, Any] | None = None
    generated_tests: dict[str, Any] | None = None
    issue_evidence: dict[str, Any] = Field(default_factory=dict)
    regression: dict[str, Any] = Field(default_factory=dict)
    static: dict[str, Any] = Field(default_factory=dict)
    verification: VerificationResult
    limitations: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_dir: str = ""


VERDICT_SUMMARIES = {
    Verdict.VERIFIED.value: "Ready for human review",
    Verdict.NEEDS_REVIEW.value: "Needs human review — evidence incomplete",
    Verdict.REJECTED.value: "Rejected — do not trust this patch",
    Verdict.ERROR.value: "Verification could not complete",
}


class ReportBuilder:
    def build(
        self,
        *,
        run_id: str,
        verification: VerificationResult,
        repository: dict[str, Any] | None = None,
        issue: dict[str, Any] | None = None,
        reproducibility: ReproducibilityMetadata | None = None,
        root_cause: dict[str, Any] | None = None,
        patch: dict[str, Any] | None = None,
        generated_tests: dict[str, Any] | None = None,
        issue_evidence: dict[str, Any] | None = None,
        regression: dict[str, Any] | None = None,
        static: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        artifact_dir: str = "",
    ) -> ProofReport:
        verdict_value = verification.verdict.value
        return ProofReport(
            run_id=run_id,
            repository=repository or {},
            issue=issue or {},
            status=verdict_value,
            verdict=verdict_value,
            evidence_score=verification.score,
            verdict_summary=VERDICT_SUMMARIES.get(verdict_value, ""),
            reproducibility=reproducibility or ReproducibilityMetadata(),
            root_cause=root_cause,
            patch=patch,
            generated_tests=generated_tests,
            issue_evidence=issue_evidence or {},
            regression=regression or {},
            static=static or {},
            verification=verification,
            limitations=verification.limitations,
            started_at=started_at,
            completed_at=completed_at,
            artifact_dir=artifact_dir,
        )


__all__ = ["VERDICT_SUMMARIES", "ProofReport", "ReportBuilder"]
