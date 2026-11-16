"""Built-in factor pipeline audit integration tests."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.audit.__main__ import main
from quantide.audit.factor import audit_factor, build_factor_spec
from quantide.audit.models import AuditStatus


def _raw() -> pl.DataFrame:
    dates = [dt.date(2024, 1, 2) + dt.timedelta(days=index) for index in range(45)]
    rows = []
    for asset in range(120):
        for index, day in enumerate(dates):
            base = 10 + asset * 0.1 + index * 0.03
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset:06d}",
                    "open": base,
                    "high": base * 1.01,
                    "low": base * 0.99,
                    "close": base * 1.002,
                    "volume": 1_000_000 + index,
                    "amount": (1_000_000 + index) * base,
                    "available_at": day,
                }
            )
    return pl.DataFrame(rows)


def test_factor_audit_passes_determinism_and_future_invariance() -> None:
    frame = _raw()
    cutoff = dt.date(2024, 2, 10)
    report = audit_factor(frame, "ma20_slope", cutoff=cutoff)
    assert report.status is AuditStatus.PASS
    assert [check.check_id for check in report.checks] == [
        "factor.schema",
        "factor.metadata",
        "factor.deterministic",
        "factor.future_invariance",
    ]
    assert all(check.status is AuditStatus.PASS for check in report.checks)
    spec = build_factor_spec(frame, "ma20_slope")
    assert spec.object_id == "ma20_slope"
    assert spec.source_hash
    assert spec.truncation_points
    assert report.as_dict()["first_difference"] is None


def test_default_audit_uses_multiple_interior_cutoffs() -> None:
    frame = _raw()
    report = audit_factor(frame, "ma20_slope")
    assert len(report.spec.truncation_points) >= 2
    assert report.status is AuditStatus.PASS


def test_duplicate_date_asset_keys_fail_schema() -> None:
    frame = _raw()
    duplicated = pl.concat([frame, frame.head(1)])
    report = audit_factor(duplicated, "bias_5", cutoff=dt.date(2024, 2, 10))
    assert report.status is AuditStatus.FAIL
    schema = report.checks[0]
    assert schema.check_id == "factor.schema"
    assert "duplicate" in schema.message
    assert schema.first_difference is not None
    assert schema.first_difference.kind == "duplicate_key"


def test_schema_rejects_unsorted_and_typed_inputs() -> None:
    frame = _raw()
    unsorted = pl.concat([frame.tail(2), frame.head(frame.height - 2)])
    report = audit_factor(unsorted, "bias_5", cutoff=dt.date(2024, 2, 10))
    assert report.status is AuditStatus.FAIL
    assert "sorted" in report.checks[0].message

    wrong_type = frame.with_columns(pl.col("date").cast(pl.Utf8))
    typed_report = audit_factor(wrong_type, "bias_5", cutoff=dt.date(2024, 2, 10))
    assert typed_report.status is AuditStatus.FAIL
    assert "date" in typed_report.checks[0].message

    missing_availability = frame.with_columns(pl.lit(None, dtype=pl.Date).alias("available_at"))
    availability_report = audit_factor(missing_availability, "bias_5", cutoff=dt.date(2024, 2, 10))
    assert availability_report.status is AuditStatus.FAIL
    assert "availability" in availability_report.checks[0].message


def test_cutoff_at_sample_end_is_inconclusive() -> None:
    frame = _raw()
    cutoff = frame["date"].max()
    report = audit_factor(frame, "bias_5", cutoff=cutoff)
    assert report.status is AuditStatus.INCONCLUSIVE
    pending = next(check for check in report.checks if check.check_id == "factor.future_invariance")
    assert "no future rows" in pending.message


def test_report_fingerprint_binds_executed_cutoffs() -> None:
    frame = _raw()
    early = audit_factor(frame, "bias_5", cutoff=dt.date(2024, 1, 21))
    late = audit_factor(frame, "bias_5", cutoff=dt.date(2024, 1, 31))
    assert early.spec.truncation_points == ("2024-01-21",)
    assert late.spec.truncation_points == ("2024-01-31",)
    assert early.spec.fingerprint != late.spec.fingerprint


def test_explicit_spec_must_match_executed_cutoffs() -> None:
    frame = _raw()
    spec = build_factor_spec(frame, "bias_5", cutoffs=(dt.date(2024, 1, 21),))
    with pytest.raises(ValueError):
        audit_factor(frame, "bias_5", spec=spec, cutoff=dt.date(2024, 1, 31))


def test_factor_without_valid_values_is_inconclusive() -> None:
    frame = _raw().filter((pl.col("date") <= dt.date(2024, 1, 4)) & (pl.col("asset") < "000003"))
    report = audit_factor(frame, "ma20_slope", cutoff=dt.date(2024, 1, 3))
    assert report.status is AuditStatus.INCONCLUSIVE
    schema = report.checks[0]
    assert schema.check_id == "factor.schema"
    assert "no valid values" in schema.message


def test_explicit_spec_binds_input_and_execution_config() -> None:
    frame = _raw()
    cutoff = dt.date(2024, 1, 21)
    spec = build_factor_spec(frame, "bias_5", cutoffs=(cutoff,))
    assert audit_factor(frame, "bias_5", spec=spec, cutoff=cutoff).status is AuditStatus.PASS

    revised = frame.with_columns((pl.col("close") * 1.01).alias("close"))
    with pytest.raises(ValueError, match="data_hash"):
        audit_factor(revised, "bias_5", spec=spec, cutoff=cutoff)
    with pytest.raises(ValueError, match="config_hash"):
        audit_factor(frame, "bias_5", spec=spec, cutoff=cutoff, modes=("extreme",))
    with pytest.raises(ValueError, match="seed_set"):
        audit_factor(frame, "bias_5", spec=spec, cutoff=cutoff, seeds=(7,))


def test_factor_audit_rejects_missing_input_without_crashing() -> None:
    frame = _raw().drop("available_at")
    report = audit_factor(frame, "ma20_slope")
    assert report.status is AuditStatus.FAIL
    assert "missing input columns" in report.checks[0].message


def test_audit_cli_writes_report_and_exit_code(tmp_path) -> None:
    frame = _raw()
    panel = tmp_path / "panel.parquet"
    output = tmp_path / "report.json"
    frame.write_parquet(panel)
    code = main(
        [
            "ma20_slope",
            "--panel",
            str(panel),
            "--cutoff",
            "2024-02-10",
            "--output",
            str(output),
        ]
    )
    assert code == 0
    assert output.exists()
    assert '"status": "PASS"' in output.read_text(encoding="utf-8")
