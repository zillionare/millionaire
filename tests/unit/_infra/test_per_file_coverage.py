"""v0.2-003 FR-0102 AC-FR-0102-1..5 per-file coverage checker tests."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path


CHECKER = Path(__file__).resolve().parents[1] / "_checkers/per_file_coverage.py"


def _run_checker(tmp_path: Path, payload: dict, waivers: list[dict] | None = None):
    coverage = tmp_path / "coverage.json"
    waiver_file = tmp_path / "coverage-waivers.json"
    coverage.write_text(json.dumps(payload))
    waiver_file.write_text(json.dumps({"waivers": waivers or []}))
    return subprocess.run(
        [sys.executable, str(CHECKER), str(coverage), str(waiver_file)],
        capture_output=True,
        text=True,
        check=False,
    )


def _coverage(percent: float, files: dict[str, dict]) -> dict:
    return {"totals": {"percent_covered": percent}, "files": files}


def _file(percent: float, statements: int = 10) -> dict:
    return {"summary": {"percent_covered": percent, "num_statements": statements}}


def test_rejects_a_79_99_percent_non_waived_production_file(tmp_path):
    """AC-FR-0102-1: a 79.99% quantide module blocks an otherwise 96% report."""
    result = _run_checker(tmp_path, _coverage(96, {"quantide/a.py": _file(79.99)}))

    assert result.returncode == 1
    assert "quantide/a.py" in result.stderr
    assert "79.99" in result.stderr


def test_accepts_covered_files_and_skips_zero_statement_files(tmp_path):
    """AC-FR-0102-2..3: executable __init__ files count while zero-statement files do not."""
    result = _run_checker(
        tmp_path,
        _coverage(96, {"quantide/__init__.py": _file(80, 1), "quantide/empty.py": _file(0, 0)}),
    )

    assert result.returncode == 0


def test_rejects_missing_coverage_schema_fields(tmp_path):
    """AC-FR-0102-5: malformed coverage reports fail with a useful diagnostic."""
    result = _run_checker(tmp_path, {"totals": {}, "files": {}})

    assert result.returncode == 1
    assert "percent_covered" in result.stderr


def test_rejects_an_expired_waiver(tmp_path):
    """AC-FR-0102-4: expired temporary waivers cannot bypass the file threshold."""
    waiver = {
        "module": "quantide/a.py",
        "current_coverage": 70.0,
        "reason": "FR-0102 gap: coverage work is pending.",
        "expires_at": str(date.today() - timedelta(days=1)),
        "followup_issue": "https://github.com/zillionare/millionaire/issues/999",
    }
    result = _run_checker(tmp_path, _coverage(96, {"quantide/a.py": _file(70)}), [waiver])

    assert result.returncode == 1
    assert "expired" in result.stderr


def test_rejects_a_waiver_without_followup_issue(tmp_path):
    """AC-FR-0102-4: every waiver requires a non-empty follow-up issue URL."""
    waiver = {
        "module": "quantide/a.py",
        "current_coverage": 70.0,
        "reason": "FR-0102 gap: coverage work is pending.",
        "expires_at": str(date.today() + timedelta(days=1)),
        "followup_issue": "",
    }
    result = _run_checker(tmp_path, _coverage(96, {"quantide/a.py": _file(70)}), [waiver])

    assert result.returncode == 1
    assert "followup_issue" in result.stderr
