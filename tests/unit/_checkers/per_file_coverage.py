"""Validate the v0.2-004 overall and classification-aware coverage gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SPEC_ID = "v0.2-004-coverage-recovery"
OVERALL_THRESHOLD = 95.0
TARGETS = {"v0.2-added": 95.0, "pre-v0.2-existing": 80.0}
DEFAULT_SPEC_DIR = Path(".louke/project/specs/v0.2-004-coverage-recovery")
REQUIRED_WAIVER_FIELDS = {
    "module",
    "current_coverage",
    "reason",
    "evidence",
    "approved_by",
    "approved_at",
    "expires_at",
    "followup_issue",
}


def _read_json(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read {label} {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must contain a JSON object")
        return {}
    return data


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _timestamp(value: Any, field: str, module: Any, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"waiver for {module!r} has invalid {field}")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"waiver for {module!r} has invalid {field}")
        return None
    if parsed.tzinfo is None:
        errors.append(f"waiver for {module!r} has timezone-less {field}")
        return None
    return parsed.astimezone(UTC)


def _inventory_rows(data: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    if data.get("spec_id") != SPEC_ID:
        errors.append(f"inventory spec_id must be {SPEC_ID}")
    records = data.get("records")
    if not isinstance(records, list):
        errors.append("inventory records must be a list")
        return {}

    rows: dict[str, dict[str, Any]] = {}
    record_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            errors.append("inventory record must be an object")
            continue
        path = record.get("path")
        record_id = record.get("record_id")
        origin = record.get("origin")
        if not isinstance(path, str) or not path.startswith("quantide/") or not path.endswith(".py"):
            errors.append(f"inventory has malformed path {path!r}")
            continue
        if path in rows:
            errors.append(f"inventory has duplicate path {path}")
            continue
        if not isinstance(record_id, str) or not record_id or record_id in record_ids:
            errors.append(f"inventory has duplicate or missing record_id for {path}")
        else:
            record_ids.add(record_id)
        if origin not in TARGETS:
            errors.append(f"inventory {path} has unsupported origin {origin!r}")
        rows[path] = record

    expected_count = data.get("record_count")
    if not isinstance(expected_count, int) or expected_count != len(records):
        errors.append(
            f"inventory record_count {expected_count!r} does not match {len(records)} records"
        )
    return rows


def _valid_waivers(
    data: dict[str, Any], inventory: dict[str, dict[str, Any]], errors: list[str]
) -> dict[str, str]:
    if data.get("schema") != "coverage-waivers/v1" or data.get("spec_id") != SPEC_ID:
        errors.append("coverage waivers have an invalid schema or spec_id")
    waivers = data.get("waivers")
    if not isinstance(waivers, list):
        errors.append("coverage waivers must contain a waivers list")
        return {}

    valid: dict[str, str] = {}
    now = datetime.now(UTC)
    for waiver in waivers:
        if not isinstance(waiver, dict):
            errors.append("waiver must be an object")
            continue
        missing = REQUIRED_WAIVER_FIELDS - waiver.keys()
        module = waiver.get("module")
        if missing:
            errors.append(f"waiver for {module!r} is missing {sorted(missing)}")
            continue
        if not isinstance(module, str) or module not in inventory:
            errors.append(f"waiver module {module!r} is absent from inventory")
            continue
        if module in valid:
            errors.append(f"duplicate waiver for {module}")
            continue
        if inventory[module].get("origin") != "pre-v0.2-existing":
            errors.append(f"waiver for v0.2-added module {module} is prohibited")
            continue

        current = waiver["current_coverage"]
        evidence = waiver["evidence"]
        issue = urlparse(str(waiver["followup_issue"]))
        approved_at = _timestamp(waiver["approved_at"], "approved_at", module, errors)
        expires_at = _timestamp(waiver["expires_at"], "expires_at", module, errors)
        module_errors: list[str] = []
        if not isinstance(current, (int, float)) or isinstance(current, bool) or not 0 <= current <= 100:
            module_errors.append("invalid current_coverage")
        if not isinstance(waiver["reason"], str) or not waiver["reason"].strip():
            module_errors.append("invalid reason")
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ):
            module_errors.append("invalid evidence")
        if waiver["approved_by"] != "Aaron":
            module_errors.append("approved_by must be Aaron")
        if expires_at is not None and expires_at <= now:
            module_errors.append("expired")
        if approved_at is not None and expires_at is not None and approved_at >= expires_at:
            module_errors.append("approved_at must precede expires_at")
        if issue.scheme != "https" or issue.netloc != "github.com" or not issue.path.strip("/"):
            module_errors.append("invalid followup_issue")
        if module_errors:
            errors.extend(f"waiver for {module} has {reason}" for reason in module_errors)
            continue
        valid[module] = f"waiver:{module}"
    return valid


def evaluate(
    coverage_path: Path, waiver_path: Path, inventory_path: Path
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    coverage = _read_json(coverage_path, "coverage.json", errors)
    waiver_data = _read_json(waiver_path, "coverage waivers", errors)
    inventory_data = _read_json(inventory_path, "production inventory", errors)
    inventory = _inventory_rows(inventory_data, errors)

    totals = coverage.get("totals")
    files = coverage.get("files")
    overall: float | None = None
    if isinstance(totals, dict) and isinstance(totals.get("percent_covered"), (int, float)):
        overall = float(totals["percent_covered"])
        if overall <= OVERALL_THRESHOLD:
            errors.append(
                f"overall coverage {overall:.2f}% must be greater than {OVERALL_THRESHOLD:.1f}%"
            )
    else:
        errors.append("coverage.json totals.percent_covered is required")
    if not isinstance(files, dict):
        errors.append("coverage.json files is required")
        files = {}

    coverage_paths = {
        path for path in files if isinstance(path, str) and path.startswith("quantide/")
    }
    inventory_paths = set(inventory)
    for path in sorted(inventory_paths - coverage_paths):
        errors.append(f"inventory path is missing from coverage.json: {path}")
    for path in sorted(coverage_paths - inventory_paths):
        errors.append(f"coverage.json has extra path absent from inventory: {path}")

    waivers = _valid_waivers(waiver_data, inventory, errors)
    rows: list[dict[str, Any]] = []
    for path, inventory_row in sorted(inventory.items()):
        record = files.get(path)
        summary = record.get("summary") if isinstance(record, dict) else None
        num_statements = summary.get("num_statements") if isinstance(summary, dict) else None
        percent = summary.get("percent_covered") if isinstance(summary, dict) else None
        covered_lines = summary.get("covered_lines") if isinstance(summary, dict) else None
        origin = inventory_row.get("origin")
        target = TARGETS.get(origin)
        row_reasons: list[str] = []
        waiver_id = waivers.get(path)
        applicable = isinstance(num_statements, int) and num_statements > 0
        status = "pass"

        if not isinstance(num_statements, int) or not isinstance(percent, (int, float)):
            row_reasons.append("missing summary.percent_covered or summary.num_statements")
            status = "fail"
        elif num_statements == 0:
            status = "threshold_not_applicable"
        elif target is None:
            row_reasons.append("unsupported inventory origin")
            status = "fail"
        elif float(percent) < target and waiver_id is None:
            row_reasons.append(f"{float(percent):.2f}% is below {target:.0f}%")
            status = "fail"
        elif float(percent) < target:
            status = "waived"

        if row_reasons:
            errors.extend(f"{path}: {reason}" for reason in row_reasons)
        rows.append(
            {
                "path": path,
                "classification": inventory_row.get("classification"),
                "origin": origin,
                "num_statements": num_statements,
                "covered_lines": covered_lines,
                "percent_covered": percent,
                "target": target,
                "threshold_applicable": applicable,
                "waiver_id": waiver_id,
                "status": status,
                "reasons": row_reasons,
            }
        )

    counts = {
        "inventory": len(inventory_paths),
        "coverage": len(coverage_paths),
        "rows": len(rows),
        "passed": sum(row["status"] == "pass" for row in rows),
        "waived": sum(row["status"] == "waived" for row in rows),
        "threshold_not_applicable": sum(
            row["status"] == "threshold_not_applicable" for row in rows
        ),
        "failed": sum(row["status"] == "fail" for row in rows),
    }
    report = {
        "schema": "per-file-coverage/v1",
        "spec_id": SPEC_ID,
        "run_id": os.environ.get("RUN_ID", "unspecified"),
        "coverage_sha256": _sha256(coverage_path),
        "inventory_sha256": _sha256(inventory_path),
        "overall": {
            "metric": "totals.percent_covered",
            "percent_covered": overall,
            "target": f">{OVERALL_THRESHOLD:.1f}",
            "status": "pass" if overall is not None and overall > OVERALL_THRESHOLD else "fail",
        },
        "rows": rows,
        "counts": counts,
        "verdict": "PASS" if not errors else "FAIL",
        "reasons": errors,
    }
    return report, errors


def check(
    coverage_path: Path, waiver_path: Path, inventory_path: Path | None = None
) -> list[str]:
    """Return all v0.2-004 gate violations for callers that need only diagnostics."""
    inventory_path = inventory_path or DEFAULT_SPEC_DIR / "recovery/production-file-inventory.json"
    return evaluate(coverage_path, waiver_path, inventory_path)[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage", nargs="?", default="coverage.json", type=Path)
    parser.add_argument(
        "waivers", nargs="?", default=DEFAULT_SPEC_DIR / "coverage-waivers.json", type=Path
    )
    parser.add_argument(
        "--inventory",
        default=DEFAULT_SPEC_DIR / "recovery/production-file-inventory.json",
        type=Path,
    )
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report, errors = evaluate(args.coverage, args.waivers, args.inventory)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
