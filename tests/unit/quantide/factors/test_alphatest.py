"""单因子检验模块（quantide.factors.alphatest）单元测试。"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import polars as pl
import pytest

from quantide.factors.alphatest import (
    MIN_CROSS_SECTION,
    RankIcSummary,
    adjacent_trading_day_expr,
    daily_rank_ic,
    decile_profile,
    ensure_trading_index,
    format_report,
    forward_return_expr,
    prepare_forward_returns,
    study_single_factor,
    summarize,
    yearly_rank_ic,
)


def test_tied_spearman_matches_independent_analytic_result():
    from quantide.factors.alphatest import _spearman

    x = np.repeat([0.0, 1.0], 50)
    y = np.arange(100, dtype=float)
    # Average ranks are 24.5 and 74.5; corr = 25 / sqrt((100**2 - 1) / 12).
    expected = 25 / math.sqrt(9999 / 12)
    assert _spearman(x, y) == pytest.approx(expected)
    assert math.isnan(_spearman(np.ones(100), y))
    assert math.isnan(_spearman(y, np.ones(100)))


def test_batch_factors_keep_independent_missing_value_masks():
    from quantide.factors.alphatest import study_factors

    panel = _panel(n_days=10, n_assets=120).with_columns(pl.lit(None).cast(pl.Float64).alias("bad"))
    reference = study_single_factor(panel, "f", 1)
    good, bad = study_factors(panel, ["f", "bad"], 1)
    assert good.rank_ic.mean == pytest.approx(reference.rank_ic.mean)
    assert good.rank_ic.n_days == reference.rank_ic.n_days
    assert good.rank_ic.n_days > 0
    assert bad.rank_ic.n_days == 0


def test_tied_factor_values_are_not_split_into_distinct_quantiles():
    frame = pl.DataFrame(
        {
            "date": [dt.date(2024, 1, 2)] * 100,
            "f": np.repeat([0.0, 1.0], 50),
            "forward": np.arange(100, dtype=float),
        }
    )
    buckets = decile_profile(frame, "f")
    populated = [bucket for bucket in buckets if bucket.n_samples]
    assert [(bucket.bucket, bucket.n_samples) for bucket in populated] == [(3, 50), (8, 50)]
    assert [bucket.mean_forward for bucket in populated] == [24.5, 74.5]


def _panel(
    n_days: int = 30,
    n_assets: int = 120,
    *,
    start: dt.date = dt.date(2024, 1, 1),
    noise: float = 0.0,
    seed: int = 7,
) -> pl.DataFrame:
    """构造合成面板：因子 f 决定 t+1 开盘到 t+2 开盘的收益（可注入噪声）。

    为了让"前瞻收益"与 t0 的因子相关，价格序列按
    ``close[d+2] = close[d+1] * (1 + 0.01 * f[d] + noise)`` 倒推构造。
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for asset_index in range(n_assets):
        factors = rng.normal(size=n_days)
        shocks = rng.normal(0, noise, size=n_days)
        closes = [0.0] * n_days
        closes[-1] = 10.0
        closes[-2] = 10.0
        for day_index in range(n_days - 3, -1, -1):
            growth = 1.0 + 0.01 * factors[day_index] + shocks[day_index]
            closes[day_index + 1] = closes[day_index + 2] / growth
        for day_index in range(n_days):
            rows.append(
                {
                    "date": start + dt.timedelta(days=day_index),
                    "asset": f"A{asset_index:04d}",
                    "f": float(factors[day_index]),
                    "open": closes[day_index],
                    "close": closes[day_index],
                }
            )
    return pl.DataFrame(rows).sort(["asset", "date"])


def test_forward_return_expr_uses_next_open_entry_and_exit():
    """持有 1 日：t1 开盘买入、t2 开盘卖出。"""
    frame = pl.DataFrame(
        {
            "asset": ["A", "A", "A"],
            "di": [0, 1, 2],
            "open": [10.0, 11.0, 12.0],
        }
    ).with_columns(
        forward_return_expr(1, "open").alias("fwd"),
    )

    assert frame["fwd"][0] == pytest.approx(12.0 / 11.0 - 1.0)
    assert frame["fwd"][1] is None


def test_forward_return_expr_supports_other_holding_windows():
    """持有 N 日：t1 开盘买入、t(N+1) 开盘卖出。"""
    frame = pl.DataFrame(
        {
            "asset": ["A"] * 5,
            "di": [0, 1, 2, 3, 4],
            "open": [10.0, 11.0, 12.0, 13.0, 14.0],
        }
    ).with_columns(forward_return_expr(3, "open").alias("fwd"))

    # 持有 3 日：t1 开盘买（11.0）、t4 开盘卖（14.0）
    assert frame["fwd"][0] == pytest.approx(14.0 / 11.0 - 1.0)


def test_forward_return_expr_rejects_invalid_holding():
    with pytest.raises(ValueError):
        forward_return_expr(0)


def test_adjacent_trading_day_expr_flags_gaps():
    """停牌跳日时样本无效。"""
    frame = pl.DataFrame(
        {
            "asset": ["A", "A", "A"],
            "di": [0, 1, 3],  # 中间缺一个交易日
            "open": [10.0, 11.0, 12.0],
        }
    ).with_columns(adjacent_trading_day_expr(1).alias("ok"))

    assert frame["ok"][0] is False
    assert frame["ok"][1] is False


def test_ensure_trading_index_adds_column():
    frame = pl.DataFrame(
        {
            "date": [dt.date(2024, 1, 2), dt.date(2024, 1, 1), dt.date(2024, 1, 3)],
            "asset": ["A"] * 3,
        }
    )

    indexed = ensure_trading_index(frame)

    assert "di" in indexed.columns
    assert indexed["di"].to_list() == [1, 0, 2]


def test_prepare_forward_returns_marks_valid_rows():
    panel = _panel(n_days=10, n_assets=110)

    prepared = prepare_forward_returns(panel, holding_days=1, price="close")

    assert "forward" in prepared.columns
    assert "valid" in prepared.columns
    assert prepared.filter(pl.col("valid")).height < prepared.height


def test_daily_rank_ic_detects_monotonic_relationship():
    """因子与前瞻收益正相关时 RankIC 接近 +1。"""
    panel = _panel(n_days=20, n_assets=150, noise=0.0001)

    frame = (
        ensure_trading_index(panel)
        .with_columns(
            [
                forward_return_expr(1, "close").alias("forward"),
                adjacent_trading_day_expr(1).alias("valid"),
            ]
        )
        .filter(pl.col("valid") & pl.col("forward").is_not_null())
    )

    ics = daily_rank_ic(frame, "f")

    assert len(ics) > 0
    assert float(np.mean(ics)) > 0.5


def test_summarize_computes_mean_and_t_stat():
    summary = summarize([0.1, 0.2, 0.3, 0.2, 0.1])

    assert isinstance(summary, RankIcSummary)
    assert summary.mean == pytest.approx(0.18)
    assert summary.n_days == 5
    assert summary.t_stat > 2.0


def test_summarize_handles_empty():
    summary = summarize([])

    assert summary.n_days == 0
    assert math.isnan(summary.mean)


def test_decile_profile_is_monotonic_for_strong_signal():
    """强信号下，十分位越高平均前瞻收益越高。"""
    panel = _panel(n_days=20, n_assets=150, noise=0.0001)
    frame = (
        ensure_trading_index(panel)
        .with_columns(
            [
                forward_return_expr(1, "close").alias("forward"),
                adjacent_trading_day_expr(1).alias("valid"),
            ]
        )
        .filter(pl.col("valid") & pl.col("forward").is_not_null())
    )

    buckets = decile_profile(frame, "f", buckets=10)

    assert len(buckets) == 10
    assert buckets[0].bucket == 1
    assert buckets[-1].mean_forward > buckets[0].mean_forward


def test_yearly_rank_ic_splits_by_year():
    panel = _panel(n_days=40, n_assets=150, start=dt.date(2023, 12, 25))
    frame = (
        ensure_trading_index(panel)
        .with_columns(
            [
                forward_return_expr(1, "close").alias("forward"),
                adjacent_trading_day_expr(1).alias("valid"),
            ]
        )
        .filter(pl.col("valid") & pl.col("forward").is_not_null())
    )

    by_year = yearly_rank_ic(frame, "f")

    assert set(by_year) == {2023, 2024}
    assert by_year[2024].n_days > 0


def test_study_single_factor_end_to_end():
    panel = _panel(n_days=20, n_assets=150, noise=0.0001)

    result = study_single_factor(panel, "f", holding_days=1, price="close")

    assert result.factor == "f"
    assert result.holding_days == 1
    assert result.rank_ic.n_days > 0
    assert result.rank_ic.mean > 0.5
    assert len(result.deciles) == 10
    assert result.n_rows > 0
    payload = result.as_dict()
    assert payload["holding_days"] == 1
    assert "rank_ic" in payload


def test_study_single_factor_rejects_missing_factor():
    with pytest.raises(KeyError):
        study_single_factor(_panel(n_days=5, n_assets=110), "not_there", holding_days=1)


def test_study_single_factor_respects_min_cross_section():
    """截面太小的交易日不参与统计。"""
    panel = _panel(n_days=5, n_assets=MIN_CROSS_SECTION - 10)

    result = study_single_factor(panel, "f", holding_days=1, price="close")

    assert result.rank_ic.n_days == 0
    assert math.isnan(result.rank_ic.mean)


def test_format_report_contains_key_fields():
    panel = _panel(n_days=20, n_assets=150, noise=0.0001)
    result = study_single_factor(panel, "f", holding_days=1, price="close")

    text = format_report([result])

    assert "f | 持有 1 日" in text
    assert "RankIC" in text
    assert "十分位" in text


def test_study_factors_matches_single_factor_results() -> None:
    """批量检验与单因子检验结果一致。"""
    from quantide.factors.alphatest import study_factors

    panel = _panel(n_days=20, n_assets=150, noise=0.0001)

    batch = study_factors(panel, ["f"], holding_days=1, price="close")
    single_f = study_single_factor(panel, "f", holding_days=1, price="close")

    assert [r.factor for r in batch] == ["f"]
    by_factor = {r.factor: r for r in batch}
    assert by_factor["f"].rank_ic.mean == pytest.approx(single_f.rank_ic.mean)
    assert by_factor["f"].rank_ic.n_days == single_f.rank_ic.n_days
    assert len(by_factor["f"].deciles) == len(single_f.deciles)


def test_study_factors_rejects_missing_factor() -> None:
    from quantide.factors.alphatest import study_factors

    with pytest.raises(KeyError):
        study_factors(_panel(n_days=5, n_assets=110), ["missing"], holding_days=1)
