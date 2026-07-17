"""Offline E2E journeys for the v0.2-004 classified coverage gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


CHECKER = Path("tests/unit/_checkers/per_file_coverage.py")
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


def _coverage(overall: float, files: dict[str, tuple[float, int]]) -> dict:
    return {
        "totals": {"percent_covered": overall},
        "files": {
            path: {
                "summary": {
                    "percent_covered": percent,
                    "num_statements": statements,
                    "covered_lines": round(statements * percent / 100),
                }
            }
            for path, (percent, statements) in files.items()
        },
    }


def _run(coverage: dict, inventory: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        coverage_path = root / "coverage.json"
        inventory_path = root / "inventory.json"
        waivers_path = root / "waivers.json"
        report_path = root / "report.json"
        coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
        inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
        waivers_path.write_text(
            json.dumps(
                {
                    "schema": "coverage-waivers/v1",
                    "spec_id": SPEC_ID,
                    "waivers": [],
                }
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                str(coverage_path),
                str(waivers_path),
                "--inventory",
                str(inventory_path),
                "--report",
                str(report_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return result, report


def test_classification_aware_threshold_failure_journey() -> None:
    """AC-NFR1001-02/03: one new and one retained under-target path both block exit."""
    inventory = _inventory(
        [("quantide/new.py", "v0.2-added"), ("quantide/old.py", "pre-v0.2-existing")]
    )
    result, report = _run(
        _coverage(96.0, {"quantide/new.py": (94.99, 100), "quantide/old.py": (79.99, 100)}),
        inventory,
    )

    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    assert report["counts"]["failed"] == 2
    assert {row["target"] for row in report["rows"]} == {80.0, 95.0}


def test_strict_overall_threshold_failure_journey() -> None:
    """AC-NFR1001-01: an otherwise valid report at exactly 95 overall fails."""
    inventory = _inventory([("quantide/old.py", "pre-v0.2-existing")])
    result, report = _run(
        _coverage(95.0, {"quantide/old.py": (100.0, 10)}), inventory
    )

    assert result.returncode == 1
    assert report["overall"]["status"] == "fail"
    assert report["verdict"] == "FAIL"


def test_valid_classification_and_zero_statement_journey() -> None:
    """AC-NFR1001-02/03/04: valid 95/80 rows pass and zero-line rows are N/A."""
    inventory = _inventory(
        [
            ("quantide/new.py", "v0.2-added"),
            ("quantide/old.py", "pre-v0.2-existing"),
            ("quantide/empty.py", "pre-v0.2-existing"),
        ]
    )
    result, report = _run(
        _coverage(
            96.0,
            {
                "quantide/new.py": (95.0, 10),
                "quantide/old.py": (80.0, 10),
                "quantide/empty.py": (100.0, 0),
            },
        ),
        inventory,
    )

    assert result.returncode == 0, result.stderr
    assert report["verdict"] == "PASS"
    assert report["counts"]["threshold_not_applicable"] == 1


def test_manifest_inequality_failure_journey() -> None:
    """AC-FR1001-01/03: simultaneous missing and extra coverage paths are explicit failures."""
    inventory = _inventory([("quantide/expected.py", "pre-v0.2-existing")])
    result, report = _run(
        _coverage(96.0, {"quantide/extra.py": (100.0, 10)}), inventory
    )

    assert result.returncode == 1
    assert any("missing from coverage.json" in reason for reason in report["reasons"])
    assert any("extra path absent from inventory" in reason for reason in report["reasons"])


def test_malformed_inventory_failure_journey() -> None:
    """AC-FR1001-01/02: malformed inventory input cannot produce an accepted report."""
    inventory = _inventory([("outside/a.txt", "unknown")])
    result, report = _run(
        _coverage(96.0, {"quantide/a.py": (100.0, 10)}), inventory
    )

    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    assert any("malformed path" in reason for reason in report["reasons"])
