"""Strategy metrics."""

import datetime
from collections.abc import Mapping
from typing import Any

import arrow
import polars as pl
from fasthtml.common import *
from monsterui.all import *

from quantide.core.enums import FrameType, OrderSide
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.metrics import metrics
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.pages.strategy_format import (
    _metric_value,
    _normalize_stats,
)
from quantide.web.pages.strategy_routes import (
    BENCHMARK_ASSET,
)


def _append_benchmark_series(
    benchmark_df: pl.DataFrame,
    total_series: list[float | None],
    date_axis: list[str],
    benchmark_series: list[float | None],
) -> list[float | None]:
    """Align benchmark equity with the portfolio date axis."""
    if not benchmark_df.is_empty():
        benchmark_df = benchmark_df.sort("date")
        close_by_date = {}
        for row in benchmark_df.iter_rows(named=True):
            dt = arrow.get(row["date"]).format("YYYY-MM-DD")
            close_by_date[dt] = row.get("close")
        first_total = next((v for v in total_series if v is not None), None)
        first_close = next(
            (close_by_date.get(dt) for dt in date_axis if close_by_date.get(dt)),
            None,
        )
        if first_total is None:
            first_total = 1.0
        if first_close:
            benchmark_series = []
            for dt in date_axis:
                close = close_by_date.get(dt)
                if close is None:
                    benchmark_series.append(None)
                else:
                    benchmark_series.append(first_total * float(close) / float(first_close))
    return benchmark_series


def _append_equity_after_history(
    daily_pnl_series: list[float | None],
    dt: str,
    last_date: str | None,
    prev_total: float | None,
    total_by_date: Mapping[str, float | None],
    total_series: list[float | None],
) -> float | None:
    """Append equity after history."""
    if last_date is not None and dt > last_date:
        total_series.append(None)
        daily_pnl_series.append(None)
    else:
        total = total_by_date.get(dt)
        total_series.append(total)
        if total is None or prev_total is None:
            daily_pnl_series.append(0.0)
        else:
            daily_pnl_series.append(total - prev_total)
        prev_total = total if total is not None else prev_total
    return prev_total


def _build_date_axis(portfolio_id: str) -> list[str]:
    """构建完整时间轴。

    Args:
        portfolio_id: 组合 ID

    Returns:
        list[str]: 日期字符串列表
    """
    portfolio = db.get_portfolio(portfolio_id)
    if portfolio:
        start_date = portfolio.start
        end_date = portfolio.end or portfolio.start
    else:
        assets_df = db.query_assets(portfolio_id)
        if assets_df.is_empty():
            return []
        assets_df = assets_df.sort("dt")
        start_date = assets_df.row(0, named=True)["dt"]
        end_date = assets_df.row(-1, named=True)["dt"]
    dates = calendar.get_frames(start_date, end_date, FrameType.DAY)
    return [arrow.get(dt).format("YYYY-MM-DD") for dt in dates]


def _build_series_payload(portfolio_id: str, date_axis: list[str]) -> dict[str, Any]:
    """构建曲线及日度序列。

    Args:
        portfolio_id: 组合 ID
        date_axis: 时间轴

    Returns:
        dict: 序列数据
    """
    assets_df = db.query_assets(portfolio_id)
    if assets_df.is_empty() or not date_axis:
        return {
            "date_axis": date_axis,
            "total": [None for _ in date_axis],
            "benchmark": [None for _ in date_axis],
            "daily_pnl": [None for _ in date_axis],
            "trade_count": [0 for _ in date_axis],
        }

    assets_df = assets_df.sort("dt")
    total_by_date = {
        arrow.get(row["dt"]).format("YYYY-MM-DD"): row["total"]
        for row in assets_df.iter_rows(named=True)
    }
    last_date = max(total_by_date) if total_by_date else None

    trade_count_by_date = _trade_counts_by_date(portfolio_id)

    total_series: list[float | None] = []
    daily_pnl_series: list[float | None] = []
    trade_count_series = []
    prev_total = None
    for dt in date_axis:
        prev_total = _append_equity_after_history(
            daily_pnl_series, dt, last_date, prev_total, total_by_date, total_series
        )
        trade_count_series.append(trade_count_by_date.get(dt, 0))

    benchmark_series: list[float | None] = [None for _ in date_axis]
    try:
        start_date = arrow.get(date_axis[0]).date()
        end_date = arrow.get(date_axis[-1]).date()
        benchmark_df = daily_bars.get_bars_in_range(
            start_date,
            end_date,
            assets=[BENCHMARK_ASSET],
            eager_mode=True,
        )
    except Exception:
        benchmark_df = pl.DataFrame()

    benchmark_series = _append_benchmark_series(
        benchmark_df, total_series, date_axis, benchmark_series
    )

    return {
        "date_axis": date_axis,
        "total": total_series,
        "benchmark": benchmark_series,
        "daily_pnl": daily_pnl_series,
        "trade_count": trade_count_series,
    }


def _build_benchmark_returns(portfolio_id: str) -> pl.DataFrame | None:
    """构建用于绩效指标计算的基准收益序列。

    Args:
        portfolio_id: 组合 ID。

    Returns:
        pl.DataFrame | None: 包含 ``dt`` 与 ``returns`` 列的基准收益率序列；
        若无法构建，则返回 ``None``。
    """
    assets_df = db.query_assets(portfolio_id)
    if assets_df.is_empty():
        return None

    assets_df = assets_df.sort("dt")
    start_date = assets_df.row(0, named=True)["dt"]
    end_date = assets_df.row(-1, named=True)["dt"]

    try:
        benchmark_df = daily_bars.get_bars_in_range(
            start_date,
            end_date,
            assets=[BENCHMARK_ASSET],
            eager_mode=True,
        )
    except Exception:
        return None

    if benchmark_df.is_empty():
        return None

    returns_df = (
        benchmark_df.sort("date")
        .select([pl.col("date").cast(pl.Date).alias("dt"), pl.col("close")])
        .with_columns(pl.col("close").pct_change().alias("returns"))
        .drop_nulls("returns")
        .select(["dt", "returns"])
    )
    return returns_df if not returns_df.is_empty() else None


METRIC_ALIASES = {
    "annual_return": ("annual_return", "cagr"),
    "total_returns": ("cumulative_return", "total_return", "total_returns"),
    "max_drawdown": ("max_drawdown",),
    "sharpe": ("sharpe_ratio", "sharpe"),
    "volatility": ("volatility_ann", "volatility"),
    "sortino": ("sortino_ratio", "sortino"),
    "calmar": ("calmar_ratio", "calmar"),
    "win_rate": ("win_rate_daily", "win_rate"),
    "profit_factor": ("profit_factor",),
    "alpha": ("alpha_ann", "alpha"),
    "beta": ("beta",),
    "payoff_ratio": ("payoff_ratio",),
    "avg_return": ("avg_return", "average_return"),
    "avg_win": ("avg_win", "average_win"),
    "avg_loss": ("avg_loss", "average_loss"),
    "best_day": ("best_day",),
    "worst_day": ("worst_day",),
    "tail_ratio": ("tail_ratio",),
    "skew": ("skewness", "skew"),
    "kurtosis": ("kurtosis",),
    "value_at_risk": ("daily_value_at_risk", "value_at_risk"),
    "information_ratio": ("information_ratio",),
}


def _build_metrics_payload(portfolio_id: str) -> dict[str, Any]:
    """构建指标数据。

    Args:
        portfolio_id: 组合 ID

    Returns:
        dict: 指标键值对
    """
    stats = metrics(portfolio_id, baseline_returns=_build_benchmark_returns(portfolio_id))
    stats_dict = _normalize_stats(stats)
    return {key: _metric_value(stats_dict, *aliases) for key, aliases in METRIC_ALIASES.items()}


def _is_stale_backtest_run(portfolio_id: str, portfolio: object | None) -> bool:
    """判断"运行中"是否已失效。

    回测总是跑在本进程内，进程内没有运行记录时不可能还在运行；若组合的
    资产快照还没到回测结束日，说明这次运行没跑完（进程重启或异常中断）。

    Args:
        portfolio_id: 回测组合 ID。
        portfolio: 回测组合记录。

    Returns:
        bool: 状态是否已失效。
    """
    end = getattr(portfolio, "end", None)
    if not isinstance(end, datetime.date):
        return False
    try:
        assets = db.query_assets(portfolio_id=portfolio_id)
    except Exception:
        return False
    if assets is None or assets.is_empty():
        return True
    last = assets["dt"].max()
    return isinstance(last, datetime.date) and last < end


def _resolve_backtest_status(portfolio_id: str) -> tuple[str, str]:
    """解析回测运行状态与错误信息。

    Args:
        portfolio_id: 回测组合 ID。

    Returns:
        tuple[str, str]: ``(status, error)``，状态可能为 ``running``、``finished``、
        ``failed`` 或 ``missing``。
    """
    run = strategy_runtime_manager.get_backtest_run(portfolio_id)
    if run is not None:
        status = str(run.status or "").strip().lower()
        if status in {"running", "finished", "failed"}:
            return status, str(run.error or "")

    portfolio = db.get_portfolio(portfolio_id)
    if portfolio is None:
        return "missing", "未找到回测记录。"
    if portfolio.status and _is_stale_backtest_run(portfolio_id, portfolio):
        # 进程内没有运行记录、且能证明这次运行没跑到结束日：进程重启或异常中断
        # 留下的悬挂状态。修好状态并允许删除。
        try:
            db.update_portfolio(portfolio_id, status=False)
        except Exception:
            pass
        return "failed", "回测异常中断，未正常结束（可删除该记录）"
    return ("running" if portfolio.status else "finished"), ""


def _build_trade_rows(portfolio_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """构建交易明细行。

    Args:
        portfolio_id: 组合 ID
        limit: 最大行数

    Returns:
        list[dict]: 交易明细
    """
    trades_df = db.trades_all(portfolio_id)
    if trades_df.is_empty():
        return []
    trades_df = trades_df.sort("tm", descending=True).head(limit)
    rows = []
    for row in trades_df.iter_rows(named=True):
        side = row.get("side")
        if isinstance(side, OrderSide):
            side_text = str(side)
            side_value = side.value
        else:
            side_value = int(side) if side is not None else 0
            side_text = "买入" if side_value == OrderSide.BUY else "卖出"
        rows.append(
            {
                "tid": str(row.get("tid", "")),
                "tm": str(row.get("tm", "")),
                "asset": row.get("asset", ""),
                "side": side_text,
                "side_value": side_value,
                "price": float(row.get("price") or 0),
                "shares": float(row.get("shares") or 0),
                "amount": float(row.get("amount") or 0),
                "fee": float(row.get("fee") or 0),
            }
        )
    return rows


def _build_daily_positions(portfolio_id: str) -> list[dict[str, Any]]:
    """构建每日持仓明细。

    Args:
        portfolio_id: 组合 ID

    Returns:
        list[dict]: 持仓明细
    """
    positions_df = db.positions_all(portfolio_id)
    if positions_df.is_empty():
        return []
    positions_df = positions_df.sort(["dt", "asset"])
    rows = []
    for row in positions_df.iter_rows(named=True):
        rows.append(
            {
                "dt": str(row.get("dt", "")),
                "asset": row.get("asset", ""),
                "shares": float(row.get("shares") or 0),
                "avail": float(row.get("avail") or 0),
                "price": float(row.get("price") or 0),
                "mv": float(row.get("mv") or 0),
                "profit": float(row.get("profit") or 0),
            }
        )
    return rows


def _build_daily_summary(portfolio_id: str) -> list[dict[str, Any]]:
    """构建每日收益概览。

    Args:
        portfolio_id: 组合 ID

    Returns:
        list[dict]: 每日收益概览
    """
    assets_df = db.query_assets(portfolio_id)
    if assets_df.is_empty():
        return []
    assets_df = assets_df.sort("dt")
    rows = []
    prev_total = None
    for row in assets_df.iter_rows(named=True):
        total = float(row.get("total") or 0)
        daily_pnl = 0.0 if prev_total is None else total - prev_total
        daily_return = 0.0 if prev_total is None or prev_total == 0 else daily_pnl / prev_total
        rows.append(
            {
                "dt": str(row.get("dt", "")),
                "cash": float(row.get("cash") or 0),
                "market_value": float(row.get("market_value") or 0),
                "total": total,
                "daily_pnl": daily_pnl,
                "daily_return": daily_return,
            }
        )
        prev_total = total
    return rows


def _trade_counts_by_date(portfolio_id: str) -> dict[str, int]:
    """Count committed fills by date for the report timeline."""
    trade_count_by_date: dict[str, int] = {}
    trades_df = db.trades_all(portfolio_id)
    if not trades_df.is_empty():
        for row in trades_df.iter_rows(named=True):
            tm = row.get("tm")
            if tm is None:
                continue
            dt = arrow.get(tm).format("YYYY-MM-DD")
            trade_count_by_date[dt] = trade_count_by_date.get(dt, 0) + 1
    return trade_count_by_date
