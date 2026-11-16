"""策略预测归因能力的动态加载。

web 层不感知具体模型：策略类通过 ``ATTRIBUTION`` 声明自己支持的归因方式
（当前为 ``"shap"``），并实现 ``explain_prediction(asset, signal_date)``。
本模块负责按回测组合找到策略、取出配置并调用该实现。
"""

from __future__ import annotations

import datetime
from typing import Any, cast

import polars as pl
from loguru import logger

from quantide.core.ports.broker import ExecutionResult
from quantide.core.strategy_config import stored_strategy_config
from quantide.data.sqlite import db
from quantide.factors import FACTOR_VERSION
from quantide.service.discovery import strategy_loader

ATTRIBUTION_SHAP = "shap"

#: 归因结果缓存（键：组合/资产/决策日/因子集），避免页签来回切换时重复计算
_EXPLAIN_RESULT_CACHE: dict[tuple[Any, ...], dict[str, Any] | None] = {}
#: 因子取值缓存（同样的键），特征页与 SHAP 页共用
_EXPLAIN_FEATURE_CACHE: dict[tuple[Any, ...], list[tuple[str, float]] | None] = {}
_EXPLAIN_RESULT_CACHE_MAX = 64


class _AttributionPosition:
    """归因用的持仓替身（只需要股数）。"""

    def __init__(self, shares: float) -> None:
        self.shares = shares
        self.avail = shares
        self.price = 0.0
        self.mv = 0.0


class _AttributionBroker:
    """归因用的最小 broker 替身。

    - ``positions``：回测当时的持仓，选股池会优先保留持仓；
    - ``bt_end``：回测结束日，面板抓取窗口依赖它（否则窗口会被截断到信号日，
      截面就取不到目标日期了）。
    """

    portfolio_id = "attribution"

    def __init__(
        self,
        positions: dict[str, Any] | None = None,
        bt_end: datetime.date | None = None,
    ) -> None:
        self._bt_end: datetime.date | None = bt_end
        self.positions: dict[str, Any] = positions or {}
        self.cash: float = 0.0

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Attribution never records metrics."""
        return None

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: object = "1d",
        *,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """Attribution does not execute strategy bar callbacks."""
        raise NotImplementedError("attribution broker does not provide history")

    def get_prices(self, assets: list[str]) -> dict[str, float]:
        """Attribution does not execute risk overlays."""
        raise NotImplementedError("attribution broker does not provide prices")

    def get_ticks(self, asset: str, count: int) -> pl.DataFrame:
        """Attribution does not execute risk overlays."""
        raise NotImplementedError("attribution broker does not provide ticks")

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        raise NotImplementedError("attribution broker cannot trade")

    async def buy_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        raise NotImplementedError("attribution broker cannot trade")

    async def buy_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        raise NotImplementedError("attribution broker cannot trade")

    async def sell(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        raise NotImplementedError("attribution broker cannot trade")

    async def sell_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        raise NotImplementedError("attribution broker cannot trade")

    async def sell_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        raise NotImplementedError("attribution broker cannot trade")

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        raise NotImplementedError("attribution broker cannot trade")

    async def cancel_order(self, qt_oid: str) -> object:
        raise NotImplementedError("attribution broker cannot cancel orders")

    async def cancel_all_orders(self, side: object = None) -> int:
        raise NotImplementedError("attribution broker cannot cancel orders")


def _cache_version(strategy_cls: Any) -> str:
    """缓存版本：因子版本 + 策略流水线版本（源码哈希）。

    因子公式或策略逻辑变化后，版本随之变化，缓存自动失效；服务重启同样失效。
    """
    pipeline = str(getattr(strategy_cls, "PIPELINE_VERSION", "") or "")
    return f"{FACTOR_VERSION}:{pipeline}"


def attribution_kind(strategy_cls: Any) -> str | None:
    """返回策略声明的归因方式；未声明则返回 ``None``。

    Args:
        strategy_cls: 策略类。

    Returns:
        str | None: 归因方式标识（如 ``"shap"``）。
    """
    if strategy_cls is None:
        return None
    kind = getattr(strategy_cls, "ATTRIBUTION", None)
    if not kind:
        return None
    if not callable(getattr(strategy_cls, "explain_prediction", None)):
        return None
    return str(kind)


def supports_attribution(strategy_cls: Any) -> bool:
    """策略是否支持逐次预测归因。"""
    return attribution_kind(strategy_cls) is not None


def backtest_range(portfolio: Any) -> tuple[datetime.date, datetime.date] | None:
    """回测实际的 bar 区间。

    组合的 ``start`` 记录的是回测首个交易日的前一交易日（broker 时钟），
    ``end`` 即回测最后一个交易日。

    Args:
        portfolio: 回测组合。

    Returns:
        tuple | None: (起始 bar 日, 结束 bar 日)；信息缺失时返回 ``None``。
    """
    from quantide.data.models.calendar import calendar

    start = getattr(portfolio, "start", None)
    end = getattr(portfolio, "end", None)
    if not isinstance(start, datetime.date) or not isinstance(end, datetime.date):
        return None
    try:
        bt_start = calendar.day_shift(start, 1)
    except Exception:
        bt_start = start
    return bt_start, end


def load_holdings_at(portfolio_id: str, signal_date: datetime.date) -> dict[str, Any]:
    """读取回测在决策日的持仓（用于还原当时的选股池）。

    Args:
        portfolio_id: 回测组合 ID。
        signal_date: 决策日。

    Returns:
        dict: 资产代码 → 持仓替身。
    """
    try:
        positions = db.query_positions(portfolio_id=portfolio_id, end=signal_date)
    except Exception:
        return {}
    if positions is None or positions.is_empty():
        return {}
    latest = positions["dt"].max()
    held: dict[str, Any] = {}
    for row in positions.filter(pl.col("dt") == latest).iter_rows(named=True):
        shares = float(row.get("shares") or 0)
        if shares > 0:
            held[str(row.get("asset") or "")] = _AttributionPosition(shares)
    return held


def load_positions_by_date(portfolio_id: str) -> dict[datetime.date, dict[str, float]]:
    """读取回测期间的每日持仓快照（日期 → 资产 → 股数）。

    选股池会优先保留当时的持仓，归因必须用同一份持仓才能复现当时的选股池。

    Args:
        portfolio_id: 回测组合 ID。

    Returns:
        dict: 持仓快照。
    """
    try:
        positions = db.query_positions(portfolio_id=portfolio_id)
    except Exception:
        return {}
    if positions is None or positions.is_empty():
        return {}
    snapshot: dict[datetime.date, dict[str, float]] = {}
    for row in positions.iter_rows(named=True):
        day = row.get("dt")
        if not isinstance(day, datetime.date):
            continue
        shares = float(row.get("shares") or 0)
        if shares <= 0:
            continue
        snapshot.setdefault(day, {})[str(row.get("asset") or "")] = shares
    return snapshot


def load_backtest_config(portfolio_id: str) -> dict[str, Any]:
    """读取回测实际使用的配置。

    Args:
        portfolio_id: 回测组合 ID。

    Returns:
        dict: 配置字典；缺失时返回空字典。
    """
    portfolio = db.get_portfolio(portfolio_id)
    if portfolio is None:
        return {}
    return stored_strategy_config(getattr(portfolio, "info", "") or "")


def explain_features(
    portfolio_id: str,
    asset: str,
    signal_date: datetime.date,
    bt_start: datetime.date | None = None,
    bt_end: datetime.date | None = None,
) -> list[tuple[str, float]] | None:
    """按策略能力动态取该资产在决策日的因子取值。

    Args:
        portfolio_id: 回测组合 ID。
        asset: 证券代码。
        signal_date: 决策日。

    Returns:
        list | None: (因子名, 取值) 列表；策略不支持或数据不足时返回 ``None``。
    """
    portfolio = db.get_portfolio(portfolio_id)
    if portfolio is None:
        return None
    strategy_cls = strategy_loader.load_from_cache().get(portfolio.name or "")
    if strategy_cls is None:
        return None
    if not callable(getattr(strategy_cls, "explain_features", None)):
        return None
    if bt_start is None or bt_end is None:
        rng = backtest_range(portfolio)
        if rng is not None:
            bt_start, bt_end = rng
    config = load_backtest_config(portfolio_id)
    cache_key = (
        portfolio_id,
        asset,
        signal_date,
        tuple(config.get("features") or ()),
        _cache_version(strategy_cls),
    )
    if cache_key in _EXPLAIN_FEATURE_CACHE:
        return _EXPLAIN_FEATURE_CACHE[cache_key]
    try:
        strategy = strategy_cls(
            _AttributionBroker(load_holdings_at(portfolio_id, signal_date), bt_end),
            config,
        )
        strategy._positions_by_date = load_positions_by_date(portfolio_id)
        explainer = getattr(strategy, "explain_features", None)
        if not callable(explainer):
            return None
        result = cast(list[tuple[str, float]] | None, explainer(asset, signal_date))
    except Exception:
        logger.exception(
            f"因子取值计算失败: portfolio={portfolio_id} asset={asset} signal={signal_date}"
        )
        return None
    if len(_EXPLAIN_FEATURE_CACHE) >= _EXPLAIN_RESULT_CACHE_MAX:
        _EXPLAIN_FEATURE_CACHE.pop(next(iter(_EXPLAIN_FEATURE_CACHE)))
    _EXPLAIN_FEATURE_CACHE[cache_key] = result
    return result


def explain_prediction(
    portfolio_id: str,
    asset: str,
    signal_date: datetime.date,
    bt_start: datetime.date | None = None,
    bt_end: datetime.date | None = None,
) -> dict[str, Any] | None:
    """按策略能力动态计算某笔交易的预测归因。

    Args:
        portfolio_id: 回测组合 ID。
        asset: 证券代码。
        signal_date: 决策日。
        bt_start: 回测起始交易日；缺省时从组合记录推导。
        bt_end: 回测结束交易日；缺省时从组合记录推导。

    Returns:
        dict | None: 归因结果；策略不支持或数据不足时返回 ``None``。
    """
    portfolio = db.get_portfolio(portfolio_id)
    if portfolio is None:
        return None
    strategy_cls = strategy_loader.load_from_cache().get(portfolio.name or "")
    if strategy_cls is None or not supports_attribution(strategy_cls):
        return None
    if bt_start is None or bt_end is None:
        rng = backtest_range(portfolio)
        if rng is not None:
            bt_start, bt_end = rng
    config = load_backtest_config(portfolio_id)
    cache_key = (
        portfolio_id,
        asset,
        signal_date,
        tuple(config.get("features") or ()),
        _cache_version(strategy_cls),
    )
    if cache_key in _EXPLAIN_RESULT_CACHE:
        return _EXPLAIN_RESULT_CACHE[cache_key]
    try:
        strategy = strategy_cls(
            _AttributionBroker(load_holdings_at(portfolio_id, signal_date), bt_end),
            config,
        )
        strategy._positions_by_date = load_positions_by_date(portfolio_id)
        explainer = getattr(strategy, "explain_prediction", None)
        if not callable(explainer):
            return None
        result = cast(dict[str, Any] | None, explainer(asset, signal_date, bt_start, bt_end))
    except Exception:
        logger.exception(
            f"归因计算失败: portfolio={portfolio_id} asset={asset} signal={signal_date}"
        )
        return None
    if len(_EXPLAIN_RESULT_CACHE) >= _EXPLAIN_RESULT_CACHE_MAX:
        _EXPLAIN_RESULT_CACHE.pop(next(iter(_EXPLAIN_RESULT_CACHE)))
    _EXPLAIN_RESULT_CACHE[cache_key] = result
    return result
