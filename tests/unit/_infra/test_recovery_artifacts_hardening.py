"""Hardening contract tests for the immutable recovery artifact verifier.

Covers schema/spec-id validation, exact reconstruction counts, production
source-grounded invariants, trace function dispositions/qualified refs, RW
registry structure, and exact bidirectional trace<->RW binding equality.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKERS = Path(__file__).resolve().parents[1] / "_checkers"
SPEC_DIR = REPO_ROOT / ".louke/project/specs/v0.2-004-coverage-recovery"


def _load_checker(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, CHECKERS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _grounded_record(rid: str = "prod-a", path: str = "quantide/a.py") -> dict:
    return {
        "record_id": rid,
        "path": path,
        "source_grounded_review_status": "manually-source-grounded",
    }


def _prod_index(
    records: list[dict],
    *,
    shard_count: int | None = None,
    record_count: int | None = None,
    source_grounded: int | None = None,
    **overrides: object,
) -> dict:
    rc = record_count if record_count is not None else len(records)
    sg = source_grounded if source_grounded is not None else rc
    base: dict = {
        "schema": "production-inventory-index/v2",
        "spec_id": "v0.2-004-coverage-recovery",
        "shard_count": shard_count if shard_count is not None else 1,
        "record_count": rc,
        "path_specific_contract_count": rc,
        "contract_count": rc,
        "source_grounded_contract_count": sg,
        "records": records,
        "shards": [],
        "records_sha256": _canonical_sha(records),
    }
    base.update(overrides)
    return base


def _function(
    fid: str,
    disposition: str = "aligned",
    work_item_id: str | None = None,
    target_refs: list[str] | None = None,
) -> dict:
    fn: dict = {
        "id": fid,
        "name": fid,
        "qualname": fid,
        "line": 1,
        "disposition": disposition,
        "target_refs": (
            target_refs
            if target_refs is not None
            else ["v0.2-003-coverage FR-0103 / AC-FR0103-01"]
        ),
        "production_targets": ["quantide/core/a.py"],
    }
    if disposition == "update":
        fn["work_item_id"] = work_item_id or "RW-0001"
    return fn


def _module(mid: str = "testmod-a", functions: list[dict] | None = None) -> dict:
    funcs = functions or []
    return {
        "record_id": mid,
        "path": f"tests/{mid}.py",
        "functions": funcs,
        "test_function_count": len(funcs),
    }


def _trace_index(
    modules: list[dict],
    *,
    functions: int,
    aligned: int,
    update: int,
    **overrides: object,
) -> dict:
    base: dict = {
        "schema": "test-trace-index/v1",
        "spec_id": "v0.2-004-coverage-recovery",
        "shard_count": 1,
        "module_count": len(modules),
        "total_test_function_count": functions,
        "function_trace_complete_count": functions,
        "spec_qualified_function_ref_count": functions,
        "all_tests_py_count": len(modules),
        "disposition_counts": {"aligned": aligned, "update": update},
        "quality_counts": {},
        "modules": modules,
        "shards": [],
    }
    base.update(overrides)
    return base


def _rw_item(wid: str = "RW-0001", fid: str = "tests/test_a.py::test_a", **overrides: object) -> dict:
    base: dict = {
        "work_item_id": wid,
        "status": "open",
        "function_ids": [fid],
        "test_modules": ["tests/test_a.py"],
        "production_targets": ["quantide/core/a.py"],
        "defect_category": "test-defect",
        "quality_finding": "incomplete",
        "ac_refs": ["v0.2-003-coverage FR-0103 / AC-FR0103-01"],
    }
    base.update(overrides)
    return base


def _rw_registry(items: list[dict], **overrides: object) -> dict:
    base: dict = {
        "schema": "devon-work-items/v1",
        "spec_id": "v0.2-004-coverage-recovery",
        "status": "open",
        "work_item_count": len(items),
        "bound_update_function_count": len(items),
        "binding_coverage": f"{len(items)}/{len(items)}",
        "work_items": items,
    }
    base.update(overrides)
    return base


def _prod_expected(records: list[dict], shards: int = 1) -> dict:
    return {
        "schema": "production-inventory-index/v2",
        "spec_id": "v0.2-004-coverage-recovery",
        "shard_count": shards,
        "record_count": len(records),
        "source_grounded": len(records),
    }


def _trace_expected(modules: list[dict], aligned: int, update: int) -> dict:
    functions = aligned + update
    return {
        "schema": "test-trace-index/v1",
        "spec_id": "v0.2-004-coverage-recovery",
        "shard_count": 1,
        "module_count": len(modules),
        "function_count": functions,
        "aligned": aligned,
        "update": update,
    }


def _rw_expected(items: list[dict]) -> dict:
    return {
        "schema": "devon-work-items/v1",
        "spec_id": "v0.2-004-coverage-recovery",
        "work_item_count": len(items),
        "status": "open",
    }


# ---------------------------------------------------------------------------
# Production index validation
# ---------------------------------------------------------------------------


def test_production_index_accepts_consistent_grounding() -> None:
    """AC-FR1201-07: a fully source-grounded, consistent index produces no errors."""
    checker = _load_checker("recovery_artifacts")
    records = [_grounded_record(f"prod-{i}", f"quantide/f{i}.py") for i in range(2)]
    index = _prod_index(records, shard_count=1)
    errors: list[str] = []

    checker._verify_production_index(index, errors, expected=_prod_expected(records))

    assert errors == []


def test_production_index_rejects_wrong_schema_and_spec_id() -> None:
    """AC-FR1001-02: schema/spec-id drift from the pinned contract is blocking."""
    checker = _load_checker("recovery_artifacts")
    records = [_grounded_record()]
    index = _prod_index(records, schema="production-inventory-index/v9", spec_id="other")
    errors: list[str] = []

    checker._verify_production_index(index, errors, expected=_prod_expected(records))

    assert any("schema" in e for e in errors)
    assert any("spec_id" in e for e in errors)


def test_production_index_rejects_count_mismatch() -> None:
    """AC-FR1001-02: declared counts must equal expected and actual record counts."""
    checker = _load_checker("recovery_artifacts")
    records = [_grounded_record()]
    index = _prod_index(records, record_count=2, source_grounded=2)
    errors: list[str] = []

    checker._verify_production_index(index, errors, expected=_prod_expected(records))

    assert any("record_count" in e for e in errors)


def test_production_index_rejects_ungrounded_record() -> None:
    """AC-FR1201-07: a non-source-grounded record violates the grounding invariant."""
    checker = _load_checker("recovery_artifacts")
    bad = {**_grounded_record("prod-b", "quantide/b.py"), "source_grounded_review_status": "pseudo-import"}
    records = [_grounded_record("prod-a", "quantide/a.py"), bad]
    index = _prod_index(records, record_count=2, source_grounded=2)
    errors: list[str] = []

    checker._verify_production_index(index, errors, expected=_prod_expected(records))

    assert any("source_grounded" in e for e in errors)


def test_production_index_rejects_source_grounded_count_drift() -> None:
    """AC-FR1201-07: source_grounded_contract_count must equal grounded record count."""
    checker = _load_checker("recovery_artifacts")
    records = [_grounded_record()]
    index = _prod_index(records, source_grounded=5)
    errors: list[str] = []

    checker._verify_production_index(index, errors, expected=_prod_expected(records))

    assert any("source_grounded" in e for e in errors)


def test_production_index_rejects_shard_count_mismatch() -> None:
    """AC-FR1001-02: declared shard_count must equal expected and len(shards)."""
    checker = _load_checker("recovery_artifacts")
    records = [_grounded_record()]
    index = _prod_index(records, shard_count=3)
    errors: list[str] = []

    checker._verify_production_index(index, errors, expected=_prod_expected(records))

    assert any("shard_count" in e for e in errors)


# ---------------------------------------------------------------------------
# Trace index validation
# ---------------------------------------------------------------------------


def test_trace_index_accepts_consistent_counts() -> None:
    """AC-FR1601-06: consistent module/function/disposition totals pass."""
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("f1", "aligned"), _function("f2", "update", "RW-0001")])]
    index = _trace_index(modules, functions=2, aligned=1, update=1)
    errors: list[str] = []

    checker._verify_trace_index(index, errors, expected=_trace_expected(modules, 1, 1))

    assert errors == []


def test_trace_index_rejects_wrong_schema() -> None:
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("f1")])]
    index = _trace_index(modules, functions=1, aligned=1, update=0, schema="bad")
    errors: list[str] = []

    checker._verify_trace_index(index, errors, expected=_trace_expected(modules, 1, 0))

    assert any("schema" in e for e in errors)


def test_trace_index_rejects_disposition_total_mismatch() -> None:
    """AC-FR1601-06: declared disposition totals must equal the expected counts."""
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("f1")])]
    index = _trace_index(modules, functions=1, aligned=2, update=0)
    errors: list[str] = []

    checker._verify_trace_index(index, errors, expected=_trace_expected(modules, 1, 0))

    assert any("disposition" in e for e in errors)


def test_trace_index_rejects_function_count_mismatch() -> None:
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("f1")])]
    index = _trace_index(modules, functions=5, aligned=1, update=0)
    errors: list[str] = []

    checker._verify_trace_index(index, errors, expected=_trace_expected(modules, 1, 0))

    assert any("total_test_function_count" in e for e in errors)


# ---------------------------------------------------------------------------
# Trace function validation
# ---------------------------------------------------------------------------


def test_trace_functions_accepts_valid_dispositions_and_refs() -> None:
    """AC-FR1601-06: valid dispositions, qualified refs, and update bindings pass."""
    checker = _load_checker("recovery_artifacts")
    modules = [
        _module("m1", [_function("f1", "aligned"), _function("f2", "update", "RW-0001")])
    ]
    errors: list[str] = []

    result = checker._verify_trace_functions(modules, errors)

    assert errors == []
    assert result["function_count"] == 2
    assert result["disposition_counts"] == {"aligned": 1, "update": 1}
    assert result["update_fn_to_wi"] == {"f2": "RW-0001"}


def test_trace_functions_rejects_invalid_disposition() -> None:
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("f1", disposition="needs-Sage-contract")])]
    errors: list[str] = []

    checker._verify_trace_functions(modules, errors)

    assert any("disposition" in e for e in errors)


def test_trace_update_function_requires_work_item_binding() -> None:
    """AC-FR1301-06: every update function must bind exactly one RW work item."""
    checker = _load_checker("recovery_artifacts")
    fn = _function("f1", "update")
    fn.pop("work_item_id")
    modules = [_module("m1", [fn])]
    errors: list[str] = []

    checker._verify_trace_functions(modules, errors)

    assert any("work_item_id" in e for e in errors)


def test_trace_update_function_requires_well_formed_work_item_id() -> None:
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("f1", "update", work_item_id="RW-1")])]
    errors: list[str] = []

    checker._verify_trace_functions(modules, errors)

    assert any("work_item_id" in e for e in errors)


def test_trace_function_requires_qualified_target_refs() -> None:
    """AC-FR1601-02: every function needs nonempty spec-qualified target refs."""
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("f1", target_refs=["not-a-spec-ref"])])]
    errors: list[str] = []

    checker._verify_trace_functions(modules, errors)

    assert any("target_refs" in e for e in errors)


def test_trace_function_rejects_empty_target_refs() -> None:
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("f1", target_refs=[])])]
    errors: list[str] = []

    checker._verify_trace_functions(modules, errors)

    assert any("target_refs" in e for e in errors)


def test_trace_functions_rejects_duplicate_function_id() -> None:
    checker = _load_checker("recovery_artifacts")
    modules = [_module("m1", [_function("dup"), _function("dup")])]
    errors: list[str] = []

    checker._verify_trace_functions(modules, errors)

    assert any("duplicate" in e for e in errors)


# ---------------------------------------------------------------------------
# RW registry validation
# ---------------------------------------------------------------------------


def test_rw_registry_accepts_valid_open_bindings() -> None:
    """AC-FR1301-06: a valid open registry with one-to-one bindings passes."""
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-0001", "f1"), _rw_item("RW-0002", "f2")]
    registry = _rw_registry(items)
    errors: list[str] = []

    result = checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert errors == []
    assert result["wi_to_fn"] == {"RW-0001": "f1", "RW-0002": "f2"}
    assert result["fn_to_wi"] == {"f1": "RW-0001", "f2": "RW-0002"}


def test_rw_registry_rejects_wrong_schema_and_status() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item()]
    registry = _rw_registry(items, schema="bad", status="closed")
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert any("schema" in e for e in errors)
    assert any("status" in e for e in errors)


def test_rw_registry_rejects_bad_id_pattern() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-1", "f1")]
    registry = _rw_registry(items)
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert any("work_item_id" in e for e in errors)


def test_rw_registry_rejects_duplicate_work_item_id() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-0001", "f1"), _rw_item("RW-0001", "f2")]
    registry = _rw_registry(items, work_item_count=1)
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items[:1]))

    assert any("duplicate" in e for e in errors)


def test_rw_registry_rejects_duplicate_function_id() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-0001", "dup"), _rw_item("RW-0002", "dup")]
    registry = _rw_registry(items)
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert any("duplicate" in e for e in errors)


def test_rw_registry_requires_exactly_one_function_binding() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-0001", "f1", function_ids=["f1", "f2"])]
    registry = _rw_registry(items)
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert any("function_ids" in e for e in errors)


def test_rw_registry_requires_nonempty_test_modules() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-0001", "f1", test_modules=[])]
    registry = _rw_registry(items)
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert any("test_modules" in e for e in errors)


def test_rw_registry_requires_nonempty_production_targets() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-0001", "f1", production_targets=[])]
    registry = _rw_registry(items)
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert any("production_targets" in e for e in errors)


def test_rw_registry_requires_qualified_ac_refs() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-0001", "f1", ac_refs=["bare-ref"])]
    registry = _rw_registry(items)
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert any("ac_refs" in e for e in errors)


def test_rw_registry_rejects_work_item_count_mismatch() -> None:
    checker = _load_checker("recovery_artifacts")
    items = [_rw_item("RW-0001", "f1")]
    registry = _rw_registry(items, work_item_count=5)
    errors: list[str] = []

    checker._verify_rw_registry(registry, errors, expected=_rw_expected(items))

    assert any("work_item_count" in e for e in errors)


# ---------------------------------------------------------------------------
# Bidirectional trace<->RW binding equality
# ---------------------------------------------------------------------------


def test_bidirectional_binding_accepts_exact_match() -> None:
    """AC-FR1301-06: reciprocal one-to-one binding with zero diff passes."""
    checker = _load_checker("recovery_artifacts")
    trace_map = {"f1": "RW-0001", "f2": "RW-0002"}
    rw_wi_to_fn = {"RW-0001": "f1", "RW-0002": "f2"}
    rw_fn_to_wi = {"f1": "RW-0001", "f2": "RW-0002"}
    errors: list[str] = []

    checker._verify_bidirectional(trace_map, rw_wi_to_fn, rw_fn_to_wi, errors)

    assert errors == []


def test_bidirectional_binding_rejects_missing_trace_function() -> None:
    """AC-FR1301-06: an RW function absent from trace is an extra binding."""
    checker = _load_checker("recovery_artifacts")
    trace_map = {"f1": "RW-0001"}
    rw_wi_to_fn = {"RW-0001": "f1", "RW-0002": "f2"}
    rw_fn_to_wi = {"f1": "RW-0001", "f2": "RW-0002"}
    errors: list[str] = []

    checker._verify_bidirectional(trace_map, rw_wi_to_fn, rw_fn_to_wi, errors)

    assert any("missing" in e or "extra" in e for e in errors)


def test_bidirectional_binding_rejects_extra_trace_function() -> None:
    """AC-FR1301-06: a trace update function absent from RW is a missing binding."""
    checker = _load_checker("recovery_artifacts")
    trace_map = {"f1": "RW-0001", "f2": "RW-0002"}
    rw_wi_to_fn = {"RW-0001": "f1"}
    rw_fn_to_wi = {"f1": "RW-0001"}
    errors: list[str] = []

    checker._verify_bidirectional(trace_map, rw_wi_to_fn, rw_fn_to_wi, errors)

    assert any("missing" in e or "extra" in e for e in errors)


def test_bidirectional_binding_rejects_mismatched_reciprocal_mapping() -> None:
    """AC-FR1301-06: a function bound to different RW ids in trace vs RW is blocking."""
    checker = _load_checker("recovery_artifacts")
    trace_map = {"f1": "RW-0001"}
    rw_wi_to_fn = {"RW-0002": "f1"}
    rw_fn_to_wi = {"f1": "RW-0002"}
    errors: list[str] = []

    checker._verify_bidirectional(trace_map, rw_wi_to_fn, rw_fn_to_wi, errors)

    assert any("mismatch" in e for e in errors)


# ---------------------------------------------------------------------------
# Full verify() integration against the real immutable repo
# ---------------------------------------------------------------------------


def _byte_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_verify_real_repo_remains_fail_on_stale_hashes_only() -> None:
    """AC-FR1001-02: hardening keeps the repo FAIL on the 10 stale shard hashes.

    No new schema/count/grounding/disposition/binding reason is introduced on the
    immutable baseline; the only failures are the pre-existing stale record hashes.
    """
    checker = _load_checker("recovery_artifacts")
    report, errors = checker.verify(SPEC_DIR)

    assert report["verdict"] == "FAIL"
    assert len(errors) == 10
    forbidden = (
        "schema",
        "spec_id",
        "shard_count",
        "record_count",
        "source_grounded",
        "disposition",
        "total_test_function_count",
        "work_item_count",
        "function_ids",
        "target_refs",
        "ac_refs",
        "test_modules",
        "production_targets",
        "bidirectional",
    )
    for reason in errors:
        assert "records SHA-256 mismatch" in reason, reason
        assert not any(token in reason for token in forbidden), reason


def test_verify_real_repo_report_is_json_serializable_with_required_fields() -> None:
    checker = _load_checker("recovery_artifacts")
    report, _ = checker.verify(SPEC_DIR)

    serialized = json.dumps(report, sort_keys=True)
    reloaded = json.loads(serialized)
    assert reloaded["verdict"] == report["verdict"]
    for field in ("schema", "spec_id", "checked_at", "artifacts", "reconstructions", "verdict", "reasons"):
        assert field in report
    assert report["schema"] == "recovery-hashes/v1"
    assert report["spec_id"] == "v0.2-004-coverage-recovery"
    assert isinstance(report["reasons"], list)
    assert isinstance(report["artifacts"], list)
    assert isinstance(report["reconstructions"], dict)


def test_verify_report_reasons_are_deterministic() -> None:
    checker = _load_checker("recovery_artifacts")
    report_a, _ = checker.verify(SPEC_DIR)
    report_b, _ = checker.verify(SPEC_DIR)

    assert report_a["reasons"] == report_b["reasons"]
    assert report_a["reasons"] == sorted(report_a["reasons"])


def test_verify_missing_pinned_files_fail_closed_without_traceback(tmp_path: Path) -> None:
    """AC-FR1901-02/§13: missing inputs produce a FAIL report, not a traceback."""
    checker = _load_checker("recovery_artifacts")
    empty_dir = tmp_path / "empty-spec"
    empty_dir.mkdir()

    report, errors = checker.verify(empty_dir)

    assert report["verdict"] == "FAIL"
    assert errors
    assert report["reasons"] == errors
    for artifact in report["artifacts"]:
        assert artifact["status"] == "fail"


def test_verify_malformed_index_fail_closed_without_traceback(tmp_path: Path) -> None:
    """AC-FR1901-02/§13: malformed JSON fails closed with actionable reasons."""
    checker = _load_checker("recovery_artifacts")
    spec_dir = tmp_path / "malformed-spec"
    recovery = spec_dir / "recovery"
    recovery.mkdir(parents=True)
    (recovery / "production-file-inventory.json").write_text("{not json", encoding="utf-8")
    (recovery / "test-trace-data.json").write_text("[]", encoding="utf-8")
    (recovery / "devon-work-items.json").write_text("null", encoding="utf-8")

    report, errors = checker.verify(spec_dir)

    assert report["verdict"] == "FAIL"
    assert errors
    serialized = json.dumps(report, sort_keys=True)
    assert "FAIL" in serialized


def test_verify_cli_writes_report_and_nonzero_exit_on_failure(tmp_path: Path) -> None:
    report_path = tmp_path / "recovery-hashes.json"
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKERS / "recovery_artifacts.py"),
            "verify",
            "--spec-dir",
            str(SPEC_DIR),
            "--report",
            str(report_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["verdict"] == "FAIL"
    assert payload["reasons"]


# ---------------------------------------------------------------------------
# Positive synthetic full verify() with a clean fixture
# ---------------------------------------------------------------------------


def _write_shard(
    spec_dir: Path, shard_rel: str, payload: dict, count_key: str, collection_key: str
) -> dict:
    shard_path = spec_dir / "recovery" / shard_rel
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    shard_path.write_text(json.dumps(payload), encoding="utf-8")
    collection = payload[collection_key]
    return {
        "path": shard_rel,
        "family": payload.get("family", "root"),
        "part": payload.get("part", 1),
        count_key: len(collection),
        "function_count": len(collection[0].get("functions", [])) if collection_key == "modules" and collection else 0,
        "sha256": _byte_sha(shard_path),
        "records_sha256": _canonical_sha(collection),
    }


def test_verify_clean_synthetic_fixture_passes(tmp_path: Path) -> None:
    """AC-FR1001-02/AC-FR1601-08: a fully consistent synthetic spec-dir verifies PASS."""
    checker = _load_checker("recovery_artifacts")
    spec_dir = tmp_path / "clean-spec"

    prod_record = _grounded_record("prod-a", "quantide/a.py")
    prod_shard = {
        "schema": "production-contract-shard/v1",
        "spec_id": "v0.2-004-coverage-recovery",
        "family": "root",
        "part": 1,
        "record_count": 1,
        "records_sha256": _canonical_sha([prod_record]),
        "records": [prod_record],
    }
    prod_row = _write_shard(spec_dir, "production-contracts/root.json", prod_shard, "record_count", "records")
    prod_index = {
        "schema": "production-inventory-index/v2",
        "spec_id": "v0.2-004-coverage-recovery",
        "shard_count": 1,
        "record_count": 1,
        "path_specific_contract_count": 1,
        "contract_count": 1,
        "source_grounded_contract_count": 1,
        "disk_file_count": 1,
        "coverage_json_file_count": 1,
        "records": [prod_record],
        "records_sha256": _canonical_sha([prod_record]),
        "shards": [prod_row],
        "shard_manifest_sha256": _canonical_sha([prod_row]),
    }

    aligned_fn = _function("f1", "aligned")
    update_fn = _function("f2", "update", "RW-0001")
    trace_module = _module("m1", [aligned_fn, update_fn])
    trace_shard = {
        "schema": "test-trace-shard/v1",
        "spec_id": "v0.2-004-coverage-recovery",
        "family": "unit",
        "part": 1,
        "module_count": 1,
        "function_count": 2,
        "records_sha256": _canonical_sha([trace_module]),
        "modules": [trace_module],
    }
    trace_row = _write_shard(spec_dir, "test-trace/root.json", trace_shard, "module_count", "modules")
    trace_index = {
        "schema": "test-trace-index/v1",
        "spec_id": "v0.2-004-coverage-recovery",
        "shard_count": 1,
        "module_count": 1,
        "total_test_function_count": 2,
        "function_trace_complete_count": 2,
        "spec_qualified_function_ref_count": 2,
        "all_tests_py_count": 1,
        "disposition_counts": {"aligned": 1, "update": 1},
        "quality_counts": {"aligned": 1, "incomplete": 1},
        "modules": [trace_module],
        "shards": [trace_row],
        "shard_manifest_sha256": _canonical_sha([trace_row]),
    }

    rw_item = _rw_item("RW-0001", "f2")
    rw_registry = _rw_registry([rw_item])

    recovery = spec_dir / "recovery"
    (recovery / "production-file-inventory.json").write_text(json.dumps(prod_index), encoding="utf-8")
    (recovery / "test-trace-data.json").write_text(json.dumps(trace_index), encoding="utf-8")
    (recovery / "devon-work-items.json").write_text(json.dumps(rw_registry), encoding="utf-8")

    checker.PINS = {
        "recovery/production-file-inventory.json": _byte_sha(recovery / "production-file-inventory.json"),
        "recovery/test-trace-data.json": _byte_sha(recovery / "test-trace-data.json"),
        "recovery/devon-work-items.json": _byte_sha(recovery / "devon-work-items.json"),
    }
    checker.PRODUCTION_EXPECTED = _prod_expected([prod_record])
    checker.TRACE_EXPECTED = _trace_expected([trace_module], 1, 1)
    checker.RW_EXPECTED = _rw_expected([rw_item])

    report, errors = checker.verify(spec_dir)

    assert errors == [], errors
    assert report["verdict"] == "PASS"
    assert report["reconstructions"]["production"]["shard_count"] == 1
    assert report["reconstructions"]["production"]["record_count"] == 1
    assert report["reconstructions"]["test_trace"]["function_count"] == 2
    assert report["reconstructions"]["rw"]["work_item_count"] == 1
