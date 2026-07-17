"""Contract tests for the v0.2-004 classification-aware coverage checker."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


CHECKER = Path(__file__).resolve().parents[1] / "_checkers/per_file_coverage.py"
SPEC_ID = "v0.2-004-coverage-recovery"


def _inventory(records: list[tuple[str, str]]) -> dict:
    return {
        "schema": "production-inventory-index/v2",
        "spec_id": SPEC_ID,
        "record_count": len(records),
        "records": [
            {
                "record_id": f"prod-{index:04d}",
                "path": path,
                "origin": origin,
                "classification": (
                    "active v0.2 product"
                    if origin == "v0.2-added"
                    else "active retained legacy"
                ),
            }
            for index, (path, origin) in enumerate(records)
        ],
    }


def _coverage(percent: float, files: dict[str, tuple[float, int]]) -> dict:
    return {
        "totals": {"percent_covered": percent},
        "files": {
            path: {
                "summary": {
                    "percent_covered": file_percent,
                    "num_statements": statements,
                    "covered_lines": round(statements * file_percent / 100),
                }
            }
            for path, (file_percent, statements) in files.items()
        },
    }


def _run_checker(
    tmp_path: Path,
    coverage: dict,
    inventory: dict,
    waivers: list[dict] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    coverage_path = tmp_path / "coverage.json"
    inventory_path = tmp_path / "inventory.json"
    waiver_path = tmp_path / "coverage-waivers.json"
    report_path = tmp_path / "report.json"
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    waiver_path.write_text(
        json.dumps(
            {
                "schema": "coverage-waivers/v1",
                "spec_id": SPEC_ID,
                "waivers": waivers or [],
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            str(coverage_path),
            str(waiver_path),
            "--inventory",
            str(inventory_path),
            "--report",
            str(report_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, json.loads(report_path.read_text(encoding="utf-8"))


def test_classification_thresholds_are_enforced(tmp_path: Path) -> None:
    """AC-NFR1001-02/03: v0.2-added and retained paths use 95/80 targets."""
    inventory = _inventory(
        [("quantide/new.py", "v0.2-added"), ("quantide/old.py", "pre-v0.2-existing")]
    )
    result, report = _run_checker(
        tmp_path,
        _coverage(96.0, {"quantide/new.py": (94.99, 100), "quantide/old.py": (79.99, 100)}),
        inventory,
    )

    assert result.returncode == 1
    assert "quantide/new.py: 94.99% is below 95%" in result.stderr
    assert "quantide/old.py: 79.99% is below 80%" in result.stderr
    assert report["verdict"] == "FAIL"


def test_overall_threshold_is_strict(tmp_path: Path) -> None:
    """AC-NFR1001-01: exactly 95 percent overall is not greater than 95."""
    inventory = _inventory([("quantide/a.py", "pre-v0.2-existing")])
    result, report = _run_checker(
        tmp_path, _coverage(95.0, {"quantide/a.py": (100.0, 1)}), inventory
    )

    assert result.returncode == 1
    assert "must be greater than 95.0%" in result.stderr
    assert report["overall"]["status"] == "fail"


def test_valid_rows_and_zero_statement_row_are_reported(tmp_path: Path) -> None:
    """AC-NFR1001-02/03/04: passing classified rows include an explicit zero-line N/A."""
    inventory = _inventory(
        [
            ("quantide/new.py", "v0.2-added"),
            ("quantide/old.py", "pre-v0.2-existing"),
            ("quantide/empty.py", "pre-v0.2-existing"),
        ]
    )
    result, report = _run_checker(
        tmp_path,
        _coverage(
            96.0,
            {
                "quantide/new.py": (95.0, 20),
                "quantide/old.py": (80.0, 20),
                "quantide/empty.py": (100.0, 0),
            },
        ),
        inventory,
    )

    assert result.returncode == 0, result.stderr
    assert report["verdict"] == "PASS"
    assert report["counts"] == {
        "coverage": 3,
        "failed": 0,
        "inventory": 3,
        "passed": 2,
        "rows": 3,
        "threshold_not_applicable": 1,
        "waived": 0,
    }
    empty = next(row for row in report["rows"] if row["path"] == "quantide/empty.py")
    assert empty["status"] == "threshold_not_applicable"
    assert empty["threshold_applicable"] is False


def test_manifest_difference_is_blocking(tmp_path: Path) -> None:
    """AC-FR1001-01: missing and extra coverage paths both block the gate."""
    inventory = _inventory([("quantide/expected.py", "pre-v0.2-existing")])
    result, report = _run_checker(
        tmp_path,
        _coverage(96.0, {"quantide/extra.py": (100.0, 1)}),
        inventory,
    )

    assert result.returncode == 1
    assert "missing from coverage.json: quantide/expected.py" in result.stderr
    assert "extra path absent from inventory: quantide/extra.py" in result.stderr
    assert report["verdict"] == "FAIL"


def _waiver(module: str) -> dict:
    return {
        "module": module,
        "current_coverage": 70.0,
        "reason": "File-specific retained behavior remains blocked.",
        "evidence": ["artifacts/coverage-recovery/run/legacy.json"],
        "approved_by": "Aaron",
        "approved_at": "2098-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "followup_issue": "https://github.com/zillionare/millionaire/issues/999",
    }


def test_valid_retained_waiver_is_file_specific(tmp_path: Path) -> None:
    """AC-FR1801-01/02: a complete Aaron-approved retained waiver applies to one file."""
    inventory = _inventory([("quantide/legacy.py", "pre-v0.2-existing")])
    result, report = _run_checker(
        tmp_path,
        _coverage(96.0, {"quantide/legacy.py": (70.0, 10)}),
        inventory,
        [_waiver("quantide/legacy.py")],
    )

    assert result.returncode == 0, result.stderr
    assert report["rows"][0]["status"] == "waived"


def test_v0_2_added_waiver_is_rejected(tmp_path: Path) -> None:
    """AC-FR1801-03/04: no waiver can lower a v0.2-added file target."""
    inventory = _inventory([("quantide/new.py", "v0.2-added")])
    result, report = _run_checker(
        tmp_path,
        _coverage(96.0, {"quantide/new.py": (70.0, 10)}),
        inventory,
        [_waiver("quantide/new.py")],
    )

    assert result.returncode == 1
    assert "waiver for v0.2-added module quantide/new.py is prohibited" in result.stderr
    assert report["rows"][0]["status"] == "fail"
