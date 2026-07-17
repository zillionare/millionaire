"""Compare production Python paths on disk, in inventory shards, and coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read {label} {path}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} must contain a JSON object")
        return {}
    return value


def _commit_sha() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _inventory_paths(inventory_path: Path, errors: list[str]) -> set[str]:
    inventory = _load(inventory_path, "production inventory", errors)
    shards = inventory.get("shards")
    if not isinstance(shards, list):
        errors.append("production inventory shards must be a list")
        return set()
    paths: set[str] = set()
    for row in shards:
        relative = row.get("path") if isinstance(row, dict) else None
        if not isinstance(relative, str):
            errors.append("production inventory has malformed shard path")
            continue
        shard = _load(inventory_path.parent / relative, "production shard", errors)
        records = shard.get("records")
        if not isinstance(records, list):
            errors.append(f"production shard {relative} records must be a list")
            continue
        for record in records:
            path = record.get("path") if isinstance(record, dict) else None
            if not isinstance(path, str) or not path.startswith("quantide/") or not path.endswith(".py"):
                errors.append(f"production shard {relative} has malformed path {path!r}")
            elif path in paths:
                errors.append(f"production inventory has duplicate path {path}")
            else:
                paths.add(path)
    return paths


def evaluate(
    source: Path, inventory_path: Path, coverage_path: Path
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    root = source.parent
    disk = {
        path.relative_to(root).as_posix()
        for path in source.rglob("*.py")
        if path.is_file()
    }
    inventory = _inventory_paths(inventory_path, errors)
    coverage_data = _load(coverage_path, "coverage.json", errors)
    raw_files = coverage_data.get("files")
    if not isinstance(raw_files, dict):
        errors.append("coverage.json files must be an object")
        raw_files = {}
    coverage = {
        path
        for path in raw_files
        if isinstance(path, str) and path.startswith("quantide/") and path.endswith(".py")
    }
    malformed_coverage = [
        path for path in raw_files if not isinstance(path, str) or not path.endswith(".py")
    ]
    if malformed_coverage:
        errors.append(f"coverage.json has malformed paths: {malformed_coverage}")

    differences = {
        "disk_minus_inventory": sorted(disk - inventory),
        "inventory_minus_disk": sorted(inventory - disk),
        "inventory_minus_coverage": sorted(inventory - coverage),
        "coverage_minus_inventory": sorted(coverage - inventory),
    }
    for label, values in differences.items():
        if values:
            errors.append(f"{label}: {values}")
    report = {
        "schema": "source-manifest/v1",
        "run_id": os.environ.get("RUN_ID", "unspecified"),
        "commit_sha": _commit_sha(),
        "disk": sorted(disk),
        "inventory": sorted(inventory),
        "coverage": sorted(coverage),
        "counts": {
            "disk": len(disk),
            "inventory": len(inventory),
            "coverage": len(coverage),
        },
        **differences,
        "pins": {
            "inventory_sha256": _sha256(inventory_path) if inventory_path.is_file() else "",
            "coverage_sha256": _sha256(coverage_path) if coverage_path.is_file() else "",
        },
        "verdict": "PASS" if not errors else "FAIL",
        "reasons": errors,
    }
    return report, errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--source", required=True, type=Path)
    check_parser.add_argument("--inventory", required=True, type=Path)
    check_parser.add_argument("--coverage", required=True, type=Path)
    check_parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report, errors = evaluate(args.source, args.inventory, args.coverage)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
