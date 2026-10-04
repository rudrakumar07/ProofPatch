"""Context builder tests (Phase 8 exit criteria)."""

from proofpatch.domain import IssueInput
from proofpatch.repo.context import ContextBuilder

ISSUE = IssueInput(
    title="Payment allowed at exact session expiry",
    description="A payment attempted exactly at expires_at is accepted.",
    error_log='Traceback: File "src/payment/session.py", line 20, in can_process_payment',
    expected_behavior="now >= expires_at should be expired",
)


def test_tree_excludes_git_and_caches(fixture_repo):
    tree = ContextBuilder().build_tree(fixture_repo)
    assert ".git" not in [line.strip() for line in tree.splitlines()]
    assert "__pycache__" not in tree
    assert ".pytest_cache" not in tree
    assert "src" in tree


def test_selected_files_include_buggy_source(fixture_repo):
    context = ContextBuilder().build(fixture_repo, ISSUE)
    paths = [f.path for f in context.files]
    assert "src/payment/session.py" in paths
    assert all(".git/" not in p for p in paths)


def test_selected_files_include_project_metadata(fixture_repo):
    context = ContextBuilder().build(fixture_repo, ISSUE)
    paths = [f.path for f in context.files]
    assert "pyproject.toml" in paths


def test_every_file_records_a_reason(fixture_repo):
    context = ContextBuilder().build(fixture_repo, ISSUE)
    for item in context.files:
        assert item.reason


def test_secret_files_excluded(tmp_path):
    builder = ContextBuilder()
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "secrets.json").write_text("{}", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    context = builder.build(tmp_path, ISSUE)
    paths = [f.path for f in context.files]
    assert ".env" not in paths
    assert "secrets.json" not in paths


def test_max_files_limit_respected(fixture_repo):
    builder = ContextBuilder(max_files=3)
    context = builder.build(fixture_repo, ISSUE)
    assert len(context.files) <= 3


def test_per_file_truncation(tmp_path):
    builder = ContextBuilder(max_chars_per_file=100, max_files=5)
    (tmp_path / "big.py").write_text("# " + "x" * 5000, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    issue = IssueInput(title="t", description="big.py and pyproject")
    context = builder.build(tmp_path, issue)
    big = next((f for f in context.files if f.path == "big.py"), None)
    if big is not None:
        assert big.truncated is True
        assert len(big.content) <= 100


def test_total_budget_respected(fixture_repo):
    builder = ContextBuilder(max_files=20, max_chars_per_file=12000, max_total_chars=500)
    context = builder.build(fixture_repo, ISSUE)
    assert context.total_chars <= 500


def test_files_found_when_repo_sits_inside_proofpatch(tmp_path):
    # Simulates a ProofPatch worktree nested under <data>/runs/<id>/worktrees/...
    # Exclusions must use repository-*relative* path components only, otherwise
    # every Python file is dropped because the run directory is named .proofpatch.
    root = tmp_path / ".proofpatch" / "runs" / "pp_x" / "worktrees" / "baseline"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text(
        "from src.app import VALUE\n\ndef test_v():\n    assert VALUE == 1\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    builder = ContextBuilder()
    assert "src/app.py" in builder._python_files(root)

    issue = IssueInput(title="t", description="tests/test_app.py is failing")
    context = builder.build(root, issue)
    paths = [f.path for f in context.files]
    assert "src/app.py" in paths, paths
    assert "tests/test_app.py" in paths
