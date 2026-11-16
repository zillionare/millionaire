"""因子库（quantide.factors）单元测试。

因子与策略解耦后，因子的计算方法、含义与示例在这里独立验证。
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.factors import (
    FEATURE_COLS,
    FEATURE_DOCS,
    FEATURE_GROUPS,
    compute_alpha_features,
    list_feature_specs,
    resolve_feature_selection,
    standardize_features,
)
from tests.unit.quantide.factors.panel_builder import _make_synthetic_panel


def test_compute_alpha_features_emits_all_features() -> None:
    panel = _make_synthetic_panel()
    features = compute_alpha_features(panel)

    assert len(FEATURE_COLS) == 28
    assert set(FEATURE_COLS) <= set(features.columns)
    assert features.height == panel.height

    latest = features.filter(pl.col("date") == features["date"].max())
    non_null = latest.select(
        [pl.col(name).is_not_null().all().alias(name) for name in FEATURE_COLS]
    ).row(0, named=True)
    assert all(non_null.values()), non_null


def test_feature_docs_cover_every_feature() -> None:
    """每个特征都必须有「计算方法 / 含义 / 示例」文档。"""
    docs = FEATURE_DOCS

    assert set(docs) == set(FEATURE_COLS)
    for name, text in docs.items():
        assert "计算：" in text, name
        assert "含义：" in text, name
        assert "示例：" in text, name


def _shadow_panel(
    *,
    up_limit_ratio: float,
    n_flat_days: int = 20,
) -> pl.DataFrame:
    """构造一根可手算影线的 K 线面板。

    前 ``n_flat_days`` 天：开=收=10、高=10.5、低=9.5 → 真实波幅恒为 1.0；
    末日：开=收=10、高=10.3、低=9.3 → 上影 0.3(3%)、下影 0.7(7%)、波幅 1.0。
    因此 ``atr20`` 恒为 1.0，影线的三种口径都可以手算。
    """
    rows: list[dict[str, object]] = []
    start = dt.date(2024, 1, 2)
    for index in range(n_flat_days + 1):
        day = start + dt.timedelta(days=index)
        if index < n_flat_days:
            open_price = close = 10.0
            high, low = 10.5, 9.5
        else:
            open_price = close = 10.0
            high, low = 10.3, 9.3
        rows.append(
            {
                "date": day,
                "asset": "600001.SH",
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000.0,
                "amount": 1000.0 * close,
                "adjust": 1.0,
                "is_st": False,
                "up_limit": round(10.0 * (1.0 + up_limit_ratio), 2),
                "down_limit": round(10.0 * (1.0 - up_limit_ratio), 2),
            }
        )
    return pl.DataFrame(rows)


def test_shadow_features_three_normalizations_match_hand_calculation() -> None:
    """同一根 K 线的三种影线口径：比例 / ATR / 涨跌停限。"""
    features = compute_alpha_features(_shadow_panel(up_limit_ratio=0.05))
    last = features.filter(pl.col("date") == features["date"].max()).row(0, named=True)

    # 末日：上影 0.3、下影 0.7、振幅 1.0、atr20 = 1.0、昨收 10.0
    assert last["atr20"] == pytest.approx(1.0)
    assert last["prev_close"] == pytest.approx(10.0)
    assert last["upper_shadow"] == pytest.approx(0.3)
    assert last["lower_shadow"] == pytest.approx(0.7)
    assert last["upper_shadow_atr"] == pytest.approx(0.3)
    assert last["lower_shadow_atr"] == pytest.approx(0.7)
    # ST：涨停 5% → 上影 3% / 5% = 0.6；下影 7% / 5% = 1.4
    assert last["limit_pct"] == pytest.approx(5.0)
    assert last["upper_shadow_limit"] == pytest.approx(0.6)
    assert last["lower_shadow_limit"] == pytest.approx(1.4)
    # CLV 改用 ATR 归一：(2*10 - 10.3 - 9.3) / 1.0 = 0.4
    assert last["clv_atr"] == pytest.approx(0.4)
    assert last["clv"] == pytest.approx(0.4)


def test_shadow_limit_normalization_is_board_aware() -> None:
    """同样的 3% 上影：ST(5%) 读作 0.6，创业板(20%) 读作 0.15。"""
    st = compute_alpha_features(_shadow_panel(up_limit_ratio=0.05))
    st_last = st.filter(pl.col("date") == st["date"].max()).row(0, named=True)
    gem = compute_alpha_features(_shadow_panel(up_limit_ratio=0.20))
    gem_last = gem.filter(pl.col("date") == gem["date"].max()).row(0, named=True)

    assert st_last["upper_shadow_limit"] == pytest.approx(0.6)
    assert gem_last["upper_shadow_limit"] == pytest.approx(0.15)
    # ATR 口径与板块无关
    assert st_last["upper_shadow_atr"] == pytest.approx(gem_last["upper_shadow_atr"])


def test_shadow_limit_is_null_without_price_limit() -> None:
    """缺少涨跌停价时，涨跌停口径为空（标准化后按 0 处理）。"""
    panel = _shadow_panel(up_limit_ratio=0.10).with_columns(pl.lit(0.0).alias("up_limit"))
    features = compute_alpha_features(panel)
    last = features.filter(pl.col("date") == features["date"].max()).row(0, named=True)

    assert last["limit_pct"] is None
    assert last["upper_shadow_limit"] is None
    assert last["upper_shadow_atr"] == pytest.approx(0.3)


def test_true_range_accounts_for_gap() -> None:
    """真实波幅包含跳空：跳空日的 ATR 会被放大。"""
    rows = []
    start = dt.date(2024, 1, 2)
    for index in range(6):
        day = start + dt.timedelta(days=index)
        if index == 5:
            open_price = close = 12.0
            high, low = 12.1, 11.9
        else:
            open_price = close = 10.0
            high, low = 10.5, 9.5
        rows.append(
            {
                "date": day,
                "asset": "600001.SH",
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000.0,
                "amount": 1000.0 * close,
                "adjust": 1.0,
                "is_st": False,
                "up_limit": 11.0,
                "down_limit": 9.0,
            }
        )
    features = compute_alpha_features(pl.DataFrame(rows))
    last = features.filter(pl.col("date") == features["date"].max()).row(0, named=True)

    # 跳空日：|high - prev_close| = |12.1 - 10| = 2.1 > 当日波幅 0.2
    assert last["true_range"] == pytest.approx(2.1)
    assert last["upper_shadow"] == pytest.approx(0.1 / 0.2)


def test_compute_alpha_features_industry_overrides_prefix_board() -> None:
    panel = _make_synthetic_panel()
    meta = pl.DataFrame(
        {
            "asset": ["600001.SH", "688001.SH"],
            "industry": ["新能源", "半导体"],
        }
    )

    features = compute_alpha_features(panel, stock_meta=meta)
    latest = features.filter(pl.col("date") == features["date"].max())
    board_by_asset = dict(latest.select(["asset", "board"]).iter_rows())

    assert board_by_asset["600001.SH"] == "新能源"
    assert board_by_asset["688001.SH"] == "半导体"
    assert board_by_asset["300001.SZ"] == "创业板"
    assert board_by_asset["002001.SZ"] == "深市中小"


def test_compute_alpha_features_prefix_board_without_meta() -> None:
    features = compute_alpha_features(_make_synthetic_panel())
    latest = features.filter(pl.col("date") == features["date"].max())
    board_by_asset = dict(latest.select(["asset", "board"]).iter_rows())

    assert board_by_asset["600001.SH"] == "主板"
    assert board_by_asset["300001.SZ"] == "创业板"
    assert board_by_asset["688001.SH"] == "科创板"
    assert board_by_asset["002001.SZ"] == "深市中小"


def test_factor_catalog_lists_every_feature_with_doc() -> None:
    """因子清单覆盖全部因子，并带上说明文档。"""
    specs = list_feature_specs()

    assert len(specs) == len(FEATURE_COLS)
    assert {spec.name for spec in specs} == set(FEATURE_COLS)
    assert all(spec.doc for spec in specs)
    assert {spec.group for spec in specs} == set(FEATURE_GROUPS)


def test_feature_groups_use_compact_taxonomy() -> None:
    """分组名称保持精简，均线支撑归入形态，均线斜率归入动量与反转。"""
    assert list(FEATURE_GROUPS) == ["相对强弱", "短线形态", "资金推动", "动量与反转"]
    assert "ma20_support_bounce" in FEATURE_GROUPS["短线形态"]
    assert {"ma10_slope", "ma20_slope", "ma_alignment", "bias_5", "bias_20"} <= set(
        FEATURE_GROUPS["动量与反转"]
    )


def test_resolve_feature_selection_defaults_to_all() -> None:
    """未勾选时使用全部因子。"""
    assert resolve_feature_selection(None) == FEATURE_COLS
    assert resolve_feature_selection([]) == FEATURE_COLS


def test_resolve_feature_selection_keeps_catalog_order() -> None:
    """勾选结果按因子目录顺序返回（与模型列顺序一致）。"""
    selected = resolve_feature_selection(["bias_5", "rs_board_5d"])

    assert selected == ["rs_board_5d", "bias_5"]


def test_resolve_feature_selection_rejects_unknown_feature() -> None:
    """勾选未知因子必须报错，避免静默用错列。"""
    with pytest.raises(ValueError):
        resolve_feature_selection(["not_a_feature"])


def test_standardize_features_only_emits_requested_columns() -> None:
    """标准化只产出勾选因子的 z 列。"""
    panel = _make_synthetic_panel(n_days=30, n_assets=6)
    features = compute_alpha_features(panel)

    normalized = standardize_features(features, ["bias_5", "ma20_slope"])

    assert "bias_5_z" in normalized.columns
    assert "ma20_slope_z" in normalized.columns
    assert "rs_board_5d_z" not in normalized.columns
