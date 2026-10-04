"""JUnit XML parsing for pytest results.

We rely on ``pytest --junitxml`` because it gives exact, comparable test IDs,
which the regression rule depends on:

    new_failures = candidate_failed_test_ids - baseline_failed_test_ids
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..domain import TestOutcome, TestSuiteResult

_FAILURE_TAGS = {"failure", "error", "skipped"}


def _test_id(classname: str, name: str) -> str:
    if classname:
        return f"{classname}::{name}"
    return name


def parse_junit_xml(text: str, command: str = "") -> TestSuiteResult:
    """Parse a pytest JUnit XML report into a :class:`TestSuiteResult`."""

    result = TestSuiteResult(command=command, ran=True)
    text = (text or "").strip()
    if not text:
        result.ran = False
        return result

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        result.ran = False
        return result

    # JUnit root can be <testsuites> (with <testsuite> children) or <testsuite>.
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        suites = list(root.iter("testsuite"))

    for suite in suites:
        for case in suite.findall("testcase"):
            classname = case.get("classname", "") or ""
            name = case.get("name", "") or ""
            outcome = "passed"
            message = ""
            for child in case:
                tag = child.tag.split("}")[-1]
                if tag in _FAILURE_TAGS:
                    outcome = "failed" if tag == "failure" else tag
                    message = (child.get("message") or (child.text or "")).strip()
                    break
            result.outcomes.append(
                TestOutcome(
                    test_id=_test_id(classname, name),
                    classname=classname,
                    outcome=outcome,
                    message=message[:500],
                )
            )

    result.total = len(result.outcomes)
    result.passed = sum(1 for o in result.outcomes if o.outcome == "passed")
    result.failed = sum(1 for o in result.outcomes if o.outcome == "failed")
    result.errors = sum(1 for o in result.outcomes if o.outcome == "error")
    result.skipped = sum(1 for o in result.outcomes if o.outcome == "skipped")
    return result


def suites_equal(a: TestSuiteResult, b: TestSuiteResult) -> bool:
    return a.outcomes == b.outcomes


__all__ = ["_test_id", "parse_junit_xml", "suites_equal"]
