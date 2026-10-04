"""JUnit XML parser tests (Phase 4 exit criteria)."""

from proofpatch.verification.pytest_parser import parse_junit_xml

ALL_PASS = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="pytest" tests="3" failures="0">
    <testcase classname="tests.test_session" name="test_a" time="0.01"/>
    <testcase classname="tests.test_session" name="test_b" time="0.01"/>
    <testcase classname="tests.test_other" name="test_c" time="0.01"/>
  </testsuite>
</testsuites>"""

ONE_FAIL = """<?xml version="1.0"?>
<testsuite name="pytest" tests="2" failures="1">
  <testcase classname="tests.test_session" name="test_ok" time="0.01"/>
  <testcase classname="tests.test_session" name="test_bad" time="0.01">
    <failure message="assert False is True">Traceback ...</failure>
  </testcase>
</testsuite>"""

WITH_ERROR_AND_SKIP = """<?xml version="1.0"?>
<testsuite name="pytest" tests="3">
  <testcase classname="t" name="test_error" time="0.01">
    <error message="boom"/>
  </testcase>
  <testcase classname="t" name="test_skipped" time="0.01">
    <skipped message="no"/>
  </testcase>
  <testcase classname="t" name="test_pass" time="0.01"/>
</testsuite>"""


def test_all_pass():
    result = parse_junit_xml(ALL_PASS, command="pytest")
    assert result.ran is True
    assert result.total == 3
    assert result.passed == 3
    assert result.failed == 0
    assert result.failed_ids == set()


def test_one_fail_parses_exact_id():
    result = parse_junit_xml(ONE_FAIL, command="pytest")
    assert result.failed == 1
    assert result.failed_ids == {"tests.test_session::test_bad"}
    outcome = next(o for o in result.outcomes if o.outcome == "failed")
    assert "assert False" in outcome.message


def test_error_and_skip():
    result = parse_junit_xml(WITH_ERROR_AND_SKIP, command="pytest")
    assert result.errors == 1
    assert result.skipped == 1
    assert "t::test_error" in result.failed_ids  # errors count as failures


def test_empty_input_is_not_ran():
    result = parse_junit_xml("", command="pytest")
    assert result.ran is False
    assert result.total == 0


def test_malformed_xml_is_not_ran():
    result = parse_junit_xml("<not-closed", command="pytest")
    assert result.ran is False


def test_new_failure_comparison_rule():
    baseline = parse_junit_xml(ALL_PASS, command="pytest")
    candidate = parse_junit_xml(ONE_FAIL, command="pytest")
    new_failures = candidate.failed_ids - baseline.failed_ids
    assert new_failures == {"tests.test_session::test_bad"}
