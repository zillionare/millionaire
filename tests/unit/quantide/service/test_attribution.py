"""策略预测归因能力（动态加载）测试。"""

import datetime as dt
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from quantide.core.enums import BrokerKind
from quantide.data.models.entities import Portfolio
from quantide.factors import FEATURE_COLS
from quantide.service import attribution as attribution_service
from quantide.strategies.example import ml_momentum_reversal
from quantide.strategies.example.ml_momentum_reversal import MLMomentumReversalStrategy


class _AttributionStrategy:
    """声明支持 shap 归因的假策略。"""

    ATTRIBUTION = "shap"

    def __init__(self, broker, config):
        self.broker = broker
        self.config = config

    def explain_prediction(
        self,
        asset: str,
        signal_date: dt.date,
        bt_start: dt.date | None = None,
        bt_end: dt.date | None = None,
    ):
        return {"asset": asset, "date": signal_date, "features": []}


class _PlainStrategy:
    """未声明归因能力的策略。"""

    def __init__(self, broker, config):
        self.broker = broker
        self.config = config


def test_attribution_kind_reads_strategy_declaration() -> None:
    assert attribution_service.attribution_kind(_AttributionStrategy) == "shap"
    assert attribution_service.attribution_kind(_PlainStrategy) is None
    assert attribution_service.attribution_kind(None) is None
    assert attribution_service.supports_attribution(_AttributionStrategy) is True
    assert attribution_service.supports_attribution(_PlainStrategy) is False


def test_attribution_kind_requires_explain_implementation() -> None:
    class _DeclaredOnly:
        ATTRIBUTION = "shap"

    assert attribution_service.attribution_kind(_DeclaredOnly) is None


def test_ml_strategy_declares_shap_attribution() -> None:
    assert MLMomentumReversalStrategy.ATTRIBUTION == "shap"
    assert callable(MLMomentumReversalStrategy.explain_prediction)


def test_load_backtest_config_reads_portfolio_info(monkeypatch) -> None:
    monkeypatch.setattr(
        attribution_service.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=BrokerKind.BACKTEST,
            start=dt.date(2024, 1, 2),
            name="MLMomentumReversalStrategy",
            info='{"config": {"top_k": 3}}',
        ),
    )

    config = attribution_service.load_backtest_config("pf-1")

    assert config == {"top_k": 3}


def test_explain_prediction_requires_supported_strategy(monkeypatch) -> None:
    monkeypatch.setattr(
        attribution_service.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=BrokerKind.BACKTEST,
            start=dt.date(2024, 1, 2),
            name="PlainStrategy",
        ),
    )
    monkeypatch.setattr(
        attribution_service.strategy_loader,
        "load_from_cache",
        lambda: {"PlainStrategy": _PlainStrategy},
    )

    assert (
        attribution_service.explain_prediction("pf-1", "000001.SZ", dt.date(2024, 1, 3))
        is None
    )


def test_explain_prediction_delegates_to_strategy(monkeypatch) -> None:
    monkeypatch.setattr(
        attribution_service.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=BrokerKind.BACKTEST,
            start=dt.date(2024, 1, 2),
            name="MLMomentumReversalStrategy",
            info='{"config": {"top_k": 3}}',
        ),
    )
    monkeypatch.setattr(
        attribution_service.strategy_loader,
        "load_from_cache",
        lambda: {"MLMomentumReversalStrategy": _AttributionStrategy},
    )

    result = attribution_service.explain_prediction(
        "pf-1", "000001.SZ", dt.date(2024, 1, 3)
    )

    assert result is not None
    assert result["asset"] == "000001.SZ"


def _synthetic_norm_panel() -> pl.DataFrame:
    """构造 3 天 × 4 只股票的标准化特征面板。"""
    rows: list[dict[str, object]] = []
    for day_index, day in enumerate(
        [dt.date(2024, 1, 2), dt.date(2024, 1, 3), dt.date(2024, 1, 4)]
    ):
        for asset_index, asset in enumerate(
            ["000001.SZ", "000002.SZ", "600000.SH", "300001.SZ"]
        ):
            row: dict[str, object] = {
                "date": day,
                "asset": asset,
                "board": "主板",
            }
            for col_index, col in enumerate(FEATURE_COLS):
                row[f"{col}_z"] = float(
                    ((day_index + 1) * 0.1 + asset_index * 0.2 + col_index * 0.01)
                    % 1.5
                    - 0.4
                )
            rows.append(row)
    return pl.DataFrame(rows).sort(["asset", "date"])


def test_explain_prediction_sums_to_final_score(monkeypatch) -> None:
    """模型贡献 + 先验贡献 + 基线 必须精确还原最终得分。"""
    panel = _synthetic_norm_panel()
    strategy = MLMomentumReversalStrategy(
        SimpleNamespace(_bt_end=None, positions={}, cash=0.0), {"use_lightgbm": True}
    )
    monkeypatch.setattr(
        strategy, "_ensure_backtest_panel", lambda signal_date: None, raising=False
    )
    monkeypatch.setattr(
        type(strategy),
        "_cached_norm_panel",
        property(lambda self: panel),
        raising=False,
    )

    # 用确定性的线性模型替代 LightGBM，验证归因的可加性
    weights = np.arange(1, len(FEATURE_COLS) + 1, dtype=float) / 100.0
    monkeypatch.setattr(
        __import__("quantide.strategies.example._ml_explanation", fromlist=["_fit_ml_model"]),
        "_fit_ml_model",
        lambda *args, **kwargs: (weights, "Ridge"),
    )

    result = strategy.explain_prediction("000002.SZ", dt.date(2024, 1, 4))

    assert result is not None
    assert result["engine"] == "Ridge"
    assert result["cross_section"] == 4
    assert result["rank"] >= 1
    total = result["baseline"] + sum(item["total"] for item in result["features"])
    assert total == pytest.approx(result["score"], abs=1e-6)


def test_explain_prediction_uses_result_cache(monkeypatch) -> None:
    """同一笔交易的归因结果应被缓存，重复请求不再计算。"""
    monkeypatch.setattr(
        attribution_service.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=BrokerKind.BACKTEST,
            start=dt.date(2024, 1, 2),
            name="MLMomentumReversalStrategy",
            info='{"config": {"top_k": 3}}',
        ),
    )
    monkeypatch.setattr(
        attribution_service.strategy_loader,
        "load_from_cache",
        lambda: {"MLMomentumReversalStrategy": _AttributionStrategy},
    )
    calls: list[str] = []

    class _CountingStrategy(_AttributionStrategy):
        def explain_prediction(
            self,
            asset: str,
            signal_date: dt.date,
            bt_start: dt.date | None = None,
            bt_end: dt.date | None = None,
        ):
            calls.append(asset)
            return {"asset": asset, "date": signal_date, "features": []}

    monkeypatch.setattr(
        attribution_service.strategy_loader,
        "load_from_cache",
        lambda: {"MLMomentumReversalStrategy": _CountingStrategy},
    )
    attribution_service._EXPLAIN_RESULT_CACHE.clear()

    first = attribution_service.explain_prediction(
        "cache-pf", "000001.SZ", dt.date(2024, 1, 3)
    )
    second = attribution_service.explain_prediction(
        "cache-pf", "000001.SZ", dt.date(2024, 1, 3)
    )

    assert first is not None
    assert second == first
    assert len(calls) == 1


def test_load_holdings_at_restores_positions(monkeypatch) -> None:
    """归因必须还原决策日持仓（选股池优先保留持仓）。"""
    import polars as pl

    monkeypatch.setattr(
        attribution_service.db,
        "query_positions",
        lambda portfolio_id=None, start=None, end=None: pl.DataFrame(
            {
                "portfolio_id": ["pf-1", "pf-1", "pf-1"],
                "dt": [
                    dt.date(2024, 1, 2),
                    dt.date(2024, 1, 3),
                    dt.date(2024, 1, 3),
                ],
                "asset": ["000001.SZ", "000002.SZ", "000003.SZ"],
                "shares": [100.0, 200.0, 0.0],
                "avail": [100.0, 200.0, 0.0],
                "price": [10.0, 20.0, 30.0],
                "profit": [0.0, 0.0, 0.0],
                "mv": [1000.0, 4000.0, 0.0],
            }
        ),
    )

    held = attribution_service.load_holdings_at("pf-1", dt.date(2024, 1, 4))

    assert set(held) == {"000002.SZ"}
    assert held["000002.SZ"].shares == 200.0


def test_cache_version_changes_with_factor_or_pipeline(monkeypatch) -> None:
    """改因子/改策略后，缓存版本随之变化（缓存自动失效）。"""
    version = attribution_service._cache_version(_AttributionStrategy)
    assert version.startswith(attribution_service.FACTOR_VERSION)

    class _Other(_AttributionStrategy):
        PIPELINE_VERSION = "deadbeef"

    assert attribution_service._cache_version(_Other) != version
