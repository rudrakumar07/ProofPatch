"""LLM agent tests using the offline stub provider (no SDK calls)."""

import asyncio

import pytest
from proofpatch.domain import (
    GeneratedTestBundle,
    GeneratedTestFile,
    IssueInput,
    PatchProposal,
    RootCauseAnalysis,
)
from proofpatch.llm.analyzer import AnalyzerAgent
from proofpatch.llm.patcher import PatchAgent
from proofpatch.llm.provider import LLMError, extract_json
from proofpatch.llm.test_generator import (
    GeneratedTestError,
    TestGeneratorAgent,
    validate_bundle,
)
from proofpatch.repo.context import ContextBuilder
from stub_provider import StubLLMProvider

ISSUE = IssueInput(
    title="Payment allowed at exact session expiry",
    description="Payments succeed exactly at expires_at.",
    repro_command="pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry",
)
CONTEXT = ContextBuilder()


def test_stub_root_cause_is_valid():
    provider = StubLLMProvider()
    result = asyncio.run(
        provider.generate_structured(
            system_prompt="s", user_prompt="u", response_model=RootCauseAnalysis, agent="analyzer"
        )
    )
    assert result.confidence in ("low", "medium", "high")
    assert result.suspected_files
    assert not result.summary.startswith("diff")


def test_stub_patch_is_valid_unified_diff(fixture_repo):
    provider = StubLLMProvider(repo_path=fixture_repo)
    patch = asyncio.run(
        provider.generate_structured(
            system_prompt="s", user_prompt="u", response_model=PatchProposal, agent="patcher"
        )
    )
    assert patch.unified_diff.startswith("---")
    assert "src/payment/session.py" in patch.unified_diff
    assert "return now < session_expires_at" in patch.unified_diff
    assert "@@" in patch.unified_diff


def test_analyzer_returns_model(fixture_repo):
    context = CONTEXT.build(fixture_repo, ISSUE)
    agent = AnalyzerAgent(StubLLMProvider(repo_path=fixture_repo))
    result = asyncio.run(agent.analyze(ISSUE, context))
    assert isinstance(result, RootCauseAnalysis)
    assert any(f.path == "src/payment/session.py" for f in context.files)


def test_analyzer_rejects_diff_output():
    from proofpatch.repo.context import RepoContext

    class DiffProvider:
        name = "fake"
        model = "fake"

        async def generate_structured(self, **kwargs):
            return RootCauseAnalysis(summary="fix: diff --git a/x b/x @@ -1 +1 @@ +a")

    with pytest.raises(LLMError):
        asyncio.run(AnalyzerAgent(DiffProvider()).analyze(ISSUE, RepoContext()))  # type: ignore[arg-type]


def test_analyzer_rejects_verdict_output():
    from proofpatch.repo.context import RepoContext

    class VerdictProvider:
        name = "fake"
        model = "fake"

        async def generate_structured(self, **kwargs):
            return RootCauseAnalysis(summary="All tests pass: VERIFIED")

    with pytest.raises(LLMError):
        asyncio.run(AnalyzerAgent(VerdictProvider()).analyze(ISSUE, RepoContext()))  # type: ignore[arg-type]


def test_patch_agent_returns_proposal(fixture_repo):
    context = CONTEXT.build(fixture_repo, ISSUE)
    root_cause = RootCauseAnalysis(summary="boundary bug", suspected_files=["src/payment/session.py"])
    agent = PatchAgent(StubLLMProvider(repo_path=fixture_repo))
    patch = asyncio.run(agent.generate(issue=ISSUE, root_cause=root_cause, context=context))
    assert isinstance(patch, PatchProposal)
    assert patch.affected_files


def test_stub_tests_are_valid_and_under_generated_dir(fixture_repo):
    context = CONTEXT.for_test_generation(fixture_repo, ISSUE)
    agent = TestGeneratorAgent(StubLLMProvider(repo_path=fixture_repo))
    root_cause = RootCauseAnalysis(summary="s")
    bundle = asyncio.run(agent.generate(issue=ISSUE, root_cause=root_cause, context=context))
    assert isinstance(bundle, GeneratedTestBundle)
    assert len(bundle.files) >= 1
    assert len(bundle.files) <= 5
    # The plan asks for 2-5 *tests* total, not files.
    test_count = sum(item.content.count("def test_") for item in bundle.files)
    assert 2 <= test_count <= 5
    for item in bundle.files:
        assert item.relative_path.startswith(".proofpatch_generated_tests/")
        compile(item.content, item.relative_path, "exec")


def test_testgen_rejects_path_outside_dir():
    bundle = GeneratedTestBundle(
        files=[GeneratedTestFile(relative_path="tests/test_evil.py", content="def test_x(): pass")]
    )
    with pytest.raises(GeneratedTestError):
        validate_bundle(bundle)


def test_testgen_rejects_traversal():
    bundle = GeneratedTestBundle(
        files=[GeneratedTestFile(relative_path=".proofpatch_generated_tests/../../x.py", content="")]
    )
    with pytest.raises(GeneratedTestError):
        validate_bundle(bundle)


def test_testgen_rejects_syntax_error():
    bundle = GeneratedTestBundle(
        files=[
            GeneratedTestFile(
                relative_path=".proofpatch_generated_tests/test_bad.py", content="def broken(:"
            )
        ]
    )
    with pytest.raises(GeneratedTestError):
        validate_bundle(bundle)


def test_testgen_rejects_empty_bundle():
    with pytest.raises(GeneratedTestError):
        validate_bundle(GeneratedTestBundle(files=[]))


def test_extract_json_handles_code_fence():
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_extract_json_handles_prose_wrapper():
    parsed = extract_json('Here is the result: {"a": 1} thanks')
    assert parsed.startswith("{")
