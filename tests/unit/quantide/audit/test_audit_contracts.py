"""Audit report and runner contract tests."""

from __future__ import annotations

import datetime as dt

from quantide.audit.models import (
    AuditCheck,
    AuditSpec,
    AuditStatus,
    FirstDifference,
    canonical_hash,
    compose_status,
)
from quantide.audit.runner import AuditRunner, fail_check
from quantide.audit.store import ReportStore


def _spec() -> AuditSpec:
    return AuditSpec(
        spec_id="factor:demo:v1",
        object_type="factor",
        object_id="demo",
        source_hash="source",
        data_hash="data",
        config_hash="config",
        interval="1d",
        timezone="Asia/Shanghai",
        availability_contract="t0 close available after t0",
        seed_set=(7, 11),
        truncation_points=("2024-01-02",),
    )


def test_spec_fingerprint_is_canonical_and_json_safe() -> None:
    first = _spec()
    second = _spec()
    assert first.fingerprint == second.fingerprint
    assert first.as_dict()["truncation_points"] == ["2024-01-02"]
    assert canonical_hash({"b": 1, "a": 2}) == canonical_hash({"a": 2, "b": 1})
    assert canonical_hash({"date": dt.date(2024, 1, 2)}) == canonical_hash({"date": "2024-01-02"})


def test_status_precedence_requires_evidence() -> None:
    assert compose_status([]) is AuditStatus.INCONCLUSIVE
    assert (
        compose_status(
            [
                AuditCheck("a", True, AuditStatus.PASS),
                AuditCheck("b", False, AuditStatus.NOT_APPLICABLE),
            ]
        )
        is AuditStatus.PASS
    )
    assert (
        compose_status([AuditCheck("a", True, AuditStatus.INCONCLUSIVE)])
        is AuditStatus.INCONCLUSIVE
    )
    assert (
        compose_status(
            [
                AuditCheck("a", True, AuditStatus.PASS),
                AuditCheck("b", True, AuditStatus.FAIL),
            ]
        )
        is AuditStatus.FAIL
    )


def test_runner_marks_exception_as_failure_and_keeps_first_difference() -> None:
    def _fail(spec):
        return fail_check(
            "determinism",
            message="past output changed",
            expected=1.0,
            actual=2.0,
            time="2024-01-02",
            asset="000001",
            column="signal",
        )

    runner = AuditRunner({"determinism": (_fail, True)})
    report = runner.run(_spec())
    assert report.status is AuditStatus.FAIL
    assert report.first_difference is not None
    assert report.first_difference.column == "signal"
    assert report.checks[0].required is True
    assert report.as_dict()["first_difference"]["asset"] == "000001"

    def _crash(spec):
        raise RuntimeError("fixture unavailable")

    crashed = AuditRunner({"crash": (_crash, True)}).run(_spec())
    assert crashed.status is AuditStatus.FAIL
    assert "fixture unavailable" in crashed.checks[0].message


def test_runner_inconclusive_for_missing_required_check() -> None:
    def _skip(spec):
        return AuditCheck("optional", False, AuditStatus.NOT_APPLICABLE)

    report = AuditRunner({"optional": (_skip, True)}).run(_spec())
    assert report.status is AuditStatus.INCONCLUSIVE


def test_report_json_contains_reproduce_and_nonfinite_is_null() -> None:
    def _pass(spec):
        return AuditCheck("ok", True, AuditStatus.PASS, details={"value": float("nan")})

    report = AuditRunner({"ok": (_pass, True)}).run(_spec())
    payload = report.as_dict()
    assert payload["status"] == "PASS"
    assert payload["checks"][0]["details"]["value"] is None
    assert payload["reproduce"]["spec"]["spec_id"] == "factor:demo:v1"
    assert "NaN" not in report.to_json()


def test_first_difference_is_json_serializable() -> None:
    difference = FirstDifference(
        time="2024-01-02",
        asset="000001",
        column="x",
        expected=dt.date(2024, 1, 2),
        actual=float("inf"),
        kind="value",
    )
    payload = difference.as_dict()
    assert payload["expected"] == "2024-01-02"
    assert payload["actual"] is None


def test_report_store_persists_and_invalidates_on_spec_change(tmp_path) -> None:
    def _pass(spec):
        return AuditCheck("ok", True, AuditStatus.PASS)

    spec = _spec()
    report = AuditRunner({"ok": (_pass, True)}).run(spec)
    store = ReportStore(tmp_path)
    path = store.save(report)
    assert path.exists()
    assert store.load(report.run_id)["status"] == "PASS"
    assert store.list_reports()[0]["run_id"] == report.run_id
    assert store.is_current(report.run_id, spec)
    changed = AuditSpec(
        spec_id=spec.spec_id,
        object_type=spec.object_type,
        object_id=spec.object_id,
        source_hash="changed",
        data_hash=spec.data_hash,
        config_hash=spec.config_hash,
        interval=spec.interval,
        timezone=spec.timezone,
        availability_contract=spec.availability_contract,
    )
    assert not store.is_current(report.run_id, changed)
