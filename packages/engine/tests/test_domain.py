"""Domain model serialization tests."""

from proofpatch.domain import (
    EvidenceItem,
    IssueInput,
    RunRequest,
    RunStatus,
    Verdict,
    VerificationOptions,
)


def test_run_request_roundtrip():
    request = RunRequest(
        repository={"path": "/tmp/repo"},
        issue={"title": "Payment bug", "description": "desc"},
        verification={"timeout_seconds": 30},
    )
    restored = RunRequest.model_validate_json(request.model_dump_json())
    assert restored.issue.title == "Payment bug"
    assert restored.verification.timeout_seconds == 30


def test_enums_are_strings():
    assert RunStatus.VERIFIED.value == "VERIFIED"
    assert Verdict.NEEDS_REVIEW.value == "NEEDS_REVIEW"


def test_verification_defaults_match_plan():
    options = VerificationOptions()
    assert options.max_patch_files == 8
    assert options.max_patch_changed_lines == 400
    assert options.allow_test_file_changes_in_patch is False


def test_evidence_item_status_literal():
    item = EvidenceItem(key="k", title="t", status="pass", weight=10, details="d")
    assert item.status == "pass"
    assert EvidenceItem.model_validate_json(item.model_dump_json()).weight == 10


def test_issue_input_optional_fields():
    issue = IssueInput(title="only title")
    assert issue.error_log is None
    assert issue.repro_command is None
