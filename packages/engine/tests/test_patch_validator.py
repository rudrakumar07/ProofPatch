"""Patch validator tests (Phase 5 exit criteria)."""

from proofpatch.domain import VerificationOptions
from proofpatch.repo.patch import (
    PatchValidator,
    check_apply,
    is_test_path,
    parse_unified_diff,
)

GOOD_DIFF = (
    "--- a/src/app.py\n"
    "+++ b/src/app.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def add(a, b):\n"
    "-    return a + b\n"
    "+    return a - b\n"
)


def test_accepts_normal_source_diff():
    result = PatchValidator().validate(GOOD_DIFF)
    assert result.allowed is True
    assert result.reasons == []
    assert result.touched_files == ["src/app.py"]
    assert result.changed_lines == 2


def test_rejects_absolute_path():
    diff = "--- /etc/passwd\n+++ /etc/passwd\n@@ -1 +1 @@\n-x\n+y\n"
    result = PatchValidator().validate(diff)
    assert result.allowed is False
    assert any("Absolute path" in r for r in result.reasons)


def test_rejects_path_traversal():
    diff = "--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -1 +1 @@\n-x\n+y\n"
    result = PatchValidator().validate(diff)
    assert result.allowed is False
    assert any("traversal" in r for r in result.reasons)


def test_rejects_git_modification():
    diff = "--- a/.git/config\n+++ b/.git/config\n@@ -1 +1 @@\n-x\n+y\n"
    assert PatchValidator().validate(diff).allowed is False


def test_rejects_proofpatch_artifact_modification():
    diff = "--- a/.proofpatch/run.json\n+++ b/.proofpatch/run.json\n@@ -1 +1 @@\n-x\n+y\n"
    assert PatchValidator().validate(diff).allowed is False


def test_rejects_generated_test_edits():
    diff = (
        "--- a/.proofpatch_generated_tests/t.py\n"
        "+++ b/.proofpatch_generated_tests/t.py\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    assert PatchValidator().validate(diff).allowed is False


def test_rejects_existing_test_edits_by_default():
    diff = "--- a/tests/test_app.py\n+++ b/tests/test_app.py\n@@ -1 +1 @@\n-x\n+y\n"
    result = PatchValidator().validate(diff)
    assert result.allowed is False
    assert any("test files" in r for r in result.reasons)


def test_allows_test_edits_when_enabled():
    options = VerificationOptions(allow_test_file_changes_in_patch=True)
    diff = "--- a/tests/test_app.py\n+++ b/tests/test_app.py\n@@ -1 +1 @@\n-x\n+y\n"
    assert PatchValidator(options).validate(diff).allowed is True


def test_rejects_too_many_files():
    chunks = []
    for i in range(12):
        chunks.append(f"--- a/f{i}.py\n+++ b/f{i}.py\n@@ -1 +1 @@\n-x\n+y\n")
    result = PatchValidator().validate("".join(chunks))
    assert result.allowed is False
    assert any("limit is 8" in r for r in result.reasons)


def test_rejects_too_many_lines():
    options = VerificationOptions(max_patch_changed_lines=2)
    diff = "--- a/f.py\n+++ b/f.py\n@@ -1,6 +1,6 @@\n" + "".join(
        f"-x{i}\n+y{i}\n" for i in range(6)
    )
    result = PatchValidator(options).validate(diff)
    assert result.allowed is False
    assert any("lines" in r for r in result.reasons)


def test_rejects_binary_patch():
    diff = "--- a/img.png\n+++ b/img.png\nGIT binary patch\nliteral 5\n"
    result = PatchValidator().validate(diff)
    assert result.allowed is False
    assert any("Binary" in r for r in result.reasons)


def test_rejects_empty_patch():
    assert PatchValidator().validate("").allowed is False


def test_warns_on_manifest_change():
    diff = "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-old\n+new\n"
    result = PatchValidator().validate(diff)
    assert result.allowed is True
    assert any("manifest" in w for w in result.warnings)


def test_is_test_path_heuristic():
    assert is_test_path("tests/test_session.py")
    assert is_test_path("pkg/thing_test.py")
    assert is_test_path("conftest.py")
    assert not is_test_path("src/session.py")


def test_parse_counts_changed_lines():
    info = parse_unified_diff(GOOD_DIFF)
    assert info.changed_lines == 2
    assert info.touched_files == ["src/app.py"]
    assert info.is_binary is False


def test_check_apply_accepts_valid_diff(temp_git_repo):
    ok, message = check_apply(GOOD_DIFF, temp_git_repo)
    # temp_git_repo has app.py at repo root (not src/), so this must fail.
    assert ok is False
    assert message


def test_check_apply_on_matching_repo(temp_git_repo):
    (temp_git_repo / "src").mkdir()
    (temp_git_repo / "src" / "app.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    import subprocess

    subprocess.run(["git", "-C", str(temp_git_repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(temp_git_repo), "commit", "-qm", "add src"], check=True
    )
    ok, message = check_apply(GOOD_DIFF, temp_git_repo)
    assert ok is True, message
