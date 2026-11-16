"""Acceptance matrix must depend on execution evidence, not static labels."""

from __future__ import annotations

import subprocess
import sys

from quantide.audit.acceptance import collect_nodeids, matrix

_ALPHA = "tests/unit/quantide/web/pages/system/test_alpha_ledger_removed.py"
_ALPHA_NODE = f"{_ALPHA}::test_alpha_ledger_page_removed"


def test_matrix_without_results_reports_mapped_not_covered() -> None:
    payload = matrix()
    assert payload["covered"] == 0
    assert not payload["release_ready"]
    assert "AC-4014" in payload["pending"]
    assert {entry["status"] for entry in payload["entries"]} <= {
        "mapped",
        "manual",
        "partial",
        "missing_evidence",
    }


def _report(
    tmp_path,
    name: str,
    child: str = "",
    suffix: str = "",
    *,
    classname: str = "tests.unit.quantide.web.pages.system.test_alpha_ledger_removed",
    nodes: tuple[str, ...] = (_ALPHA_NODE,),
) -> dict:
    report = tmp_path / f"results-{name}-{suffix or 'pass'}.xml"
    report.write_text(
        f'<testsuites><testsuite><testcase classname="{classname}" '
        f'name="{name}">{child}</testcase></testsuite></testsuites>',
        encoding="utf-8",
    )
    return matrix([report], {"AC-4302": nodes})


def test_matrix_requires_full_passing_file_evidence(tmp_path) -> None:
    payload = _report(tmp_path, "test_alpha_ledger_page_removed")
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "covered"


def test_acceptance_rejects_failed_skipped_error_and_unknown_cases(tmp_path) -> None:
    for label, child in (
        ("failure", '<failure message="x"/>'),
        ("error", '<error message="x"/>'),
        ("skipped", "<skipped/>"),
    ):
        payload = _report(tmp_path, "test_alpha_ledger_page_removed", child, label)
        statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
        assert statuses["AC-4302"] == "mapped"

    payload = _report(tmp_path, "not_real")
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "mapped"


def test_acceptance_rejects_partial_class_execution(tmp_path) -> None:
    file_path = _ALPHA
    classname = "tests.unit.quantide.web.pages.system.test_alpha_ledger_removed.TestLedger"
    nodes = (f"{file_path}::TestLedger::test_one", f"{file_path}::TestLedger::test_two")
    payload = _report(
        tmp_path,
        "test_one",
        classname=classname,
        nodes=nodes,
    )
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "mapped"


def test_acceptance_does_not_merge_parameter_skip_with_passed_instance(tmp_path) -> None:
    nodes = (
        f"{_ALPHA}::test_alpha_ledger_page_removed[p1]",
        f"{_ALPHA}::test_alpha_ledger_page_removed[p2]",
    )
    report = tmp_path / "params.xml"
    report.write_text(
        "<testsuites><testsuite>"
        '<testcase classname="tests.unit.quantide.web.pages.system.test_alpha_ledger_removed" '
        'name="test_alpha_ledger_page_removed[p1]" />'
        '<testcase classname="tests.unit.quantide.web.pages.system.test_alpha_ledger_removed" '
        'name="test_alpha_ledger_page_removed[p2]"><skipped /></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    payload = matrix([report], {"AC-4302": nodes})
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "mapped"


def test_real_pytest_partial_parameterization_is_not_covered(tmp_path) -> None:
    synthetic = "tests/unit/quantide/audit/test_synthetic.py"
    statistics = "tests/unit/quantide/audit/test_statistics.py"
    expected = collect_nodeids([synthetic, statistics])
    report = tmp_path / "partial.xml"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            synthetic,
            statistics,
            "--deselect="
            "tests/unit/quantide/audit/test_synthetic.py::"
            "test_pearson_power_recovers_positive_and_negative_signals[-0.25]",
            "-q",
            "-p",
            "no:cacheprovider",
            "--disable-socket",
            "--allow-unix-socket",
            "--allow-hosts=127.0.0.1,::1,localhost",
            f"--junitxml={report}",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    manifest = {
        "AC-4004": sorted(
            nodeid
            for nodeid in expected
            if nodeid.startswith(synthetic + "::") or nodeid.startswith(statistics + "::")
        ),
        "AC-4005": sorted(nodeid for nodeid in expected if nodeid.startswith(synthetic + "::")),
    }
    payload = matrix([report], manifest)
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4004"] == "mapped"
    assert statuses["AC-4005"] == "mapped"


def test_skipped_instance_cannot_be_overwritten_by_later_pass(tmp_path) -> None:
    skipped = tmp_path / "skipped.xml"
    passed = tmp_path / "passed.xml"
    body = (
        "<testsuites><testsuite><testcase "
        'classname="tests.unit.quantide.web.pages.system.test_alpha_ledger_removed" '
        'name="test_alpha_ledger_page_removed">{}</testcase></testsuite></testsuites>'
    )
    skipped.write_text(body.format("<skipped />"), encoding="utf-8")
    passed.write_text(body.format(""), encoding="utf-8")
    payload = matrix([skipped, passed], {"AC-4302": [_ALPHA_NODE]})
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "mapped"
