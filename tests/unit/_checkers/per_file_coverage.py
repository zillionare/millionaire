"""Block releases whose coverage report violates v0.2-003 FR-0102."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


OVERALL_THRESHOLD = 95.0
FILE_THRESHOLD = 80.0
REQUIRED_WAIVER_FIELDS = {
    "module", "current_coverage", "reason", "expires_at", "followup_issue"
}


def _read_json(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    """Read a JSON object from *path*, appending a contextual error on failure."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read {label} {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must contain a JSON object")
        return {}
    return data


def _valid_waivers(data: dict[str, Any], files: dict[str, Any], errors: list[str]) -> set[str]:
    """Validate waiver records and return modules eligible to bypass file checks."""
    modules: set[str] = set()
    waivers = data.get("waivers")
    if not isinstance(waivers, list):
        errors.append("coverage waivers must contain a waivers list")
        return modules
    for waiver in waivers:
        if not isinstance(waiver, dict) or REQUIRED_WAIVER_FIELDS - waiver.keys():
            errors.append("waiver is missing required fields")
            continue
        module = waiver["module"]
        issue = waiver["followup_issue"]
        try:
            expiry = date.fromisoformat(waiver["expires_at"])
        except (TypeError, ValueError):
            errors.append(f"waiver {module!r} has invalid expires_at")
            continue
        parsed_issue = urlparse(str(issue))
        if not isinstance(module, str) or module not in files:
            errors.append(f"waiver module {module!r} is absent from coverage.json")
        elif expiry < date.today():
            errors.append(f"waiver for {module} is expired")
        elif not isinstance(waiver["current_coverage"], (int, float)) or not 0 <= waiver["current_coverage"] <= 100:
            errors.append(f"waiver for {module} has invalid current_coverage")
        elif not isinstance(waiver["reason"], str) or not waiver["reason"].strip():
            errors.append(f"waiver for {module} has invalid reason")
        elif parsed_issue.scheme != "https" or not parsed_issue.netloc or not parsed_issue.path:
            errors.append(f"waiver for {module} has invalid followup_issue")
        else:
            modules.add(module)
    return modules


def check(coverage_path: Path, waiver_path: Path) -> list[str]:
    """Return all FR-0102 violations found in the supplied report and waiver list."""
    errors: list[str] = []
    coverage = _read_json(coverage_path, "coverage.json", errors)
    waivers = _read_json(waiver_path, "coverage waivers", errors)
    totals = coverage.get("totals")
    files = coverage.get("files")
    if not isinstance(totals, dict) or not isinstance(totals.get("percent_covered"), (int, float)):
        errors.append("coverage.json totals.percent_covered is required")
    elif totals["percent_covered"] < OVERALL_THRESHOLD:
        errors.append(f"overall coverage {totals['percent_covered']:.2f}% is below {OVERALL_THRESHOLD:.0f}%")
    if not isinstance(files, dict):
        errors.append("coverage.json files is required")
        return errors
    waived = _valid_waivers(waivers, files, errors)
    for module, record in files.items():
        if not isinstance(module, str) or not module.startswith("quantide/") or not module.endswith(".py"):
            continue
        summary = record.get("summary") if isinstance(record, dict) else None
        if not isinstance(summary, dict) or not isinstance(summary.get("num_statements"), int) or not isinstance(summary.get("percent_covered"), (int, float)):
            errors.append(f"{module} is missing summary.percent_covered or summary.num_statements")
        elif summary["num_statements"] > 0 and module not in waived and summary["percent_covered"] < FILE_THRESHOLD:
            errors.append(f"{module}: {summary['percent_covered']:.2f}% is below {FILE_THRESHOLD:.0f}%")
    return errors


def main(argv: list[str] | None = None) -> int:
    """Run the coverage gate and return 0 on success or 1 with diagnostics."""
    args = argv or sys.argv[1:]
    coverage_path = Path(args[0]) if args else Path("coverage.json")
    waiver_path = Path(args[1]) if len(args) > 1 else Path(".louke/project/specs/v0.2-003-coverage/coverage-waivers.json")
    errors = check(coverage_path, waiver_path)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
