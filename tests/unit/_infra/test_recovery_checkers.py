"""Contract tests for immutable recovery and source-manifest checkers."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

CHECKERS = Path(__file__).resolve().parents[1] / "_checkers"


def _load_checker(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, CHECKERS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_sha(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "quantide"
    source.mkdir()
    (source / "a.py").write_text("value = 1\n", encoding="utf-8")

    shard_dir = tmp_path / "production-contracts"
    shard_dir.mkdir()
    records = [{"record_id": "prod-a", "path": "quantide/a.py"}]
    shard = {
        "record_count": 1,
        "records_sha256": _canonical_sha(records),
        "records": records,
    }
    (shard_dir / "root.json").write_text(json.dumps(shard), encoding="utf-8")
    inventory = {
        "shards": [{"path": "production-contracts/root.json"}],
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(
        json.dumps({"files": {"quantide/a.py": {"summary": {}}}}), encoding="utf-8"
    )
    return source, inventory_path, coverage_path


def test_source_manifest_accepts_equal_sets(tmp_path: Path) -> None:
    """AC-FR1001-01/03: equal disk, reconstructed inventory, and coverage sets pass."""
    source, inventory, coverage = _source_fixture(tmp_path)
    report = tmp_path / "source-report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKERS / "source_manifest.py"),
            "check",
            "--source",
            str(source),
            "--inventory",
            str(inventory),
            "--coverage",
            str(coverage),
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stderr
    assert payload["counts"] == {"coverage": 1, "disk": 1, "inventory": 1}
    assert payload["verdict"] == "PASS"


def test_source_manifest_reports_each_set_difference(tmp_path: Path) -> None:
    """AC-FR1001-01/03: a coverage path outside disk/inventory blocks the manifest."""
    source, inventory, coverage = _source_fixture(tmp_path)
    coverage.write_text(
        json.dumps({"files": {"quantide/extra.py": {"summary": {}}}}), encoding="utf-8"
    )
    checker = _load_checker("source_manifest")

    report, errors = checker.evaluate(source, inventory, coverage)

    assert report["verdict"] == "FAIL"
    assert report["inventory_minus_coverage"] == ["quantide/a.py"]
    assert report["coverage_minus_inventory"] == ["quantide/extra.py"]
    assert errors


def test_recovery_shard_reconstruction_checks_hashes_and_uniqueness(
    tmp_path: Path,
) -> None:
    """AC-FR1001-02/04: canonical shard hashes and unique records reconstruct exactly."""
    checker = _load_checker("recovery_artifacts")
    records = [{"record_id": "prod-a", "path": "quantide/a.py"}]
    shard = {
        "record_count": 1,
        "records_sha256": _canonical_sha(records),
        "records": records,
    }
    shard_path = tmp_path / "shard.json"
    shard_path.write_text(json.dumps(shard), encoding="utf-8")
    shard_row = {
        "path": "shard.json",
        "record_count": 1,
        "sha256": hashlib.sha256(shard_path.read_bytes()).hexdigest(),
        "records_sha256": _canonical_sha(records),
    }
    index = {
        "shards": [shard_row],
        "shard_manifest_sha256": _canonical_sha([shard_row]),
    }
    errors: list[str] = []

    reconstruction = checker._verify_shards(
        tmp_path,
        index,
        collection_key="records",
        count_key="record_count",
        id_key="record_id",
        errors=errors,
    )

    assert errors == []
    assert reconstruction["record_count"] == 1
    assert reconstruction["unique_id_count"] == 1
    assert reconstruction["unique_path_count"] == 1


def test_recovery_shard_reconstruction_rejects_tampering(tmp_path: Path) -> None:
    """AC-FR1001-02/04: changed shard bytes and records produce blocking reasons."""
    checker = _load_checker("recovery_artifacts")
    records = [{"record_id": "prod-a", "path": "quantide/a.py"}]
    shard_path = tmp_path / "shard.json"
    shard_path.write_text(
        json.dumps({"record_count": 1, "records_sha256": "0" * 64, "records": records}),
        encoding="utf-8",
    )
    shard_row = {
        "path": "shard.json",
        "record_count": 1,
        "sha256": "0" * 64,
        "records_sha256": "0" * 64,
    }
    index = {"shards": [shard_row], "shard_manifest_sha256": _canonical_sha([shard_row])}
    errors: list[str] = []

    checker._verify_shards(
        tmp_path,
        index,
        collection_key="records",
        count_key="record_count",
        id_key="record_id",
        errors=errors,
    )

    assert any("byte SHA-256 mismatch" in error for error in errors)
    assert any("records SHA-256 mismatch" in error for error in errors)


def test_recovery_shard_reconstruction_rejects_non_object_manifest_row(
    tmp_path: Path,
) -> None:
    """AC-FR1001-02/04: malformed rows fail closed instead of raising."""
    checker = _load_checker("recovery_artifacts")
    rows = ["not-an-object"]
    errors: list[str] = []

    reconstruction = checker._verify_shards(
        tmp_path,
        {"shards": rows, "shard_manifest_sha256": _canonical_sha([])},
        collection_key="records",
        count_key="record_count",
        id_key="record_id",
        errors=errors,
    )

    assert reconstruction["record_count"] == 0
    assert "malformed shard row" in errors


def test_recovery_shard_reconstruction_rejects_parent_path(tmp_path: Path) -> None:
    """AC-FR1001-02/04: a tampered manifest cannot read outside recovery_dir."""
    checker = _load_checker("recovery_artifacts")
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    row = {
        "path": "../outside.json",
        "record_count": 0,
        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
        "records_sha256": _canonical_sha([]),
    }
    errors: list[str] = []

    checker._verify_shards(
        recovery,
        {"shards": [row], "shard_manifest_sha256": _canonical_sha([row])},
        collection_key="records",
        count_key="record_count",
        id_key="record_id",
        errors=errors,
    )

    assert errors == ["shard path escapes recovery directory: ../outside.json"]
