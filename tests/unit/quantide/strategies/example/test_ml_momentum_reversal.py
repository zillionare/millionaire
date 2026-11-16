"""Unit tests for the ML momentum/reversal stock-selection strategy.

Coverage targets:
- Strategy discovery/metadata and parameter contract.
- The five alpha-feature groups and industry-based board override.
 - Future close-return labeling without signal-time lookahead.
 - LightGBM / Prior-Ridge selection and eligibility exclusions.
 - ``on_bar`` daily top-K rebalance behavior.
- Web stock-selection modal, list button, and POST re-run route.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fasthtml.common import to_xml

from quantide.core.strategy import BaseStrategy
from quantide.core.strategy_discovery import StrategyDiscovery
from quantide.factors.alpha import compute_alpha_features, standardize_features
from quantide.strategies.example import ml_momentum_reversal
from quantide.strategies.example.ml_momentum_reversal import (
    MLMomentumReversalStrategy,
    _fit_ml_model,
    _format_candidate_rows,
    compute_future_close_return_labels,
)
from quantide.web.pages import strategy as strategy_page
from tests.unit.quantide.factors.panel_builder import _make_synthetic_panel

try:
    import lightgbm as _lightgbm  # noqa: F401

    HAS_LIGHTGBM = True
except ImportError:  # pragma: no cover - exercised only without the optional dep
    HAS_LIGHTGBM = False


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------


def _ohlc_panel(rows: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    """Build a single-asset OHLC panel from ``(open, high, low, close)`` rows."""
    start = dt.date(2024, 1, 2)
    return pl.DataFrame(
        {
            "date": [start + dt.timedelta(days=i) for i in range(len(rows))],
            "asset": ["600001.SH"] * len(rows),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
        }
    )


def _lock_up_limit(panel: pl.DataFrame, asset: str) -> pl.DataFrame:
    """Make ``asset`` close at its up-limit on the final bar."""
    last_date = panel["date"].max()
    mask = (pl.col("asset") == asset) & (pl.col("date") == last_date)
    limit = panel.filter(mask)["up_limit"][0]
    return panel.with_columns(
        pl.when(mask).then(pl.lit(limit)).otherwise(pl.col("close")).alias("close"),
        pl.when(mask)
        .then(pl.max_horizontal(pl.col("high"), pl.lit(limit)))
        .otherwise(pl.col("high"))
        .alias("high"),
    )


# ---------------------------------------------------------------------------
# 1. Discovery & metadata contract
# ---------------------------------------------------------------------------


def test_strategy_is_a_base_strategy_subclass() -> None:
    assert issubclass(MLMomentumReversalStrategy, BaseStrategy)


def test_strategy_discovery_finds_clean_metadata() -> None:
    root = Path(ml_momentum_reversal.__file__).parent
    result = StrategyDiscovery.discover(root)

    matches = [s for s in result.strategies if s.name == "MLMomentumReversalStrategy"]
    assert len(matches) == 1
    metadata = matches[0]
    assert metadata.strategy_type == "independent"
    assert metadata.default_config == MLMomentumReversalStrategy.default_config()

    not_a_strategy = [
        d for d in result.diagnostics if d.reason.value == "NotAStrategy"
    ]
    invalid_config = [
        d for d in result.diagnostics if d.reason.value == "InvalidConfig"
    ]
    assert not_a_strategy == []
    assert invalid_config == []
    assert result.diagnostics == []


def test_default_config_and_params_expose_required_keys() -> None:
    required = {
        "top_k",
        "universe_size",
        "train_window",
        "future_return_horizon",
        "retrain_days",
        "use_lightgbm",
    }
    assert required <= set(MLMomentumReversalStrategy.PARAMS)
    assert required <= set(MLMomentumReversalStrategy.default_config())
    assert MLMomentumReversalStrategy.default_config() == (
        MLMomentumReversalStrategy.PARAMS
    )
    assert MLMomentumReversalStrategy.default_config() is not (
        MLMomentumReversalStrategy.PARAMS
    )


# ---------------------------------------------------------------------------
# 2. Feature engineering (5 groups)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 3. Future close-return labeling
# ---------------------------------------------------------------------------


def test_future_close_return_label_uses_n_trading_day_close() -> None:
    rows = [
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 102.0, 99.0, 102.0),
        (102.0, 104.0, 101.0, 104.0),
        (104.0, 106.0, 103.0, 106.0),
        (106.0, 108.0, 105.0, 108.0),
    ]
    labeled = compute_future_close_return_labels(_ohlc_panel(rows), horizon=3)

    first = labeled.row(0, named=True)
    assert first["future_n_trading_day_close_return"] == pytest.approx(
        106.0 / 100.0 - 1.0
    )


def test_future_close_return_label_has_no_lookahead_on_last_horizon_rows() -> None:
    horizon = 3
    labeled = compute_future_close_return_labels(
        _make_synthetic_panel(), horizon=horizon
    )

    null_counts = labeled.group_by("asset").agg(
        pl.col("future_n_trading_day_close_return")
        .is_null()
        .sum()
        .alias("null_count")
    )
    assert null_counts["null_count"].to_list() == [horizon] * labeled[
        "asset"
    ].n_unique()

    non_null = labeled.filter(
        pl.col("future_n_trading_day_close_return").is_not_null()
    )
    assert non_null.height > 0


# ---------------------------------------------------------------------------
# 4. LightGBM & Prior-Ridge stock selection
# ---------------------------------------------------------------------------


_SELECTION_CONFIG = {
    "top_k": 5,
    "universe_size": 1000,
    "train_window": 45,
    "future_return_horizon": 3,
    "retrain_days": 5,
    "use_lightgbm": True,
}

_CANDIDATE_KEYS = {
    "rank",
    "asset",
    "name",
    "board",
    "close",
    "ml_score",
    "kline_pattern",
    "signal_reason",
}


def test_select_stocks_lightgbm_contract_has_no_exit_metadata() -> None:
    panel = _make_synthetic_panel()
    picks = MLMomentumReversalStrategy.select_stocks(
        bars_df=panel, config=_SELECTION_CONFIG
    )

    assert len(picks) == _SELECTION_CONFIG["top_k"]
    assert [item["rank"] for item in picks] == list(range(1, len(picks) + 1))

    # 65 days x 12 assets leaves ~45 training dates x 11 eligible assets,
    # far above the 30-sample LightGBM threshold in ``_fit_ml_model``.
    if HAS_LIGHTGBM:
        assert {item["model_engine"] for item in picks} == {"LightGBM"}
    else:  # pragma: no cover - only when the optional dependency is missing
        assert {item["model_engine"] for item in picks} <= {
            "LightGBM",
            "Prior-Ridge",
        }

    for item in picks:
        assert _CANDIDATE_KEYS <= set(item)
        assert "tb_barrier_text" not in item
        assert "tp_price" not in item
        assert "sl_price" not in item


def test_select_stocks_prior_ridge_when_lightgbm_disabled() -> None:
    panel = _make_synthetic_panel()
    picks = MLMomentumReversalStrategy.select_stocks(
        bars_df=panel,
        config={**_SELECTION_CONFIG, "use_lightgbm": False},
    )

    assert len(picks) == _SELECTION_CONFIG["top_k"]
    assert {item["model_engine"] for item in picks} == {"Prior-Ridge"}


def test_fit_ml_model_reuses_labels_without_dropping_selected_features() -> None:
    panel = _make_synthetic_panel()
    feature_cols = ["rs_board_5d", "ma20_slope"]
    normalized = standardize_features(
        compute_alpha_features(panel), feature_cols=feature_cols
    )
    cache_key = ("label-cache-regression", id(normalized))

    first_model, first_engine = _fit_ml_model(
        normalized,
        use_lightgbm=False,
        feature_cols=[feature_cols[0]],
        label_cache_key=cache_key,
    )
    second_model, second_engine = _fit_ml_model(
        normalized,
        use_lightgbm=False,
        feature_cols=[feature_cols[1]],
        label_cache_key=cache_key,
    )

    assert first_engine == second_engine == "Prior-Ridge"
    assert first_model is not None and second_model is not None
    assert first_model.shape == (1,)
    assert second_model.shape == (1,)


def test_select_stocks_accepts_missing_optional_limit_inputs() -> None:
    panel = _make_synthetic_panel().drop(["up_limit", "down_limit"])
    picks = MLMomentumReversalStrategy.select_stocks(
        bars_df=panel,
        config={
            **_SELECTION_CONFIG,
            "use_lightgbm": False,
            "features": ["upper_shadow_limit", "ma20_slope"],
        },
    )

    assert len(picks) == _SELECTION_CONFIG["top_k"]


def test_select_stocks_excludes_st_stocks() -> None:
    panel = _make_synthetic_panel().with_columns(
        pl.when(pl.col("asset") == "600001.SH")
        .then(True)
        .otherwise(pl.col("is_st"))
        .alias("is_st")
    )
    picks = MLMomentumReversalStrategy.select_stocks(
        bars_df=panel,
        config={**_SELECTION_CONFIG, "top_k": 20},
    )

    assets = {item["asset"] for item in picks}
    assert "600001.SH" not in assets
    assert len(picks) <= 20


def test_select_stocks_excludes_up_limit_locked_stocks() -> None:
    panel = _lock_up_limit(_make_synthetic_panel(), "300001.SZ")
    picks = MLMomentumReversalStrategy.select_stocks(
        bars_df=panel,
        config={**_SELECTION_CONFIG, "top_k": 20},
    )

    assets = {item["asset"] for item in picks}
    assert "300001.SZ" not in assets
    assert len(picks) <= 20


def test_top_k_is_only_an_upper_bound_after_eligibility_filtering() -> None:
    """Invalid ST/suspended/limit rows are removed before applying top_k."""
    scored = pl.DataFrame(
        {
            "asset": ["GOOD.SZ", "ST.SZ", "SUSPENDED.SZ", "LOCKED.SZ"],
            "close": [10.0, 10.0, 10.0, 10.0],
            "volume": [1000.0, 1000.0, 0.0, 1000.0],
            "is_st": [False, True, False, False],
            "up_limit": [11.0, 11.0, 11.0, 10.0],
            "ml_score": [1.0, 4.0, 3.0, 2.0],
        }
    )

    picks = _format_candidate_rows(
        scored, dt.date(2024, 1, 2), "Prior-Ridge", limit=3
    )

    assert [item["asset"] for item in picks] == ["GOOD.SZ"]


def test_filter_universe_market_cap_trim_then_st_and_suspension(monkeypatch) -> None:
    monkeypatch.setattr(
        ml_momentum_reversal.stock_list, "_data", pl.DataFrame()
    )
    panel = _make_synthetic_panel(n_assets=20)
    assets = sorted(panel["asset"].unique())
    caps = pl.DataFrame(
        {
            "asset": assets,
            "total_mv": [float(i + 1) * 1e9 for i in range(len(assets))],
        }
    )
    panel = panel.join(caps, on="asset", how="left")

    last_date = panel["date"].max()
    st_asset = assets[5]
    suspended_asset = assets[6]
    panel = panel.with_columns(
        pl.when((pl.col("asset") == st_asset) & (pl.col("date") == last_date))
        .then(True)
        .otherwise(pl.col("is_st"))
        .alias("is_st"),
        pl.when(
            (pl.col("asset") == suspended_asset) & (pl.col("date") == last_date)
        )
        .then(0.0)
        .otherwise(pl.col("volume"))
        .alias("volume"),
    )

    selected = ml_momentum_reversal._filter_universe(
        panel,
        last_date,
        universe_size=300,
        mode="market_cap_trim",
        trim_pct=0.05,
    )

    expected = set(assets[1:5] + assets[7:19])
    assert set(selected) == expected


def test_filter_universe_falls_back_to_liquidity_without_market_cap(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ml_momentum_reversal.stock_list, "_data", pl.DataFrame()
    )
    panel = _make_synthetic_panel(n_assets=20)
    selected = ml_momentum_reversal._filter_universe(
        panel,
        panel["date"].max(),
        universe_size=5,
        mode="market_cap_trim",
        trim_pct=0.05,
    )
    assert len(selected) == 5


# ---------------------------------------------------------------------------
# 5. on_bar execution: daily top-K rebalance
# ---------------------------------------------------------------------------


class _FakeBroker:
    """Broker boundary fake that records orders and exposes portfolio state."""

    def __init__(
        self,
        *,
        cash: float = 1_000_000.0,
        positions: dict[str, object] | None = None,
    ) -> None:
        self.positions = dict(positions or {})
        self.cash = cash
        self.portfolio_id = "unit-test"
        self.buy_calls: list[tuple[str, float, dict[str, object]]] = []
        self.sell_calls: list[tuple[str, int, dict[str, object]]] = []

    async def buy_amount(self, asset: str, amount: float, **kwargs: object):
        self.buy_calls.append((asset, float(amount), kwargs))
        return SimpleNamespace(trades=[object()])

    async def sell(self, asset: str, shares: int, **kwargs: object):
        self.sell_calls.append((asset, int(shares), kwargs))
        return SimpleNamespace(trades=[object()])


def _make_strategy(
    broker: _FakeBroker, config: dict[str, object] | None = None
) -> MLMomentumReversalStrategy:
    strategy = MLMomentumReversalStrategy(broker, config)
    strategy.logs = []
    strategy.log = lambda msg, *args, **kwargs: strategy.logs.append(str(msg))
    return strategy


def _ranked_item(asset: str, score: float, rank: int = 1) -> dict[str, object]:
    return {
        "rank": rank,
        "asset": asset,
        "name": asset,
        "ml_score": score,
        "kline_pattern": "量价共振向上",
        "signal_reason": "板块超额+1.0% | MA20斜率向上(+1.0%) | 日内资金净流入",
    }


async def test_on_bar_buys_top_ranked_candidates_into_open_slots() -> None:
    broker = _FakeBroker(cash=100_000.0)
    strategy = _make_strategy(broker, {"top_k": 2, "use_lightgbm": False})
    ranked = [
        _ranked_item("600001.SH", 0.9, 1),
        _ranked_item("300001.SZ", 0.8, 2),
        _ranked_item("688001.SH", 0.7, 3),
    ]
    strategy._rank_for_bar = lambda tm: (
        ranked,
        {"600001.SH": 10.0, "300001.SZ": 20.0, "688001.SH": 30.0},
        {"600001.SH": 1, "300001.SZ": 2, "688001.SH": 3},
    )

    await strategy.on_bar(dt.datetime(2024, 6, 3, 14, 58))

    assert [asset for asset, _amount, _kwargs in broker.buy_calls] == [
        "600001.SH",
        "300001.SZ",
    ]
    for _asset, amount, _kwargs in broker.buy_calls:
        assert amount == pytest.approx(49_000.0)


async def test_on_bar_sells_every_available_holding_absent_from_top_k() -> None:
    position = SimpleNamespace(shares=100, avail=100, price=10.0, mv=1000.0)
    broker = _FakeBroker(cash=0.0, positions={"600001.SH": position})
    strategy = _make_strategy(broker, {"top_k": 1, "use_lightgbm": False})
    strategy._rank_for_bar = lambda tm: (
        [_ranked_item("600002.SH", -10.0, 1)],
        {"600002.SH": 10.0},
        {"600002.SH": 1},
    )

    await strategy.on_bar(dt.datetime(2024, 6, 3, 14, 58))

    assert [(asset, shares) for asset, shares, _kw in broker.sell_calls] == [
        ("600001.SH", 100)
    ]
    assert any("不在今日Top-1" in message for message in strategy.logs)


async def test_on_bar_keeps_selected_holding_and_buys_new_top_k_asset() -> None:
    held = SimpleNamespace(shares=100, avail=100, price=10.0, mv=1000.0)
    broker = _FakeBroker(cash=100_000.0, positions={"600001.SH": held})
    strategy = _make_strategy(broker, {"top_k": 2, "use_lightgbm": False})
    strategy._rank_for_bar = lambda tm: (
        [
            _ranked_item("600001.SH", -100.0, 1),
            _ranked_item("600002.SH", -200.0, 2),
        ],
        {"600001.SH": 10.0, "600002.SH": 20.0},
        {"600001.SH": 1, "600002.SH": 2},
    )

    await strategy.on_bar(dt.datetime(2024, 6, 3, 14, 58))

    assert broker.sell_calls == []
    assert [asset for asset, _amount, _kwargs in broker.buy_calls] == ["600002.SH"]


def test_strategy_has_no_risk_overlay_or_barrier_parameters() -> None:
    strategy_cls = ml_momentum_reversal.MLMomentumReversalStrategy
    assert not hasattr(strategy_cls, "RISK_OVERLAY")
    assert not {
        "keep_top_n",
        "stop_loss_pct",
        "take_profit_pct",
        "use_broker_barriers",
        "use_alpha_exit",
    } & set(strategy_cls.default_config())


# ---------------------------------------------------------------------------
# 6. Web stock-selection modal & routes
# ---------------------------------------------------------------------------


class FakeRequest:
    def __init__(self, form_data: dict[str, str]) -> None:
        self._form_data = form_data

    async def form(self) -> dict[str, str]:
        return self._form_data


def _sample_picks() -> list[dict[str, object]]:
    return [
        {
            "rank": 1,
            "asset": "600001.SH",
            "name": "示例股份",
            "board": "主板",
            "close": 10.0,
            "ret_1d": 0.01,
            "ret_5d": 0.02,
            "ret_20d": 0.05,
            "ml_score": 0.8123,
            "rs_board_20d": 0.03,
            "kline_pattern": "低开阳线弱转强",
            "signal_reason": "板块超额+5.0% | MA20斜率向上(+1.0%) | 日内资金净流入",
            "as_of_date": "2024-12-31",
            "model_engine": "LightGBM",
            "future_return_horizon": 3,
        }
    ]


def _install_selection_mocks(monkeypatch, picks, calls=None):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {"MLMomentumReversalStrategy": MLMomentumReversalStrategy},
    )

    def _fake_select(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return list(picks)

    monkeypatch.setattr(
        MLMomentumReversalStrategy,
        "select_stocks",
        staticmethod(_fake_select),
    )


def test_build_strategy_rows_renders_stock_selection_button(monkeypatch) -> None:
    _install_selection_mocks(monkeypatch, _sample_picks())
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolios_by_strategy",
        lambda name: pl.DataFrame(),
    )

    rows = strategy_page._build_strategy_rows(
        {"MLMomentumReversalStrategy": MLMomentumReversalStrategy}
    )
    html = to_xml(rows[0])

    assert "选股" in html
    assert 'hx-get="/strategy/MLMomentumReversalStrategy/select/modal"' in html


def test_strategy_select_modal_renders_future_return_target(monkeypatch) -> None:
    _install_selection_mocks(monkeypatch, _sample_picks())

    html = to_xml(
        strategy_page.strategy_select_modal("MLMomentumReversalStrategy")
    )

    assert 'id="stock-selection-table"' in html
    assert "600001.SH" in html
    assert "示例股份" in html
    assert "低开阳线弱转强" in html
    assert "未来3日收盘收益（仅训练）" in html
    assert "0.812" in html
    assert "模型引擎: LightGBM" in html


async def test_run_strategy_select_uses_submitted_params(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    _install_selection_mocks(monkeypatch, _sample_picks(), calls=calls)
    request = FakeRequest(
        {
            "as_of_date": "2024-12-31",
            "param_top_k": "3",
            "param_universe_size": "50",
            "param_train_window": "30",
            "param_future_return_horizon": "3",
            "param_use_lightgbm": "true",
        }
    )

    html = to_xml(
        await strategy_page.run_strategy_select(
            request, "MLMomentumReversalStrategy"
        )
    )

    assert calls[0]["config"]["top_k"] == 3
    assert calls[0]["config"]["use_lightgbm"] is True
    assert calls[0]["as_of_date"] == "2024-12-31"
    assert 'id="stock-selection-table"' in html
    assert "600001.SH" in html
    assert "未来3日收盘收益（仅训练）" in html


def test_strategy_select_modal_warns_when_requested_date_exceeds_local_data(
    monkeypatch,
) -> None:
    _install_selection_mocks(monkeypatch, _sample_picks())
    monkeypatch.setattr(
        strategy_page,
        "_get_default_selection_date",
        lambda: "2024-12-31",
    )

    html = to_xml(
        strategy_page._render_stock_selection_modal(
            "MLMomentumReversalStrategy",
            MLMomentumReversalStrategy,
            as_of_date="2026-10-20",
            auto_run=True,
        )
    )

    assert "请求日期 2026-10-20 晚于本地最新行情 2024-12-31" in html
    assert "已自动使用最近可用交易日 2024-12-31 选股" in html
    assert "选股基准日: 2024-12-31" in html


def test_strategy_select_modal_exposes_loading_indicator(monkeypatch) -> None:
    _install_selection_mocks(monkeypatch, _sample_picks())
    monkeypatch.setattr(
        strategy_page,
        "_get_default_selection_date",
        lambda: "2024-12-31",
    )

    html = to_xml(
        strategy_page.strategy_select_modal("MLMomentumReversalStrategy")
    )

    assert 'id="select-loading"' in html
    assert 'hx-indicator="#select-loading"' in html
    assert 'hx-disabled-elt="this"' in html
    assert "正在拉取行情、计算 24 个因子并运行模型" in html


def test_selection_date_notice_same_day_is_empty() -> None:
    assert (
        strategy_page._resolve_selection_date_notice(
            "2024-12-31",
            "2024-12-31",
            "2024-12-31",
            has_picks=True,
        )
        == ""
    )


def test_build_strategy_rows_marks_global_loading_indicator(monkeypatch) -> None:
    _install_selection_mocks(monkeypatch, _sample_picks())
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolios_by_strategy",
        lambda name: pl.DataFrame(),
    )

    rows = strategy_page._build_strategy_rows(
        {"MLMomentumReversalStrategy": MLMomentumReversalStrategy}
    )
    html = to_xml(rows[0])

    assert 'hx-indicator="#global-loading"' in html


def test_filter_universe_respects_universe_size_in_market_cap_trim_mode(monkeypatch):
    """market_cap_trim 模式必须遵守 universe_size（之前被忽略，导致截面是全市场）。"""
    monkeypatch.setattr(
        ml_momentum_reversal.stock_list, "_data", pl.DataFrame()
    )
    panel = _make_synthetic_panel(n_assets=20, n_days=3)
    total_date = panel["date"].max()
    panel = panel.with_columns(
        (pl.col("close") * (pl.arange(pl.len()).cast(pl.Float64) + 1.0)).alias("total_mv")
    )

    assets = ml_momentum_reversal._filter_universe(
        panel, total_date, 5, mode="market_cap_trim", trim_pct=0.0
    )

    assert len(assets) == 5


def test_filter_universe_market_cap_trim_draws_random_sample(monkeypatch):
    """裁剪后随机抽取 N 只（种子与日期绑定，可复现）。"""
    monkeypatch.setattr(
        ml_momentum_reversal.stock_list, "_data", pl.DataFrame()
    )
    panel = _make_synthetic_panel(n_assets=20, n_days=3)
    total_date = panel["date"].max()
    market_caps = {
        asset: float(index + 1) * 1e8
        for index, asset in enumerate(sorted(panel["asset"].unique().to_list()))
    }
    panel = panel.with_columns(
        pl.col("asset").replace_strict(market_caps, default=0.0).alias("total_mv")
    )

    assets = ml_momentum_reversal._filter_universe(
        panel, total_date, 3, mode="market_cap_trim", trim_pct=0.0
    )
    again = ml_momentum_reversal._filter_universe(
        panel, total_date, 3, mode="market_cap_trim", trim_pct=0.0
    )

    assert len(assets) == 3
    # 同一日期重复调用必须得到同一批股票
    assert assets == again
    # 不是简单取市值最大的 N 只
    largest = set(sorted(market_caps, key=lambda a: market_caps[a])[-3:])
    assert set(assets) != largest


def test_filter_universe_membership_is_stable_across_rebalance_dates(monkeypatch):
    """稳定哈希抽样：成员不随调仓日轮换（避免持仓被"未入池"强制卖出）。"""
    monkeypatch.setattr(
        ml_momentum_reversal.stock_list, "_data", pl.DataFrame()
    )
    panel = _make_synthetic_panel(n_assets=20, n_days=3)
    market_caps = {
        asset: float(index + 1) * 1e8
        for index, asset in enumerate(sorted(panel["asset"].unique().to_list()))
    }
    panel = panel.with_columns(
        pl.col("asset").replace_strict(market_caps, default=0.0).alias("total_mv")
    )
    dates = sorted(panel["date"].unique().to_list())

    first = ml_momentum_reversal._filter_universe(
        panel, dates[0], 5, mode="market_cap_trim", trim_pct=0.0
    )
    last = ml_momentum_reversal._filter_universe(
        panel, dates[-1], 5, mode="market_cap_trim", trim_pct=0.0
    )

    assert len(first) == 5
    assert first == last


def test_filter_universe_always_keeps_current_holdings(monkeypatch):
    """持仓优先入池，其余按稳定哈希补足，保证持仓不会被"未入池"强卖。"""
    monkeypatch.setattr(
        ml_momentum_reversal.stock_list, "_data", pl.DataFrame()
    )
    panel = _make_synthetic_panel(n_assets=20, n_days=3)
    market_caps = {
        asset: float(index + 1) * 1e8
        for index, asset in enumerate(sorted(panel["asset"].unique().to_list()))
    }
    panel = panel.with_columns(
        pl.col("asset").replace_strict(market_caps, default=0.0).alias("total_mv")
    )
    total_date = panel["date"].max()
    all_assets = sorted(panel["asset"].unique().to_list())
    # 选一个"哈希排序靠后"的股票作为持仓，它本不该被随机抽到
    held = [all_assets[-1]]

    without = ml_momentum_reversal._filter_universe(
        panel, total_date, 5, mode="market_cap_trim", trim_pct=0.0
    )
    with_holding = ml_momentum_reversal._filter_universe(
        panel, total_date, 5, mode="market_cap_trim", trim_pct=0.0, holdings=held
    )

    assert len(with_holding) == 5
    assert held[0] in with_holding
    assert held[0] not in without


def test_filter_universe_holdings_do_not_change_size(monkeypatch):
    """持仓入池后仍要补足到 universe_size。"""
    monkeypatch.setattr(
        ml_momentum_reversal.stock_list, "_data", pl.DataFrame()
    )
    panel = _make_synthetic_panel(n_assets=20, n_days=3)
    panel = panel.with_columns(
        (pl.col("close") * 1000.0).alias("total_mv")
    )
    total_date = panel["date"].max()
    all_assets = sorted(panel["asset"].unique().to_list())

    assets = ml_momentum_reversal._filter_universe(
        panel,
        total_date,
        8,
        mode="market_cap_trim",
        trim_pct=0.0,
        holdings=all_assets[:3],
    )

    assert len(assets) == 8
    assert set(all_assets[:3]) <= set(assets)


def test_explain_cache_keys_include_versions_and_holdings(monkeypatch) -> None:
    """归因缓存键必须含流水线/因子版本与当时持仓，避免命中旧结果。"""
    strategy = _make_strategy(
        _FakeBroker(cash=0.0, positions={}), {"use_lightgbm": False}
    )
    cross_key, model_key = strategy._explain_cache_keys(dt.date(2024, 6, 3))

    assert ml_momentum_reversal.PIPELINE_VERSION in cross_key
    assert ml_momentum_reversal.FACTOR_VERSION in cross_key
    assert () in cross_key  # 持仓元组
    assert cross_key != model_key  # 模型键额外含 use_lightgbm


def test_explain_cache_keys_change_with_holdings(monkeypatch) -> None:
    """持仓不同 → 缓存键不同（选股池不同）。"""
    position = SimpleNamespace(shares=100, avail=100, price=10.0, mv=1000.0)
    empty = _make_strategy(_FakeBroker(cash=0.0, positions={}), {})
    held = _make_strategy(
        _FakeBroker(cash=0.0, positions={"600001.SH": position}), {}
    )

    assert empty._explain_cache_keys(dt.date(2024, 6, 3)) != held._explain_cache_keys(
        dt.date(2024, 6, 3)
    )


# ---------------------------------------------------------------------------
# 7. 精确归因：回放选池/训练节奏
# ---------------------------------------------------------------------------


class _StubCalendar:
    """仅支持工作日的交易日历替身。"""

    def __init__(self, days: list[dt.date]):
        self._days = sorted(days)

    def _index(self, day: dt.date) -> int:
        for index, value in enumerate(self._days):
            if value >= day:
                return index
        return len(self._days)

    def day_shift(self, day: dt.date, offset: int) -> dt.date:
        index = self._index(day) + offset
        index = max(0, min(len(self._days) - 1, index))
        return self._days[index]

    def shift(self, day: dt.date, offset: int, frame_type=None) -> dt.date:
        return self.day_shift(day, offset)

    def get_frames(self, start: dt.date, end: dt.date, frame_type=None) -> list[dt.date]:
        return [d for d in self._days if start <= d <= end]


def _stub_strategy(monkeypatch, days: list[dt.date], **overrides):
    from quantide.strategies.example import ml_momentum_reversal as module

    monkeypatch.setattr(module, "calendar", _StubCalendar(days))
    monkeypatch.setattr("quantide.strategies.example._ml_explanation.calendar", _StubCalendar(days))
    broker = SimpleNamespace(_bt_end=None, positions={}, cash=0.0)
    config = {"universe_size": 10, "universe_rebalance_days": 5, "retrain_days": 2}
    config.update(overrides)
    return module.MLMomentumReversalStrategy(broker, config)


def _weekdays(start: dt.date, count: int) -> list[dt.date]:
    days: list[dt.date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += dt.timedelta(days=1)
    return days


def test_replay_panel_builds_follow_rebalance_grid(monkeypatch) -> None:
    """面板按 universe_rebalance_days 刷新，回放序列与回测一致。"""
    days = _weekdays(dt.date(2024, 1, 1), 40)
    strategy = _stub_strategy(monkeypatch, days, universe_rebalance_days=5)

    builds = strategy._replay_panel_builds(days[0], days[-1])

    # 首个 bar 的信号日是前一个交易日；窗口为 [信号日, 信号日+5]，
    # 因此下一次重建发生在信号日越过窗口的那一根 bar（滞后一根 → 每 6 个 bar）
    assert builds[0][0] == days[0]
    assert [b[0] for b in builds][:3] == [days[0], days[6], days[12]]


def test_replay_context_finds_panel_and_refit(monkeypatch) -> None:
    """目标信号日能定位到当次面板构建日与最近一次模型重训。"""
    days = _weekdays(dt.date(2024, 1, 1), 40)
    strategy = _stub_strategy(monkeypatch, days, universe_rebalance_days=5, retrain_days=2)

    target_signal = days[6]
    target_build, refit_build, refit_signal = strategy._replay_context(
        target_signal, days[0], days[-1]
    )

    assert target_build == days[6]  # 该信号日正是第 2 个面板窗口的构建日
    # retrain_days=2 → 在 bar 1,3,5,7... 重训；目标信号日最近的一次重训在 days[5]
    # （该 bar 的信号日），它落在第 1 个面板窗口里
    assert refit_signal == days[5]
    assert refit_build == days[0]


def test_panel_cache_key_covers_lookback_and_window_inputs(monkeypatch) -> None:
    """面板缓存键必须覆盖所有影响面板内容的参数，避免跨组合污染。"""
    days = _weekdays(dt.date(2024, 1, 1), 20)
    base = _stub_strategy(monkeypatch, days, train_window=45)
    other_window = _stub_strategy(monkeypatch, days, train_window=120)
    other_rebalance = _stub_strategy(monkeypatch, days, universe_rebalance_days=10)

    signal_date = days[5]
    base_key = base._panel_cache_key(signal_date)
    assert base_key != other_window._panel_cache_key(signal_date)
    assert base_key != other_rebalance._panel_cache_key(signal_date)
    assert base_key == base._panel_cache_key(signal_date)


def test_panel_cache_key_tracks_backtest_end_date(monkeypatch) -> None:
    """回测结束日不同（面板窗口不同）时缓存键必须不同。"""
    days = _weekdays(dt.date(2024, 1, 1), 20)
    first = _stub_strategy(monkeypatch, days)
    second = _stub_strategy(monkeypatch, days)
    second.broker._bt_end = days[-1]

    signal_date = days[5]
    assert first._panel_cache_key(signal_date) != second._panel_cache_key(signal_date)


def test_explain_cache_keys_include_build_signal(monkeypatch) -> None:
    """缓存键必须包含面板构建日，避免不同窗口互相污染。"""
    days = _weekdays(dt.date(2024, 1, 1), 20)
    strategy = _stub_strategy(monkeypatch, days)

    cross_key, model_key = strategy._explain_cache_keys(days[3], days[0])

    assert days[0] in cross_key
    assert days[3] in cross_key
    assert model_key != cross_key


def test_retrain_cadence_counts_trading_days_not_bar_calls(monkeypatch) -> None:
    """重训节奏按交易日计：同一交易日内多次调用不触发重训。"""
    days = _weekdays(dt.date(2024, 1, 1), 30)
    strategy = _stub_strategy(monkeypatch, days, retrain_days=5)

    # 第一天：没有模型 -> 需要重训
    assert strategy._should_retrain(days[0]) is True
    strategy._model = object()  # 模拟已拟合出模型
    strategy._mark_retrained()

    # 同一天内多次调用（实盘每 2 秒一次）不重训
    for _ in range(50):
        assert strategy._should_retrain(days[0]) is False

    # 每过一个交易日计数 +1，第 5 个交易日再次重训
    for index, day in enumerate(days[1:6], start=1):
        expected = index >= 5
        assert strategy._should_retrain(day) is expected
        if expected:
            strategy._mark_retrained()


def test_retrain_cadence_matches_backtest_bar_grid(monkeypatch) -> None:
    """回测里仍是每 5 个 bar 重训一次（与历史回测口径一致）。"""
    days = _weekdays(dt.date(2024, 1, 1), 30)
    strategy = _stub_strategy(monkeypatch, days, retrain_days=5)

    fits = []
    for index, day in enumerate(days):
        if strategy._should_retrain(day):
            fits.append(index)
            strategy._model = object()  # 模拟已拟合出模型
            strategy._mark_retrained()

    assert fits[:4] == [0, 5, 10, 15]


def test_on_bar_is_idempotent_within_same_signal_day(monkeypatch) -> None:
    """同一信号日内重复 on_bar 不会重复决策（实盘每 2 秒轮询）。"""
    days = _weekdays(dt.date(2024, 1, 1), 20)
    strategy = _stub_strategy(monkeypatch, days)

    calls: list[dt.date] = []

    def _fake_rank(tm):
        calls.append(tm.date())
        return [], {}, {}

    monkeypatch.setattr(strategy, "_rank_for_bar", _fake_rank)

    tm = dt.datetime(2024, 1, 2, 14, 58, 0)
    import asyncio

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        strategy.on_bar(tm)
    )
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        strategy.on_bar(tm)
    )

    # 第二次调用被去重拦截
    assert len(calls) == 1


def test_filter_universe_index_pit_uses_constituents(monkeypatch):
    """index_pit 只保留目标日指数成分（PIT）。"""
    import quantide.data as data_mod
    from quantide.strategies.example.ml_momentum_reversal import _filter_universe

    class _Store:
        def constituents(self, code, as_of, include_weight=True):
            assert code == "000300.SH"
            return pl.DataFrame(
                {
                    "date": [as_of, as_of],
                    "index_code": [code, code],
                    "con_code": ["000001.SZ", "600000.SH"],
                }
            )

    monkeypatch.setattr(data_mod, "get_index_weight_store", lambda: _Store())
    bars = pl.DataFrame(
        {
            "date": [dt.date(2024, 3, 1)] * 3,
            "asset": ["000001.SZ", "600000.SH", "000002.SZ"],
            "close": [10.0, 10.0, 10.0],
            "volume": [1000.0, 1000.0, 1000.0],
            "is_st": [False, False, False],
        }
    )
    picked = _filter_universe(
        bars,
        dt.date(2024, 3, 1),
        2000,
        mode="index_pit",
        index_codes=["000300.SH"],
    )
    assert picked == ["000001.SZ", "600000.SH"]


def test_filter_universe_index_pit_falls_back_when_empty(monkeypatch):
    """成分数据缺失时退回市值/流动性裁剪，不返回空池。"""
    import quantide.data as data_mod
    from quantide.strategies.example.ml_momentum_reversal import _filter_universe

    class _Store:
        def constituents(self, code, as_of, include_weight=True):
            return pl.DataFrame()

    monkeypatch.setattr(data_mod, "get_index_weight_store", lambda: _Store())
    bars = pl.DataFrame(
        {
            "date": [dt.date(2024, 5, 6)] * 2,
            "asset": ["000001.SZ", "600000.SH"],
            "close": [10.0, 20.0],
            "volume": [1000.0, 2000.0],
            "amount": [10000.0, 40000.0],
            "is_st": [False, False],
        }
    )
    picked = _filter_universe(
        bars,
        dt.date(2024, 5, 6),
        2000,
        mode="index_pit",
        index_codes=["000300.SH"],
    )
    assert picked == ["000001.SZ", "600000.SH"]


async def test_on_bar_skips_decisions_before_auction_in_live_mode() -> None:
    """实盘 14:57 前不决策（避免盘中提前下单）。"""
    broker = _FakeBroker(cash=100_000.0)
    strategy = _make_strategy(broker, {"top_k": 2, "use_lightgbm": False})
    strategy._rank_for_bar = lambda tm: ([], {"600001.SH": 10.0}, {})
    await strategy.on_bar(dt.datetime(2024, 6, 3, 10, 0))
    assert strategy._last_executed_signal_date is None
