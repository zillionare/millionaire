"""Executable counterexamples for the quality and release gates.

Run with unittest so quality CI does not import the application's pytest fixtures.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_quality, check_test_results

ROOT = Path(__file__).resolve().parents[2]


class StaticGateCounterexamples(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def source(self, name, content):
        path = self.directory / name
        path.write_text(content, encoding="utf-8")
        return path

    def run_tool(self, tool, *arguments):
        return subprocess.run(
            [sys.executable, "-m", tool, *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def pylint(self, rule, *paths):
        return self.run_tool(
            "pylint",
            f"--rcfile={ROOT / 'pyproject.toml'}",
            "--disable=all",
            f"--enable={rule}",
            "--score=n",
            *paths,
        )

    def assert_rejected(self, process, rule):
        self.assertNotEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn(rule, process.stdout + process.stderr)

    def test_cognitive_complexity_rejects_nested_branching(self):
        path = self.source(
            "nested.py",
            "def choose(a, b, c, d, e, f):\n"
            "    if a:\n        if b:\n            if c:\n                if d:\n"
            "                    if e:\n                        if f:\n"
            "                            return 1\n    return 0\n",
        )
        result = self.run_tool("flake8", f"--config={ROOT / '.flake8'}", path)
        self.assert_rejected(result, "CCR001")

    def test_line_width_rejects_a_long_statement(self):
        path = self.source("wide.py", 'VALUE = "' + "several words " * 10 + '"\n')
        result = self.run_tool("ruff", "check", "--config", ROOT / "pyproject.toml", path)
        self.assert_rejected(result, "E501")

    def test_module_length_rejects_more_than_1000_physical_lines(self):
        path = self.source("large.py", "VALUE = 1\n" + "# A documented line.\n" * 1000)
        self.assert_rejected(self.pylint("C0302", path), "C0302")

    def test_duplication_compares_different_modules(self):
        body = (
            "    result = []\n"
            "    for item in data:\n"
            "        value = item + 1\n"
            "        doubled = value * 2\n"
            "        adjusted = doubled - 3\n"
            "        bounded = max(adjusted, 0)\n"
            "        rendered = str(bounded)\n"
            "        result.append(rendered)\n"
            "    return result\n"
        )
        first = self.source("first.py", "def first(data):\n" + body)
        second = self.source("second.py", "def second(data):\n" + body)
        self.assert_rejected(self.pylint("R0801", first, second), "R0801")

    def test_method_statement_budget_is_enforced(self):
        body = "".join(f"    value = {number}\n" for number in range(51))
        path = self.source("statements.py", "def calculate():\n" + body + "    return value\n")
        self.assert_rejected(self.pylint("R0915", path), "R0915")

    def test_local_variable_budget_is_enforced(self):
        body = "".join(f"    value_{number} = {number}\n" for number in range(16))
        path = self.source("locals.py", "def calculate():\n" + body + "    return value_0\n")
        self.assert_rejected(self.pylint("R0914", path), "R0914")

    def test_clean_source_passes_the_three_analyzers(self):
        path = self.source(
            "clean.py",
            '"""Small pure calculation."""\n\ndef add(left, right):\n    return left + right\n',
        )
        checks = (
            self.run_tool("ruff", "check", "--config", ROOT / "pyproject.toml", path),
            self.run_tool("flake8", f"--config={ROOT / '.flake8'}", path),
            self.pylint("R0801,C0302,R0915,R0914", path),
        )
        for result in checks:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def report(self, xml):
        path = self.directory / "tests.xml"
        path.write_text(xml, encoding="utf-8")
        return path

    def test_namespace_modules_are_explicit_inputs_to_every_analyzer(self):
        for name in ("quantide/service/runtime.py", "scripts/check.py"):
            path = self.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("VALUE = 1\n")
        with patch.object(check_quality, "ROOT", self.directory):
            commands = check_quality.commands(sys.executable)
        for _, command in commands:
            self.assertIn("quantide/service/runtime.py", command)
            self.assertIn("scripts/check.py", command)

    def test_accepts_real_passing_cases(self):
        path = self.report(
            '<testsuites><testsuite><testcase name="one"/><testcase name="two"/></testsuite></testsuites>'
        )
        self.assertEqual(check_test_results.validate(path), 2)

    def test_empty_failed_skipped_and_xfailed_reports_are_rejected(self):
        for body in (
            "",
            "<testcase><failure/></testcase>",
            "<testcase><error/></testcase>",
            '<testcase><skipped type="pytest.xfail"/></testcase>',
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                check_test_results.validate(self.report(f"<testsuite>{body}</testsuite>"))

    def test_suite_errors_are_not_hidden_by_passing_cases(self):
        path = self.report('<testsuite errors="1"><testcase name="one"/></testsuite>')
        with self.assertRaises(ValueError):
            check_test_results.validate(path)

    def test_missing_tool_produces_a_failing_report(self):
        report = self.directory / "quality.json"
        with (
            patch.object(check_quality, "tool_versions", side_effect=ValueError("missing tool")),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = check_quality.main(["--report", str(report)])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(report.read_text())["passed"])

    def test_a_failed_scan_still_runs_the_other_checks(self):
        report = self.directory / "quality.json"
        results = [
            {"name": "lint", "exit_code": 1},
            {"name": "complexity", "exit_code": 0},
            {"name": "duplication", "exit_code": 0},
        ]
        with (
            patch.object(check_quality, "tool_versions", return_value={}),
            patch.object(check_quality, "source_digest", return_value=(1, "digest")),
            patch.object(check_quality, "run_check", side_effect=results) as scans,
        ):
            code = check_quality.main(["--report", str(report)])
        self.assertEqual(code, 1)
        self.assertEqual(scans.call_count, 3)
        self.assertFalse(json.loads(report.read_text())["passed"])

    def test_a_source_change_during_the_scan_cannot_receive_passing_evidence(self):
        report = self.directory / "quality.json"
        with (
            patch.object(check_quality, "tool_versions", return_value={}),
            patch.object(check_quality, "source_digest", side_effect=[(1, "before"), (1, "after")]),
            patch.object(check_quality, "run_check", return_value={"exit_code": 0}),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = check_quality.main(["--report", str(report)])
        self.assertEqual(code, 1)
        self.assertIn("changed during scan", json.loads(report.read_text())["error"])


if __name__ == "__main__":
    unittest.main()
