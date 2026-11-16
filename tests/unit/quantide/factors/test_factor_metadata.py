from dataclasses import replace

import pytest

from quantide.factors.alpha import FEATURE_COLS
from quantide.factors.metadata import (
    FACTOR_METADATA,
    TrackingDefaults,
    factor_definition,
    list_factor_definitions,
    normalized_tracking_defaults,
    validate_factor_metadata,
)


def test_catalog_coverage_and_fields() -> None:
    validate_factor_metadata()
    definitions = list_factor_definitions()
    assert list(FACTOR_METADATA) == FEATURE_COLS
    assert [item.factor_id for item in definitions] == FEATURE_COLS
    assert len({item.display_name for item in definitions}) == len(FEATURE_COLS)
    for item in definitions:
        assert any("\u4e00" <= char <= "\u9fff" for char in item.display_name)
        assert item.direction in {"positive", "negative", "nonlinear"}
        assert item.parameters and all(item.parameters)
        assert all(
            (
                item.group,
                item.principle,
                item.formula,
                item.example,
                item.data_requirements,
                item.caveats,
            )
        )


def test_tracking_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    factor_id = FEATURE_COLS[0]
    fallback = normalized_tracking_defaults(factor_id)
    assert (
        fallback.lookback,
        fallback.primary_holding_days,
        fallback.comparison_holding_days,
        fallback.price_field,
        fallback.defaults_version,
        fallback.source,
    ) == ("3y", 5, (1, 3, 5), "open", "1", "global")
    custom = TrackingDefaults("1y", 10, (2, 10), "close", "2")
    monkeypatch.setitem(
        FACTOR_METADATA,
        factor_id,
        replace(factor_definition(factor_id), recommended_tracking=custom),
    )
    result = normalized_tracking_defaults(factor_id)
    assert (
        result.lookback,
        result.primary_holding_days,
        result.comparison_holding_days,
        result.price_field,
        result.defaults_version,
        result.source,
    ) == ("1y", 10, (2, 10), "close", "2", "factor")


def test_validation_reports_missing_factor_and_fields() -> None:
    entries = dict(FACTOR_METADATA)
    missing = FEATURE_COLS[0]
    del entries[missing]
    other = FEATURE_COLS[1]
    entries[other] = replace(entries[other], formula="", parameters=())
    with pytest.raises(ValueError) as exc:
        validate_factor_metadata(entries)
    assert missing in str(exc.value)
    assert "missing formula" in str(exc.value)
    assert "missing parameters" in str(exc.value)
