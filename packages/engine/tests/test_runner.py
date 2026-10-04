"""Command runner tests (Phase 2 exit criteria)."""

from proofpatch.verification.runner import CommandRunner, LocalExecutionBackend


def test_successful_command_captured(tmp_path):
    result = CommandRunner().run("echo hello", tmp_path, 10)
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.timed_out is False
    assert result.passed is True
    assert result.duration_ms >= 0


def test_failing_command_captures_exit_code(tmp_path):
    result = CommandRunner().run("exit 3", tmp_path, 10)
    assert result.exit_code == 3
    assert result.passed is False
    assert result.ran is True


def test_timeout_produces_timed_out(tmp_path):
    result = CommandRunner().run("sleep 5", tmp_path, 1)
    assert result.timed_out is True
    assert result.passed is False
    assert result.ran is False


def test_large_output_is_truncated_in_memory(tmp_path):
    backend = LocalExecutionBackend(max_output_chars=1000)
    result = backend.run("python3 -c \"print('x'*50000)\"", tmp_path, 10)
    assert len(result.stdout) < 5000
    assert "truncated" in result.stdout


def test_stderr_captured(tmp_path):
    result = CommandRunner().run("python3 -c 'import sys; sys.stderr.write(\"bad\")'", tmp_path, 10)
    assert "bad" in result.stderr


def test_nonexistent_command_returns_127(tmp_path):
    result = CommandRunner().run("definitely_not_a_command_xyz", tmp_path, 10)
    assert result.exit_code == 127
    assert result.passed is False
