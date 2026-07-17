"""Verify immutable v0.2-004 recovery indexes, shards, and RW bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SPEC_ID = "v0.2-004-coverage-recovery"
PINS = {
    "recovery/production-file-inventory.json": "8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe",
    "recovery/test-trace-data.json": "3d7ebc07cc8d014aab8981c025a142f1112c7d7cfb05390254de02c19da38fd0",
    "recovery/devon-work-items.json": "bac42a69bcd6359afe16fbcdc8ae710314ad00ced431dff9c1625186cb2bd088",
}
PRODUCTION_EXPECTED = {
    "schema": "production-inventory-index/v2",
    "spec_id": SPEC_ID,
    "shard_count": 13,
    "record_count": 169,
    "source_grounded": 169,
}
TRACE_EXPECTED = {
    "schema": "test-trace-index/v1",
    "spec_id": SPEC_ID,
    "shard_count": 11,
    "module_count": 240,
    "function_count": 1651,
    "aligned": 1455,
    "update": 196,
}
RW_EXPECTED = {
    "schema": "devon-work-items/v1",
    "spec_id": SPEC_ID,
    "work_item_count": 196,
    "status": "open",
}

_RW_ID = re.compile(r"^RW-[0-9]{4}$")
_QUALIFIED_REF = re.compile(
    r"^v0\.2-[0-9]{3}(?:-[a-z0-9-]+)? (?:FR|NFR)-[A-Z0-9-]+ / "
    r"AC-[A-Z0-9-]+(?: \([^\r\n]*\))?$"
)


def _qualified_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(_QUALIFIED_REF.fullmatch(value))


def _nonempty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and bool(item) for item in value
    )


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _byte_sha(path: Path) -> str:
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


def _verify_shards(
    recovery_dir: Path,
    index: dict[str, Any],
    *,
    collection_key: str,
    count_key: str,
    id_key: str,
    errors: list[str],
) -> dict[str, Any]:
    shard_rows = index.get("shards")
    if not isinstance(shard_rows, list):
        errors.append("index shards must be a list")
        return {}
    sortable_rows = [row for row in shard_rows if isinstance(row, dict)]
    if len(sortable_rows) != len(shard_rows):
        errors.append("malformed shard row")
    if _canonical_sha(sorted(sortable_rows, key=lambda row: row.get("path", ""))) != index.get(
        "shard_manifest_sha256"
    ):
        errors.append("shard manifest SHA-256 mismatch")

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    recovery_root = recovery_dir.resolve()
    for shard_row in shard_rows:
        if not isinstance(shard_row, dict) or not isinstance(shard_row.get("path"), str):
            if isinstance(shard_row, dict):
                errors.append("malformed shard row")
            continue
        shard_path = (recovery_dir / shard_row["path"]).resolve()
        if not shard_path.is_relative_to(recovery_root):
            errors.append(f"shard path escapes recovery directory: {shard_row['path']}")
            continue
        try:
            actual_sha = _byte_sha(shard_path)
        except OSError as exc:
            errors.append(f"cannot read shard {shard_row['path']}: {exc}")
            continue
        if actual_sha != shard_row.get("sha256"):
            errors.append(f"shard byte SHA-256 mismatch: {shard_row['path']}")
        shard = _load(shard_path, "shard", errors)
        shard_records = shard.get(collection_key)
        if not isinstance(shard_records, list):
            errors.append(f"{shard_row['path']} has no {collection_key} list")
            continue
        if len(shard_records) != shard_row.get(count_key) or len(shard_records) != shard.get(
            count_key
        ):
            errors.append(f"{shard_row['path']} {count_key} mismatch")
        if _canonical_sha(shard_records) != shard_row.get("records_sha256") or _canonical_sha(
            shard_records
        ) != shard.get("records_sha256"):
            errors.append(f"{shard_row['path']} records SHA-256 mismatch")
        for record in shard_records:
            if not isinstance(record, dict):
                errors.append(f"{shard_row['path']} has a non-object record")
                continue
            record_id = record.get(id_key)
            path = record.get("path")
            if not isinstance(record_id, str) or not record_id or record_id in seen_ids:
                errors.append(f"duplicate or missing {id_key} in {shard_row['path']}")
            else:
                seen_ids.add(record_id)
            if not isinstance(path, str) or not path or path in seen_paths:
                errors.append(f"duplicate or missing path in {shard_row['path']}")
            else:
                seen_paths.add(path)
            records.append(record)

    return {
        "shard_count": len(shard_rows),
        "record_count": len(records),
        "unique_id_count": len(seen_ids),
        "unique_path_count": len(seen_paths),
        "records": records,
    }


def _verify_production_index(
    index: dict[str, Any], errors: list[str], *, expected: dict[str, Any]
) -> dict[str, Any]:
    if index.get("schema") != expected["schema"]:
        errors.append("production index schema mismatch")
    if index.get("spec_id") != expected["spec_id"]:
        errors.append("production index spec_id mismatch")

    records = index.get("records")
    if not isinstance(records, list):
        errors.append("production index records must be a list")
        records = []
    actual_grounded = sum(
        isinstance(record, dict)
        and record.get("source_grounded_review_status") == "manually-source-grounded"
        for record in records
    )
    declared_record_count = index.get("record_count")
    if declared_record_count != len(records) or declared_record_count != expected["record_count"]:
        errors.append("production index record_count mismatch")
    if index.get("shard_count") != expected["shard_count"]:
        errors.append("production index shard_count mismatch")
    if index.get("path_specific_contract_count") != len(records):
        errors.append("production index path_specific_contract_count mismatch")
    if index.get("contract_count") != len(records):
        errors.append("production index contract_count mismatch")
    if (
        index.get("source_grounded_contract_count") != actual_grounded
        or actual_grounded != expected["source_grounded"]
    ):
        errors.append("production index source_grounded contract count mismatch")
    return {"record_count": len(records), "source_grounded_count": actual_grounded}


def _verify_trace_index(
    index: dict[str, Any], errors: list[str], *, expected: dict[str, Any]
) -> dict[str, Any]:
    if index.get("schema") != expected["schema"]:
        errors.append("test trace index schema mismatch")
    if index.get("spec_id") != expected["spec_id"]:
        errors.append("test trace index spec_id mismatch")
    if "shard_count" in index and index.get("shard_count") != expected["shard_count"]:
        errors.append("test trace index shard_count mismatch")

    modules = index.get("modules")
    if not isinstance(modules, list):
        errors.append("test trace index modules must be a list")
        modules = []
    function_count = sum(
        len(module.get("functions", []))
        for module in modules
        if isinstance(module, dict) and isinstance(module.get("functions"), list)
    )
    if index.get("module_count") != len(modules) or len(modules) != expected["module_count"]:
        errors.append("test trace index module_count mismatch")
    if (
        index.get("total_test_function_count") != function_count
        or function_count != expected["function_count"]
    ):
        errors.append("test trace index total_test_function_count mismatch")
    if index.get("function_trace_complete_count") != function_count:
        errors.append("test trace index function_trace_complete_count mismatch")
    if index.get("spec_qualified_function_ref_count") != function_count:
        errors.append("test trace index spec_qualified_function_ref_count mismatch")

    dispositions = index.get("disposition_counts")
    expected_dispositions = {
        "aligned": expected["aligned"],
        "update": expected["update"],
    }
    if dispositions != expected_dispositions or sum(expected_dispositions.values()) != function_count:
        errors.append("test trace index disposition_counts mismatch")
    return {"module_count": len(modules), "function_count": function_count}


def _verify_trace_functions(
    modules: list[dict[str, Any]], errors: list[str]
) -> dict[str, Any]:
    seen_ids: set[str] = set()
    disposition_counts = {"aligned": 0, "update": 0}
    update_fn_to_wi: dict[str, str] = {}
    for module in modules:
        if not isinstance(module, dict):
            errors.append("test trace module must be an object")
            continue
        functions = module.get("functions")
        if not isinstance(functions, list):
            errors.append(f"test trace module {module.get('path')!r} functions must be a list")
            continue
        if module.get("test_function_count") != len(functions):
            errors.append(f"test trace module {module.get('path')!r} test_function_count mismatch")
        for function in functions:
            if not isinstance(function, dict):
                errors.append("test trace function must be an object")
                continue
            function_id = function.get("id")
            if not isinstance(function_id, str) or not function_id or function_id in seen_ids:
                errors.append(f"duplicate or missing test trace function id {function_id!r}")
                continue
            seen_ids.add(function_id)
            disposition = function.get("disposition")
            if disposition not in disposition_counts:
                errors.append(f"invalid disposition for test trace function {function_id}")
            else:
                disposition_counts[disposition] += 1
            target_refs = function.get("target_refs")
            if not _nonempty_strings(target_refs) or not all(
                _qualified_ref(ref) for ref in target_refs
            ):
                errors.append(f"invalid target_refs for test trace function {function_id}")
            if disposition == "update":
                work_item_id = function.get("work_item_id")
                if not isinstance(work_item_id, str) or not _RW_ID.fullmatch(work_item_id):
                    errors.append(f"invalid work_item_id for test trace function {function_id}")
                elif work_item_id in update_fn_to_wi.values():
                    errors.append(f"duplicate work_item_id binding {work_item_id}")
                else:
                    update_fn_to_wi[function_id] = work_item_id
    return {
        "function_count": len(seen_ids),
        "disposition_counts": disposition_counts,
        "update_fn_to_wi": update_fn_to_wi,
    }


def _verify_rw_registry(
    registry: dict[str, Any], errors: list[str], *, expected: dict[str, Any]
) -> dict[str, Any]:
    if registry.get("schema") != expected["schema"]:
        errors.append("RW registry schema mismatch")
    if registry.get("spec_id") != expected["spec_id"]:
        errors.append("RW registry spec_id mismatch")
    if registry.get("status") != expected["status"]:
        errors.append("RW registry status mismatch")
    work_items = registry.get("work_items")
    if not isinstance(work_items, list):
        errors.append("RW registry work_items must be a list")
        return {}
    work_ids: set[str] = set()
    function_ids: set[str] = set()
    wi_to_fn: dict[str, str] = {}
    fn_to_wi: dict[str, str] = {}
    open_count = 0
    for item in work_items:
        if not isinstance(item, dict):
            errors.append("RW work item must be an object")
            continue
        work_id = item.get("work_item_id")
        functions = item.get("function_ids")
        valid_work_id = isinstance(work_id, str) and bool(_RW_ID.fullmatch(work_id))
        if not valid_work_id or work_id in work_ids:
            errors.append(f"duplicate, missing, or malformed work_item_id {work_id!r}")
        else:
            work_ids.add(work_id)
        if not isinstance(functions, list) or len(functions) != 1 or not isinstance(functions[0], str):
            errors.append(f"{work_id!r} function_ids must bind exactly one function")
        elif functions[0] in function_ids:
            errors.append(f"duplicate RW function binding {functions[0]}")
        else:
            function_ids.add(functions[0])
            if valid_work_id and work_id not in wi_to_fn:
                wi_to_fn[work_id] = functions[0]
                fn_to_wi[functions[0]] = work_id
        if item.get("status") != "open":
            errors.append(f"{work_id!r} status must be open")
        if not _nonempty_strings(item.get("test_modules")):
            errors.append(f"{work_id!r} test_modules must be nonempty")
        if not _nonempty_strings(item.get("production_targets")):
            errors.append(f"{work_id!r} production_targets must be nonempty")
        ac_refs = item.get("ac_refs")
        if not _nonempty_strings(ac_refs) or not all(_qualified_ref(ref) for ref in ac_refs):
            errors.append(f"{work_id!r} ac_refs must be spec-qualified")
        open_count += item.get("status") == "open"
    declared_count = registry.get("work_item_count")
    if declared_count != len(work_items) or declared_count != len(work_ids):
        errors.append(f"RW work_item_count {declared_count!r} does not match unique items")
    if len(work_items) != expected["work_item_count"]:
        errors.append("RW work_item_count does not match locked expectation")
    if registry.get("bound_update_function_count") != len(function_ids):
        errors.append("RW bound_update_function_count mismatch")
    if registry.get("binding_coverage") != f"{len(function_ids)}/{len(work_items)}":
        errors.append("RW binding_coverage mismatch")
    return {
        "work_item_count": len(work_items),
        "unique_work_item_count": len(work_ids),
        "unique_function_count": len(function_ids),
        "open_count": open_count,
        "wi_to_fn": wi_to_fn,
        "fn_to_wi": fn_to_wi,
    }


def _verify_bidirectional(
    trace_fn_to_wi: dict[str, str],
    rw_wi_to_fn: dict[str, str],
    rw_fn_to_wi: dict[str, str],
    errors: list[str],
) -> None:
    trace_functions = set(trace_fn_to_wi)
    rw_functions = set(rw_fn_to_wi)
    missing_from_rw = sorted(trace_functions - rw_functions)
    extra_in_rw = sorted(rw_functions - trace_functions)
    if missing_from_rw:
        errors.append(f"bidirectional RW bindings missing functions: {missing_from_rw}")
    if extra_in_rw:
        errors.append(f"bidirectional RW bindings have extra functions: {extra_in_rw}")
    for function_id in sorted(trace_functions & rw_functions):
        if trace_fn_to_wi[function_id] != rw_fn_to_wi[function_id]:
            errors.append(f"bidirectional RW binding mismatch for {function_id}")
    for work_item_id, function_id in sorted(rw_wi_to_fn.items()):
        if trace_fn_to_wi.get(function_id) != work_item_id:
            errors.append(f"bidirectional trace binding mismatch for {work_item_id}")


def verify(spec_dir: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    artifacts: list[dict[str, str]] = []
    loaded: dict[str, dict[str, Any]] = {}
    for relative, expected in PINS.items():
        path = spec_dir / relative
        try:
            actual = _byte_sha(path)
        except OSError as exc:
            actual = ""
            errors.append(f"cannot read pinned artifact {relative}: {exc}")
        status = "pass" if actual == expected else "fail"
        if status == "fail":
            errors.append(f"pinned artifact SHA-256 mismatch: {relative}")
        artifacts.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "status": status,
            }
        )
        loaded[relative] = _load(path, relative, errors)

    recovery_dir = spec_dir / "recovery"
    production = _verify_shards(
        recovery_dir,
        loaded["recovery/production-file-inventory.json"],
        collection_key="records",
        count_key="record_count",
        id_key="record_id",
        errors=errors,
    )
    inventory = loaded["recovery/production-file-inventory.json"]
    production_index = _verify_production_index(
        inventory, errors, expected=PRODUCTION_EXPECTED
    )
    index_records = inventory.get("records")
    if not isinstance(index_records, list) or _canonical_sha(index_records) != inventory.get(
        "records_sha256"
    ):
        errors.append("production index records SHA-256 mismatch")
    if production.get("record_count") != inventory.get("record_count"):
        errors.append("production reconstructed record count mismatch")
    if isinstance(index_records, list):
        shard_paths = {row.get("path") for row in production.get("records", [])}
        index_paths = {row.get("path") for row in index_records if isinstance(row, dict)}
        if shard_paths != index_paths:
            errors.append("production index/shard path sets differ")
    if production.get("shard_count") != PRODUCTION_EXPECTED["shard_count"]:
        errors.append("production reconstructed shard_count mismatch")
    production.update(production_index)
    production.pop("records", None)

    trace = _verify_shards(
        recovery_dir,
        loaded["recovery/test-trace-data.json"],
        collection_key="modules",
        count_key="module_count",
        id_key="path",
        errors=errors,
    )
    trace_index = loaded["recovery/test-trace-data.json"]
    trace_modules = trace.get("records", [])
    trace_validation_input = dict(trace_index)
    trace_validation_input["modules"] = trace_modules
    trace_index_result = _verify_trace_index(
        trace_validation_input, errors, expected=TRACE_EXPECTED
    )
    trace_functions = _verify_trace_functions(trace_modules, errors)
    function_count = trace_functions["function_count"]
    trace.update(trace_index_result)
    trace["disposition_counts"] = trace_functions["disposition_counts"]
    if trace.get("record_count") != trace_index.get("module_count"):
        errors.append("test trace reconstructed module count mismatch")
    if function_count != trace_index.get("total_test_function_count"):
        errors.append("test trace reconstructed function count mismatch")
    if trace.get("shard_count") != TRACE_EXPECTED["shard_count"]:
        errors.append("test trace reconstructed shard_count mismatch")
    trace.pop("records", None)

    rw = _verify_rw_registry(
        loaded["recovery/devon-work-items.json"], errors, expected=RW_EXPECTED
    )
    _verify_bidirectional(
        trace_functions["update_fn_to_wi"],
        rw.get("wi_to_fn", {}),
        rw.get("fn_to_wi", {}),
        errors,
    )
    rw.pop("wi_to_fn", None)
    rw.pop("fn_to_wi", None)
    errors.sort()
    report = {
        "schema": "recovery-hashes/v1",
        "spec_id": SPEC_ID,
        "checked_at": datetime.now(UTC).isoformat(),
        "artifacts": artifacts,
        "reconstructions": {"production": production, "test_trace": trace, "rw": rw},
        "verdict": "PASS" if not errors else "FAIL",
        "reasons": errors,
    }
    return report, errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--spec-dir", required=True, type=Path)
    verify_parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report, errors = verify(args.spec_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
