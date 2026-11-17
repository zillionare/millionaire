"""Cross-sectional factor redundancy diagnostics."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.factors.orthogonality import orthogonality_summary


def _panel() -> pl.DataFrame:
    rows = []
    start = dt.date(2025, 1, 2)
    for day in range(12):
        for asset in range(8):
            value = float((asset * 3 + day * 5) % 11)
            rows.append(
                {
                    "date": start + dt.timedelta(days=day),
                    "asset": f"{asset:06d}",
                    "base": value,
                    "copy": value * 2.0 + 1.0,
                    "independent": float((asset * 7 + day * 2) % 13),
                }
            )
    return pl.DataFrame(rows)


def test_high_collinearity_and_top_peer() -> None:
    summary = orthogonality_summary(
        "base",
        _panel(),
        peers=["copy", "independent"],
    )

    assert summary.high_collinearity is True
    assert summary.status == "HIGH_COLLINEARITY"
    assert summary.max_abs_rank_corr == pytest.approx(1.0)
    assert summary.nearest_peer_id == "copy"
    assert summary.top_peers[0].n_common_days == 12


def test_missing_peer_does_not_pollute_other_correlations() -> None:
    panel = _panel().with_columns(pl.lit(None, dtype=pl.Float64).alias("empty"))

    summary = orthogonality_summary(
        "base",
        panel,
        peers=["empty", "independent"],
    )

    assert summary.nearest_peer_id == "independent"
    assert summary.max_abs_rank_corr is not None
    assert summary.max_abs_rank_corr < 0.85


def test_unknown_factor_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing factor column"):
        orthogonality_summary("missing", _panel())
