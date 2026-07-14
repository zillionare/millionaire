"""Build coverage-file-classification.json per spec FR-0801/FR-0802.

Inputs:
- /tmp/cov-modes.json: latest pytest --cov JSON (current coverage)
- .louke/project/specs/v0.2-004-coverage-recovery/recovery/production-contracts/*.json:
  per-shard inventory with origin (v0.2-added / pre-v0.2-existing) and statements count

Output:
- .louke/project/specs/v0.2-004-coverage-recovery/coverage-file-classification.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


SPEC_DIR = Path(".louke/project/specs/v0.2-004-coverage-recovery")
SHARD_DIR = SPEC_DIR / "recovery" / "production-contracts"
COVERAGE_JSON = Path("/tmp/cov-modes.json")
OUT_PATH = SPEC_DIR / "coverage-file-classification.json"

V02_THRESHOLD = 95.0
RETAINED_THRESHOLD = 80.0


def load_inventory() -> dict[str, dict]:
    """Aggregate per-shard inventory into one path → record dict."""
    records: dict[str, dict] = {}
    for sf in sorted(SHARD_DIR.iterdir()):
        if not sf.suffix == ".json":
            continue
        with open(sf) as f:
            data = json.load(f)
        for rec in data.get("records", []):
            path = rec.get("path")
            if not path:
                continue
            records[path] = rec
    return records


def load_coverage() -> dict[str, dict]:
    """Load current coverage.json (pytest --cov output)."""
    with open(COVERAGE_JSON) as f:
        data = json.load(f)
    return data.get("files", {})


def build_classification() -> dict:
    inventory = load_inventory()
    coverage = load_coverage()

    classified_files = []
    v02_under_threshold = []
    retained_under_threshold = []

    for path, rec in sorted(inventory.items()):
        origin = rec.get("origin", "unknown")
        cov_record = coverage.get(path, {})
        cov_summary = cov_record.get("summary", {}) if isinstance(cov_record, dict) else {}

        # Use live coverage when available, fall back to inventory's stored value.
        percent_covered = cov_summary.get("percent_covered", rec.get("percent_covered", 0.0))
        num_statements = cov_summary.get("num_statements", rec.get("num_statements", 0))
        num_branches = cov_summary.get("num_branches", rec.get("num_branches", 0))
        covered_branches = cov_summary.get("covered_branches", rec.get("covered_branches", 0))

        threshold = V02_THRESHOLD if origin == "v0.2-added" else RETAINED_THRESHOLD
        is_pass = (
            num_statements == 0
            or percent_covered >= threshold
        )

        classified_files.append({
            "path": path,
            "origin": origin,
            "threshold": threshold,
            "percent_covered": round(percent_covered, 2),
            "num_statements": num_statements,
            "num_branches": num_branches,
            "covered_branches": covered_branches,
            "coverage_status": rec.get("coverage_status", "measured"),
            "passes_threshold": is_pass,
        })

        if not is_pass and num_statements > 0:
            if origin == "v0.2-added":
                v02_under_threshold.append((path, percent_covered, num_statements))
            else:
                retained_under_threshold.append((path, percent_covered, num_statements))

    v02_count = sum(1 for f in classified_files if f["origin"] == "v0.2-added")
    retained_count = sum(1 for f in classified_files if f["origin"] == "pre-v0.2-existing")

    summary = {
        "total_files": len(classified_files),
        "v0.2_added_count": v02_count,
        "pre_v0.2_retained_count": retained_count,
        "v0.2_added_passing": v02_count - len(v02_under_threshold),
        "pre_v0.2_retained_passing": retained_count - len(retained_under_threshold),
        "v0.2_added_under_threshold": [
            {"path": p, "percent_covered": round(c, 2), "num_statements": n}
            for p, c, n in v02_under_threshold
        ],
        "pre_v0.2_retained_under_threshold": [
            {"path": p, "percent_covered": round(c, 2), "num_statements": n}
            for p, c, n in retained_under_threshold
        ],
    }

    return {
        "schema_version": 1,
        "spec_id": "v0.2-004-coverage-recovery",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_source": str(COVERAGE_JSON),
        "thresholds": {
            "v0.2_added": V02_THRESHOLD,
            "pre_v0.2_retained": RETAINED_THRESHOLD,
        },
        "summary": summary,
        "files": classified_files,
    }


def main() -> int:
    if not COVERAGE_JSON.exists():
        print(f"ERROR: coverage JSON not found at {COVERAGE_JSON}", flush=True)
        return 1
    classification = build_classification()
    with open(OUT_PATH, "w") as f:
        json.dump(classification, f, indent=2, sort_keys=False)
    print(f"wrote {OUT_PATH}")
    print(f"  total files: {classification['summary']['total_files']}")
    print(f"  v0.2-added: {classification['summary']['v0.2_added_count']} "
          f"({classification['summary']['v0.2_added_passing']} pass, "
          f"{len(classification['summary']['v0.2_added_under_threshold'])} fail)")
    print(f"  pre-v0.2-retained: {classification['summary']['pre_v0.2_retained_count']} "
          f"({classification['summary']['pre_v0.2_retained_passing']} pass, "
          f"{len(classification['summary']['pre_v0.2_retained_under_threshold'])} fail)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
