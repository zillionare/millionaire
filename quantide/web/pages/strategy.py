import asyncio
import datetime
import json
import uuid
from pathlib import Path as FilePath
from typing import Any

import arrow
import fasthtml.common as fh
import polars as pl
from fasthtml.common import *
from fasthtml.svg import Path as SvgPath
from loguru import logger
from monsterui.all import *
from starlette.websockets import WebSocket, WebSocketDisconnect

from quantide.core.enums import BrokerKind, FrameType, OrderSide
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.backtest_logs import (
    delete_saved_backtest_log,
    list_backtest_logs,
    load_saved_backtest_logs,
    saved_backtest_log_exists,
    saved_backtest_log_path,
)
from quantide.service.discovery import strategy_loader
from quantide.service.grid_search import GridSearch
from quantide.service.metrics import metrics
from quantide.service.runner import BacktestRunner
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.layouts.main import MainLayout
from quantide.web.theme import AppTheme

strategy_app, rt = fast_app()

BENCHMARK_ASSET = "000300.SH"
BACKTEST_REPORT_TABS = {
    "overview": "收益概述",
    "trades": "交易详情",
    "positions": "每日持仓",
    "logs": "日志输出",
}
STRATEGY_MODAL_CLOSE_JS = "closeStrategyModal()"


def _strategy_modal_script() -> Any:
    """提供策略页面共用的弹窗打开与关闭脚本。"""
    return Script(
        r"""
        (function () {
            function modalContainer() {
                return document.getElementById('modal-container');
            }

            function modalElement(root) {
                if (!root) {
                    return null;
                }
                return root.querySelector('[data-uk-modal], .uk-modal');
            }

            function modalApi(element) {
                if (!element || !window.UIkit || typeof window.UIkit.modal !== 'function') {
                    return null;
                }
                return window.UIkit.modal(element);
            }

            function hideCurrentModal() {
                var container = modalContainer();
                var element = modalElement(container);
                var api = modalApi(element);
                if (api) {
                    api.hide();
                }
            }

            function clearModalContainer() {
                var container = modalContainer();
                if (!container) {
                    return;
                }
                hideCurrentModal();
                container.innerHTML = '';
            }

            function showInsertedModal(root) {
                var api = modalApi(modalElement(root));
                if (api) {
                    api.show();
                }
            }

            window.closeStrategyModal = clearModalContainer;

            document.body.addEventListener('htmx:beforeSwap', function (event) {
                if (event.target && event.target.id === 'modal-container') {
                    hideCurrentModal();
                }
            });

            document.body.addEventListener('htmx:afterSwap', function (event) {
                if (event.target && event.target.id === 'modal-container') {
                    showInsertedModal(event.target);
                }
            });
        })();
        """
    )


def _strategy_dialog_modal(
    title: str,
    body: Any,
    footer: Any,
    *,
    modal_id: str,
    width_cls: str = "max-w-lg",
) -> Any:
    """渲染策略页面统一风格的对话框。"""
    return Div(
        Div(cls="fixed inset-0 bg-black/50 transition-opacity"),
        Div(
            Div(
                Div(
                    Div(
                        H3(title, cls="text-lg font-medium leading-6 text-gray-900"),
                        cls="px-6 py-5 border-b border-gray-200",
                    ),
                    Div(body, cls="px-6 py-5"),
                    Div(footer, cls="px-6 py-4 border-t border-gray-100"),
                    cls=f"inline-block w-full {width_cls} overflow-hidden rounded-lg bg-white text-left align-middle shadow-xl",
                ),
                cls="flex min-h-full items-center justify-center p-4 text-center",
            ),
            cls="fixed inset-0 z-10 overflow-y-auto",
        ),
        id=modal_id,
    )

def _normalize_stats(stats):
    """规范化 quantstats 指标名称并返回字典。

    Args:
        stats: quantstats 输出的指标表

    Returns:
        dict: 指标键值对，键为下划线风格
    """
    if stats is None or stats.empty:
        return {}
    series = stats.iloc[:, 0]
    index = series.index.astype(str)
    normalized = (
        index.str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    series.index = normalized
    return series.to_dict()


def _to_number(value) -> float | None:
    """将指标值转换为 float。

    Args:
        value: 指标值

    Returns:
        float | None: 数值化结果。百分比字符串会被转换为小数。
    """
    is_percent = False
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned == "" or cleaned.lower() in {"nan", "n/a", "na"}:
            return None
        is_percent = cleaned.endswith("%")
        if is_percent:
            cleaned = cleaned[:-1].strip()
        value = cleaned
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number / 100 if is_percent else number


def _metric_value(stats_dict: dict[str, Any], *keys: str) -> float | None:
    """解析首个存在的指标值。

    Args:
        stats_dict: 规范化后的指标字典。
        *keys: 候选指标键名，按优先级顺序查找。

    Returns:
        解析后的数值；若所有键都不存在或无法解析，则返回 ``None``。
    """
    for key in keys:
        if key not in stats_dict:
            continue
        value = _to_number(stats_dict[key])
        if value is not None:
            return value
    return None


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


def _build_series_payload(portfolio_id: str, date_axis: list[str]) -> dict:
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
    asset_rows = assets_df.iter_rows(named=True)
    total_by_date = {}
    last_date = None
    totals = []
    for row in asset_rows:
        dt = arrow.get(row["dt"]).format("YYYY-MM-DD")
        total_by_date[dt] = row["total"]
        last_date = dt
        totals.append(row["total"])

    trade_count_by_date: dict[str, int] = {}
    trades_df = db.trades_all(portfolio_id)
    if not trades_df.is_empty():
        for row in trades_df.iter_rows(named=True):
            tm = row.get("tm")
            if tm is None:
                continue
            dt = arrow.get(tm).format("YYYY-MM-DD")
            trade_count_by_date[dt] = trade_count_by_date.get(dt, 0) + 1

    total_series = []
    daily_pnl_series = []
    trade_count_series = []
    prev_total = None
    for dt in date_axis:
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
        trade_count_series.append(trade_count_by_date.get(dt, 0))

    benchmark_series = [None for _ in date_axis]
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


def _build_metrics_payload(portfolio_id: str) -> dict:
    """构建指标数据。

    Args:
        portfolio_id: 组合 ID

    Returns:
        dict: 指标键值对
    """
    stats = metrics(portfolio_id, baseline_returns=_build_benchmark_returns(portfolio_id))
    stats_dict = _normalize_stats(stats)
    annual_return = _metric_value(stats_dict, "annual_return", "cagr")
    sharpe = _metric_value(stats_dict, "sharpe_ratio", "sharpe")
    max_drawdown = _metric_value(stats_dict, "max_drawdown")
    total_returns = _metric_value(
        stats_dict,
        "cumulative_return",
        "total_return",
        "total_returns",
    )
    volatility = _metric_value(stats_dict, "volatility_ann", "volatility")
    sortino = _metric_value(stats_dict, "sortino_ratio", "sortino")
    calmar = _metric_value(stats_dict, "calmar_ratio", "calmar")
    win_rate = _metric_value(stats_dict, "win_rate_daily", "win_rate")
    profit_factor = _metric_value(stats_dict, "profit_factor")
    alpha = _metric_value(stats_dict, "alpha_ann", "alpha")
    beta = _metric_value(stats_dict, "beta")
    payoff_ratio = _metric_value(stats_dict, "payoff_ratio")
    avg_return = _metric_value(stats_dict, "avg_return", "average_return")
    avg_win = _metric_value(stats_dict, "avg_win", "average_win")
    avg_loss = _metric_value(stats_dict, "avg_loss", "average_loss")
    best_day = _metric_value(stats_dict, "best_day")
    worst_day = _metric_value(stats_dict, "worst_day")
    tail_ratio = _metric_value(stats_dict, "tail_ratio")
    skew = _metric_value(stats_dict, "skewness", "skew")
    kurtosis = _metric_value(stats_dict, "kurtosis")
    value_at_risk = _metric_value(
        stats_dict,
        "daily_value_at_risk",
        "value_at_risk",
    )
    information_ratio = _metric_value(stats_dict, "information_ratio")
    return {
        "annual_return": annual_return,
        "total_returns": total_returns,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "volatility": volatility,
        "sortino": sortino,
        "calmar": calmar,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "alpha": alpha,
        "beta": beta,
        "payoff_ratio": payoff_ratio,
        "avg_return": avg_return,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "best_day": best_day,
        "worst_day": worst_day,
        "tail_ratio": tail_ratio,
        "skew": skew,
        "kurtosis": kurtosis,
        "value_at_risk": value_at_risk,
        "information_ratio": information_ratio,
    }


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
    return ("running" if portfolio.status else "finished"), ""


def _build_trade_rows(portfolio_id: str, limit: int = 200) -> list[dict]:
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


def _build_daily_positions(portfolio_id: str) -> list[dict]:
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


def _build_daily_summary(portfolio_id: str) -> list[dict]:
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
        daily_return = 0.0 if prev_total in (None, 0) else daily_pnl / prev_total
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


def _build_log_rows(portfolio_id: str, limit: int = 200) -> list[dict]:
    """构建日志行。

    Args:
        portfolio_id: 组合 ID
        limit: 最大行数

    Returns:
        list[dict]: 日志行
    """
    return list_backtest_logs(portfolio_id, limit=limit)


def _parse_checkbox(value: Any) -> bool:
    """解析 checkbox/form 布尔值。"""
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def _normalize_backtest_tab(value: Any) -> str:
    """规范化回测报告标签。"""
    key = str(value or "overview").strip().lower()
    if key not in BACKTEST_REPORT_TABS:
        return "overview"
    return key


def _build_backtest_sidebar_menu(
    portfolio_id: str,
    active_tab: str,
) -> list[dict[str, Any]]:
    """构建回测报告侧边栏。"""
    children = []
    for tab, title in BACKTEST_REPORT_TABS.items():
        children.append(
            {
                "title": title,
                "url": f"/strategy/backtest/{portfolio_id}?tab={tab}",
                "active": tab == active_tab,
            }
        )

    return [
        {
            "title": "策略列表",
            "url": "/strategy",
            "icon_path": "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
        },
        {
            "title": "回测报告",
            "url": f"/strategy/backtest/{portfolio_id}",
            "icon_path": "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
            "active": True,
            "children": children,
        },
    ]


def _build_log_meta(portfolio_id: str) -> dict[str, Any]:
    """构建回测日志状态元数据。"""
    saved_path = saved_backtest_log_path(portfolio_id)
    run = strategy_runtime_manager.get_backtest_run(portfolio_id)
    return {
        "save_requested": bool(getattr(run, "save_logs", False)),
        "saved": saved_backtest_log_exists(portfolio_id),
        "saved_path": str(saved_path),
    }


def _format_log_lines(rows: list[dict[str, Any]]) -> list[str]:
    """格式化回测日志展示文本。"""
    lines: list[str] = []
    for row in rows:
        base = (
            f"{row.get('dt', '')} | {row.get('level', 'INFO')} | "
            f"{row.get('source', 'system')} | {row.get('message', '')}"
        )
        extra = str(row.get("extra") or "").strip()
        lines.append(f"{base} | {extra}" if extra else base)
    return lines


def _build_log_panel(
    portfolio_id: str,
    status: str,
    rows: list[dict[str, Any]] | None = None,
    source_label: str = "实时日志",
    error_text: str = "",
) -> Any:
    """构建回测日志面板。"""
    log_rows = rows if rows is not None else _build_log_rows(portfolio_id, limit=200)
    meta = _build_log_meta(portfolio_id)
    log_lines = _format_log_lines(log_rows)
    save_status_text = "本次回测未启用文件保存"
    save_status_cls = "text-xs text-gray-500"
    if meta["save_requested"] and meta["saved"]:
        save_status_text = "已保存到文件，可重复加载"
        save_status_cls = "text-xs text-green-600"
    elif meta["save_requested"]:
        save_status_text = "已启用文件保存，日志生成后会写入本地文件"
        save_status_cls = "text-xs text-amber-600"

    load_button = (
        Button(
            "加载已保存日志",
            cls="btn btn-secondary btn-sm",
            type="button",
            hx_get=f"/strategy/backtest/{portfolio_id}/logs/saved",
            hx_target="#backtest-log-panel",
            hx_swap="outerHTML",
        )
        if meta["saved"]
        else Button(
            "暂无已保存日志",
            cls="btn btn-secondary btn-sm opacity-60 cursor-not-allowed",
            type="button",
            disabled=True,
        )
    )

    return Div(
        Div(
            Div(
                H3("日志输出", cls="text-xl font-bold"),
                P(
                    "运行中自动刷新；保存日志后可从文件重复加载。",
                    cls="text-sm text-gray-500 mt-1",
                ),
            ),
            Div(
                Span(
                    f"当前来源：{source_label}",
                    id="log_source_badge",
                    cls="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600",
                ),
                load_button,
                cls="flex flex-wrap items-center gap-2",
            ),
            cls="flex flex-col gap-3 md:flex-row md:items-start md:justify-between",
        ),
        Div(
            P(
                "回测进行中，日志会自动刷新。"
                if status == "running"
                else "回测已结束，可查看已采集日志。",
                cls="text-xs text-gray-500",
            ),
            P(
                save_status_text,
                id="log_save_status",
                cls=save_status_cls,
            ),
            P(
                meta["saved_path"],
                id="log_save_path",
                cls="text-xs text-gray-400 break-all",
            ),
            cls="space-y-1 mt-4",
        ),
        (
            Div(
                error_text,
                id="log_panel_error",
                cls="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600",
            )
            if error_text
            else Div(id="log_panel_error", cls="hidden")
        ),
        Pre(
            "\n".join(log_lines) if log_lines else "暂无回测日志",
            id="log_output",
            cls="mt-4 max-h-[560px] overflow-auto rounded-lg bg-gray-950 p-4 text-xs text-gray-100 whitespace-pre-wrap",
        ),
        id="backtest-log-panel",
        cls="bg-white p-6 rounded-lg shadow-sm border border-gray-100 mt-6",
    )


def _format_date(value) -> str:
    """格式化日期。

    Args:
        value: 日期值

    Returns:
        str: 格式化后的日期文本
    """
    if value is None:
        return "--"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _format_range(start, end) -> str:
    """格式化回测区间。

    Args:
        start: 开始日期
        end: 结束日期

    Returns:
        str: 回测区间文本
    """
    if start is None and end is None:
        return "--"
    return f"{_format_date(start)} ~ {_format_date(end)}"


def _format_percent(value) -> str:
    """格式化百分比值。

    Args:
        value: 百分比数值

    Returns:
        str: 百分比文本
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    return f"{number * 100:.1f}%"


def _format_number(value) -> str:
    """格式化数值。

    Args:
        value: 数值

    Returns:
        str: 格式化后的数字文本
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    return f"{number:.2f}"


def _params_to_text(params: dict) -> str:
    """格式化参数显示文本。

    Args:
        params: 参数字典

    Returns:
        str: 参数文本
    """
    if not params:
        return "--"
    items = []
    for key, value in params.items():
        text_value = value
        if isinstance(value, dict):
            text_value = value.get("default", "")
        items.append(f"{key}={text_value}")
    return ", ".join(items) if items else "--"


def _extract_params_from_info(info) -> dict:
    """从回测信息中提取参数。

    Args:
        info: 组合信息字段

    Returns:
        dict: 参数字典
    """
    if not info:
        return {}
    if isinstance(info, dict):
        return info
    if isinstance(info, str):
        try:
            payload = json.loads(info)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            config = payload.get("config")
            if isinstance(config, dict):
                return config
            return payload
    return {}


def _strategy_version(strategy_cls) -> str:
    """获取策略版本。

    Args:
        strategy_cls: 策略类

    Returns:
        str: 版本文本
    """
    if strategy_cls is None:
        return "v1.0.0"
    return getattr(strategy_cls, "VERSION", getattr(strategy_cls, "__version__", "v1.0.0"))


def _build_backtest_name_cell(name: str, portfolio_id: str) -> Any:
    """构建回测报告列表中的策略名单元格。"""
    return Td(
        A(
            name,
            href=f"/strategy/backtest/{portfolio_id}",
            cls="text-blue-600 font-medium hover:underline",
        ),
        cls="text-gray-900",
    )


def _build_backtest_deploy_button(
    label: str,
    modal_path: str,
    *,
    is_available: bool,
    unavailable_reason: str,
) -> Any:
    """构建回测报告列表中的投放按钮。"""
    button_cls = "btn btn-secondary btn-sm"
    if is_available:
        return Button(
            label,
            cls=button_cls,
            type="button",
            hx_get=modal_path,
            hx_target="#modal-container",
        )
    return Span(
        Button(
            label,
            cls=f"{button_cls} opacity-50 cursor-not-allowed pointer-events-none",
            type="button",
            disabled=True,
        ),
        title=unavailable_reason,
        cls="inline-flex",
    )


def _build_backtest_action_cell(
    portfolio_id: str,
    deployment_modes: dict[str, dict[str, Any]] | None = None,
    *,
    paper_available: bool = True,
    paper_unavailable_reason: str = "",
    live_available: bool = True,
    live_unavailable_reason: str = "",
    hx_swap_oob: bool = False,
) -> Any:
    """构建回测报告列表操作列。"""
    deployment_modes = deployment_modes or strategy_runtime_manager.backtest_deployment_modes(portfolio_id)
    controls: list[Any] = []

    if "paper" in deployment_modes:
        controls.append(
            Span(
                "仿真中",
                cls="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-600",
            )
        )
    else:
        controls.append(
            _build_backtest_deploy_button(
                "转仿真",
                f"/strategy/backtest/{portfolio_id}/deploy/paper/modal",
                is_available=paper_available,
                unavailable_reason=paper_unavailable_reason,
            )
        )

    if "live" in deployment_modes:
        controls.append(
            Span(
                "实盘中",
                cls="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-600",
            )
        )
    else:
        controls.append(
            _build_backtest_deploy_button(
                "转实盘",
                f"/strategy/backtest/{portfolio_id}/deploy/live/modal",
                is_available=live_available,
                unavailable_reason=live_unavailable_reason,
            )
        )

    controls.append(
        Button(
            UkIcon("trash-2", size=14),
            title="删除回测",
            hx_get=f"/strategy/backtest/{portfolio_id}/delete/modal",
            hx_target="#modal-container",
            cls="w-8 h-8 flex items-center justify-center bg-transparent border-0 shadow-none p-0 text-red-500 hover:text-red-700",
            type="button",
        )
    )

    attrs: dict[str, Any] = {"id": f"backtest-actions-{portfolio_id}"}
    if hx_swap_oob:
        attrs["hx_swap_oob"] = "true"

    return Td(Div(*controls, cls="flex flex-wrap items-center gap-2"), **attrs)


def _build_strategy_rows(strategies: dict) -> list:
    """构建策略列表行。

    Args:
        strategies: 策略字典

    Returns:
        list: 行数据
    """
    rows = []
    for name, cls in strategies.items():
        doc = cls.__doc__ or "暂无描述"
        version = _strategy_version(cls)
        portfolios = db.get_portfolios_by_strategy(name)
        history_count = portfolios.height if hasattr(portfolios, "height") else 0
        latest_link = None
        latest_date = "--"
        if not portfolios.is_empty():
            portfolios = portfolios.sort("start", descending=True)
            latest_row = portfolios.row(0, named=True)
            latest_date = _format_date(latest_row.get("end") or latest_row.get("start"))
            latest_link = latest_row.get("portfolio_id")

        latest_cell = (
            A(latest_date, href=f"/strategy/backtest/{latest_link}", cls="text-blue-600 hover:underline")
            if latest_link
            else Span("--", cls="text-gray-400")
        )

        rows.append(
            Tr(
                Td(
                    Button(
                        UkIcon("play", size=16, cls="text-blue-600"),
                        title="重新运行回测",
                        hx_get=f"/strategy/{name}/backtest/modal",
                        hx_target="#modal-container",
                        cls="w-8 h-8 flex items-center justify-center bg-transparent border-0 shadow-none p-0 hover:text-blue-800",
                        type="button",
                    )
                ),
                Td(name, cls="text-gray-900 font-medium"),
                Td(doc, cls="text-gray-600"),
                Td(version, cls="text-gray-900"),
                Td(f"{history_count}次", cls="text-gray-900"),
                Td(latest_cell),
                cls="border-b border-gray-200 hover:bg-gray-50",
            )
        )
    return rows


def _build_backtest_rows(
    strategies: dict,
    *,
    paper_available: bool = True,
    paper_unavailable_reason: str = "",
    live_available: bool = True,
    live_unavailable_reason: str = "",
) -> list:
    """构建回测报告列表行。

    Args:
        strategies: 策略字典
        paper_available: 是否允许转入仿真。
        paper_unavailable_reason: 仿真不可用原因。
        live_available: 是否允许转入实盘。
        live_unavailable_reason: 实盘不可用原因。

    Returns:
        list: 行数据
    """
    rows = []
    portfolios = db.portfolios_all()
    if portfolios.is_empty():
        return rows
    if "start" in portfolios.columns:
        portfolios = portfolios.sort("start", descending=True)
    for row in portfolios.iter_rows(named=True):
        kind = row.get("kind")
        if isinstance(kind, str):
            try:
                kind = BrokerKind(kind)
            except ValueError:
                continue
        if kind != BrokerKind.BACKTEST:
            continue
        portfolio_id = row.get("portfolio_id")
        name = row.get("name") or "--"
        strategy_cls = strategies.get(name)
        version = _strategy_version(strategy_cls)
        info_params = _extract_params_from_info(row.get("info"))
        if not info_params and strategy_cls:
            info_params = getattr(strategy_cls, "PARAMS", {})
        params_text = _params_to_text(info_params)
        range_text = _format_range(row.get("start"), row.get("end"))
        deployment_modes = strategy_runtime_manager.backtest_deployment_modes(portfolio_id)
        metrics_payload = _build_metrics_payload(portfolio_id)
        annual_return = metrics_payload.get("annual_return")
        sharpe = metrics_payload.get("sharpe")
        max_drawdown = metrics_payload.get("max_drawdown")
        sortino = metrics_payload.get("sortino")
        annual_cls = (
            "text-gray-900"
            if annual_return is None
            else ("text-green-600" if annual_return >= 0 else "text-red-600")
        )
        drawdown_cls = (
            "text-gray-900"
            if max_drawdown is None
            else ("text-red-600" if max_drawdown < 0 else "text-gray-900")
        )

        rows.append(
            Tr(
                _build_backtest_name_cell(name, portfolio_id),
                Td(version, cls="text-gray-600"),
                Td(params_text, cls="text-gray-600"),
                Td(range_text, cls="text-gray-600"),
                Td(_format_percent(annual_return), cls=f"{annual_cls} font-medium"),
                Td(_format_number(sharpe), cls="text-gray-900"),
                Td(_format_percent(max_drawdown), cls=drawdown_cls),
                Td(_format_number(sortino), cls="text-gray-900"),
                _build_backtest_action_cell(
                    portfolio_id,
                    deployment_modes,
                    paper_available=paper_available,
                    paper_unavailable_reason=paper_unavailable_reason,
                    live_available=live_available,
                    live_unavailable_reason=live_unavailable_reason,
                ),
                cls="border-b border-gray-200 hover:bg-gray-50",
            )
        )
    return rows


@rt("/")
def index(req, session):
    layout = MainLayout(title="策略列表", user=session.get("auth"))
    layout.header_active = "策略"
    layout.sidebar_menu = [
        {
            "title": "策略列表",
            "url": "/strategy",
            "icon_path": "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
            "active": True,
        },
        {
            "title": "回测报告",
            "url": "/strategy#backtest-list",
            "icon_path": "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
        },
    ]

    # 从缓存加载策略（不再每次扫描）
    strategies = strategy_loader.load_from_cache()
    strategy_rows = _build_strategy_rows(strategies)
    backtest_rows = _build_backtest_rows(strategies, **_get_backtest_deploy_capabilities(req))

    strategy_table = Table(
        Thead(
            Tr(
                Th("操作", cls="px-6 py-3 font-medium w-20"),
                Th("名称", cls="px-6 py-3 font-medium"),
                Th("简介", cls="px-6 py-3 font-medium"),
                Th("版本", cls="px-6 py-3 font-medium"),
                Th("历史回测", cls="px-6 py-3 font-medium"),
                Th("最新回测", cls="px-6 py-3 font-medium"),
                cls="text-left text-sm text-gray-600 border-b border-gray-200",
            )
        ),
        Tbody(*strategy_rows, cls="text-sm"),
        cls="w-full",
    )

    backtest_table = Table(
        Thead(
            Tr(
                Th("策略名", cls="px-6 py-3 font-medium"),
                Th("版本", cls="px-6 py-3 font-medium"),
                Th("参数", cls="px-6 py-3 font-medium"),
                Th("回测区间", cls="px-6 py-3 font-medium"),
                Th("年化收益", cls="px-6 py-3 font-medium"),
                Th("夏普", cls="px-6 py-3 font-medium"),
                Th("最大回撤", cls="px-6 py-3 font-medium"),
                Th("索提诺", cls="px-6 py-3 font-medium"),
                Th("操作", cls="px-6 py-3 font-medium"),
                cls="text-left text-sm text-gray-600 border-b border-gray-200",
            )
        ),
        Tbody(*backtest_rows, cls="text-sm"),
        cls="w-full",
    )

    section_toggle_script = Script(
        r"""
        (function () {
            function setSidebarItemState(element, isActive) {
                if (!element) {
                    return;
                }
                element.classList.toggle('bg-[#fcfcfc]', isActive);
                element.classList.toggle('text-[#e41815]', isActive);
                element.classList.toggle('font-medium', isActive);
                element.classList.toggle('text-[#2c3030]', !isActive);
                element.classList.toggle('hover:bg-[#fcfcfc]', !isActive);
            }

            function normalizePath(path) {
                if (!path) {
                    return '/';
                }
                return path.length > 1 ? path.replace(/\/$/, '') : path;
            }

            function findSidebarLink(expectedPath, expectedHash, expectedLabel) {
                var links = document.querySelectorAll('aside a');
                for (var i = 0; i < links.length; i++) {
                    var link = links[i];
                    var href = link.getAttribute('href') || '';
                    var url = new URL(href, window.location.origin);
                    var label = (link.textContent || '').trim();
                    if (
                        normalizePath(url.pathname) === expectedPath
                        && url.hash === expectedHash
                    ) {
                        return link;
                    }
                    if (label === expectedLabel) {
                        return link;
                    }
                }
                return null;
            }

            function toggleStrategySections() {
                var strategySection = document.getElementById('strategy-list-section');
                var backtestSection = document.getElementById('backtest-list');
                if (!strategySection || !backtestSection) {
                    return;
                }
                var showBacktestOnly = window.location.hash === '#backtest-list';
                var strategyMenuLink = findSidebarLink('/strategy', '', '策略列表');
                var backtestMenuLink = findSidebarLink('/strategy', '#backtest-list', '回测报告');
                strategySection.classList.toggle('hidden', showBacktestOnly);
                backtestSection.classList.toggle('mt-0', showBacktestOnly);
                setSidebarItemState(strategyMenuLink, !showBacktestOnly);
                setSidebarItemState(backtestMenuLink, showBacktestOnly);
            }

            function handleSidebarToggleClick(event) {
                var link = event.target.closest('aside a');
                if (!link) {
                    return;
                }
                var url = new URL(link.href, window.location.origin);
                if (normalizePath(url.pathname) !== '/strategy') {
                    return;
                }
                var nextHash = url.hash || '';
                if (nextHash !== '' && nextHash !== '#backtest-list') {
                    return;
                }
                event.preventDefault();
                var nextUrl = url.pathname + url.search + nextHash;
                if (window.location.pathname + window.location.search + window.location.hash == nextUrl) {
                    toggleStrategySections();
                    return;
                }
                if (nextHash === window.location.hash) {
                    window.history.replaceState(null, '', nextUrl);
                } else {
                    window.history.pushState(null, '', nextUrl);
                }
                toggleStrategySections();
            }

            window.addEventListener('hashchange', toggleStrategySections);
            window.addEventListener('load', toggleStrategySections);
            window.addEventListener('pageshow', toggleStrategySections);
            document.addEventListener('click', handleSidebarToggleClick);
            toggleStrategySections();
        })();
        """
    )

    layout.main_block = lambda: Div(
        Div(
            Nav(
                A("首页", href="/", cls="hover:text-blue-600"),
                Span(">", cls="text-gray-400"),
                A("策略", href="/strategy", cls="hover:text-blue-600"),
                Span(">", cls="text-gray-400"),
                Span("策略列表", cls="text-gray-900 font-medium"),
                cls="flex items-center space-x-2 text-sm text-gray-600",
            ),
            cls="mb-4",
        ),
        Div(
            Div(
                Div(
                    H2("策略列表", cls="text-lg font-semibold text-gray-900"),
                    P(
                        "内置示例已默认参与扫描；如需复制到自己的策略目录，请点击“复制示例策略”。",
                        cls="mt-1 text-sm text-gray-500",
                    ),
                ),
                _strategy_scan_toolbar(),
                cls="p-6 border-b border-gray-200 flex justify-between items-center",
            ),
            Div(strategy_table, cls="overflow-x-auto"),
            cls="bg-white rounded-lg shadow mb-6",
            id="strategy-list-section",
        ),
        Div(
            Div(
                Div(
                    H2("回测报告列表", cls="text-lg font-semibold text-gray-900"),
                    Div(id="deploy-result", cls="mt-2 text-sm"),
                    cls="flex flex-col items-start",
                ),
                Div(
                    Div(
                        Input(
                            type="text",
                            placeholder="按策略名过滤...",
                            cls="pl-10 pr-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                        ),
                         Svg(
                             SvgPath(
                                 d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
                                **{
                                    "stroke-linecap": "round",
                                    "stroke-linejoin": "round",
                                    "stroke-width": "2",
                                },
                            ),
                            cls="w-5 h-5 text-gray-400 absolute left-3 top-2.5",
                            fill="none",
                            stroke="currentColor",
                            viewBox="0 0 24 24",
                        ),
                        cls="relative",
                    ),
                    fh.Select(
                        fh.Option("按年化收益排序", value="annual", selected=True),
                        fh.Option("按夏普比率排序", value="sharpe"),
                        fh.Option("按最大回撤排序", value="drawdown"),
                        fh.Option("按索提诺排序", value="sortino"),
                        cls="uk-select uk-form-small text-gray-900",
                    ),
                    cls="flex items-center space-x-4",
                ),
                cls="p-6 border-b border-gray-200 flex justify-between items-center",
            ),
            Div(backtest_table, cls="overflow-x-auto"),
            cls="bg-white rounded-lg shadow",
            id="backtest-list",
        ),
        section_toggle_script,
        _strategy_modal_script(),
        Div(id="modal-container"),
        cls="space-y-6",
    )

    return layout.render()

@rt("/{name}")
def strategy_detail(req, session, name: str):
    layout = MainLayout(title=f"策略详情 - {name}", user=session.get("auth"))

    strategies = strategy_loader.load_from_cache()

    if name not in strategies:
        return RedirectResponse("/strategy")

    cls = strategies[name]
    doc = cls.__doc__ or "暂无描述"
    params = getattr(cls, "PARAMS", {})

    # Get history
    portfolios = db.get_portfolios_by_strategy(name)
    history_rows = []

    if not portfolios.is_empty():
        # Sort by start time desc (assuming DB returns roughly in order, or we sort manually)
        # Polars sort:
        portfolios = portfolios.sort("start", descending=True)

        for row in portfolios.iter_rows(named=True):
            pid = row["portfolio_id"]
            start = row["start"]
            end = row["end"]

            history_rows.append(
                Tr(
                    Td(pid[:8]),
                    Td(str(start)),
                    Td(str(end)),
                    Td(
                        A("查看报告", href=f"/strategy/backtest/{pid}", cls="text-blue-600 hover:underline"),
                    )
                )
            )

    history_table = Table(
        Thead(Tr(Th("ID"), Th("开始时间"), Th("结束时间"), Th("操作"))),
        Tbody(*history_rows),
        cls=TableT.striped
    )

    layout.main_block = lambda: Div(
        Div(
            A("← 返回列表", href="/strategy", cls="text-gray-500 hover:text-gray-800 mb-4 inline-block"),
            H1(name, cls="text-3xl font-bold mb-2"),
            P(doc, cls="text-gray-600 mb-6"),

            Card(
                CardHeader(H3("默认参数")),
                CardBody(Pre(str(params), cls="bg-gray-50 p-4 rounded text-sm")),
                cls="mb-6"
            ),

            Div(
                H3("回测历史", cls="text-xl font-bold mb-4"),
                history_table,
                cls="bg-white p-6 rounded-lg shadow-sm border border-gray-100"
            ),

            cls="max-w-4xl mx-auto py-8"
        )
    )

    return layout.render()

# --- Backtest Modal & Runner ---

def _parse_params(form, prefix="param_"):
    config = {}
    for k, v in form.items():
        if k.startswith(prefix):
            param_name = k[len(prefix):]
            # Try to infer type
            if v.lower() == 'true':
                v = True
            elif v.lower() == 'false':
                v = False
            else:
                try:
                    if '.' in v:
                        v = float(v)
                    else:
                        v = int(v)
                except (TypeError, ValueError):
                    pass
            config[param_name] = v
    return config

@rt("/{name}/backtest/modal")
def backtest_modal(name: str):
    strategies = strategy_loader.load_from_cache()
    cls = strategies.get(name)
    if not cls:
        return "Strategy not found"

    default_params = getattr(cls, "PARAMS", {})

    param_inputs = []
    for k, v in default_params.items():
        param_inputs.append(
            Div(
                Span(k, cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                Input(name=f"param_{k}", value=str(v), cls="input input-sm w-full"),
                cls="flex items-center gap-3 mb-3"
            )
        )

    return Div(
        Div(
            H3(f"运行回测 - {name}", cls="text-lg font-bold mb-4"),
            Form(
                Div(
                    Span("开始日期", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                    Input(
                        name="start_date",
                        type="date",
                        value="2024-01-01",
                        required=True,
                        cls="input input-sm w-full"
                    ),
                    cls="flex items-center gap-3 mb-3"
                ),
                Div(
                    Span("结束日期", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                    Input(
                        name="end_date",
                        type="date",
                        value=arrow.now().format("YYYY-MM-DD"),
                        required=True,
                        cls="input input-sm w-full"
                    ),
                    cls="flex items-center gap-3 mb-3"
                ),
                Div(
                    Span("初始资金", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                    Input(
                        name="initial_cash",
                        type="number",
                        value="1000000",
                        cls="input input-sm w-full"
                    ),
                    cls="flex items-center gap-3 mb-3"
                ),
                Div(
                    Span("周期", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                    fh.Select(
                        fh.Option("日线", value="1d", selected="selected"),
                        fh.Option("1分钟", value="1m"),
                        name="interval",
                        cls="uk-select uk-form-small flex-1 text-gray-700",
                    ),
                    cls="flex items-center gap-3 mb-3"
                ),
                Div(
                    Span("日志保存", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                    fh.Label(
                        fh.Input(name="save_logs", type="checkbox", cls="checkbox checkbox-sm"),
                        Span("保存回测日志到本地文件", cls="text-sm text-gray-700"),
                        cls="flex items-center gap-2",
                    ),
                    cls="flex items-center gap-3 mb-1"
                ),
                P(
                    "开启后会在回测运行时同步写入本地 backtest_logs 目录，报告页可反复加载。",
                    cls="ml-[6.75rem] mb-3 text-xs text-gray-500",
                ),
                Div(H4("策略参数", cls="text-sm font-semibold text-gray-600 mt-4 mb-2"), *param_inputs),
                Div(
                    Button("取消", type="button", cls="btn btn-ghost", onclick=STRATEGY_MODAL_CLOSE_JS),
                    Button(
                        "开始运行",
                        type="button",
                        cls="btn btn-primary",
                        onclick="this.disabled=true;this.setAttribute('aria-busy','true');this.textContent='启动中...';",
                        hx_post=f"/strategy/{name}/backtest/run",
                        hx_target="#modal-container",
                        hx_include="closest form"
                    ),
                    cls="flex justify-end gap-2 mt-6"
                ),
            ),
            cls="bg-white p-6 rounded-xl shadow-xl max-w-lg w-full"
        ),
        cls="fixed inset-0 bg-black/50 flex items-center justify-center z-50",
        id="strategy-modal"
    )

@rt("/{name}/backtest/run", methods=["POST"])
async def run_backtest(req, name: str):
    form = await req.form()

    try:
        start_date = arrow.get(form.get("start_date")).date()
        end_date = arrow.get(form.get("end_date")).date()
        initial_cash = float(form.get("initial_cash", 1000000))
        interval = form.get("interval", "1d")
        save_logs = _parse_checkbox(form.get("save_logs"))
        config = _parse_params(form)

        strategies = strategy_loader.load_from_cache()
        cls = strategies.get(name)

        if not cls:
            raise Exception("Strategy not found")

        portfolio_id = uuid.uuid4().hex
        strategy_runtime_manager.create_backtest_runtime(
            portfolio_id=portfolio_id,
            strategy_name=name,
            config=config,
            interval=interval,
            start_date=str(start_date),
            end_date=str(end_date),
            initial_cash=initial_cash,
            save_logs=save_logs,
        )
        runner = BacktestRunner()
        loop = asyncio.get_running_loop()

        def _job():
            try:
                asyncio.run(
                    runner.run(
                        strategy_cls=cls,
                        config=config,
                        start_date=start_date,
                        end_date=end_date,
                        frame_type=FrameType(interval),
                        initial_cash=initial_cash,
                        portfolio_id=portfolio_id,
                        save_logs=save_logs,
                    )
                )
                strategy_runtime_manager.complete_backtest_runtime(portfolio_id)
            except Exception as e:
                strategy_runtime_manager.complete_backtest_runtime(
                    portfolio_id, error=str(e)
                )
                raise

        loop.run_in_executor(None, _job)
        return Response(
            "",
            headers={"HX-Redirect": f"/strategy/backtest/{portfolio_id}"},
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Div(
            Div(f"回测失败: {str(e)}", cls="text-red-500 mb-4"),
            Button("关闭", cls="btn btn-secondary", onclick="this.closest('.modal').remove()"),
            cls="p-4 bg-white rounded shadow"
        )


def _get_runtime(req):
    if req is None:
        return None
    app = getattr(req, "app", None)
    state = getattr(app, "state", None)
    return getattr(state, "runtime", None)


def _get_registry(req):
    runtime = _get_runtime(req)
    if runtime is None:
        return None
    return runtime.registry


def _get_market_data(req):
    runtime = _get_runtime(req)
    if runtime is None:
        return None
    return runtime.market_data


def _get_paper_deploy_availability(req) -> tuple[bool, str]:
    """返回转入仿真的可用性。"""
    runtime = _get_runtime(req)
    if runtime is None:
        return False, "运行时未初始化，无法转仿真"
    if runtime.market_data is None:
        return False, "行情源未初始化，无法转仿真"
    return True, ""


def _get_live_deploy_availability(req) -> tuple[bool, str]:
    """返回转入实盘的可用性。"""
    registry = _get_registry(req)
    if registry is None:
        return False, "运行时未初始化，无法转实盘"
    if registry.get(BrokerKind.QMT, "gateway") is None:
        return False, "请先配置交易网关，才能转实盘"
    return True, ""


def _get_backtest_deploy_capabilities(req) -> dict[str, Any]:
    """返回回测投放按钮的可用性上下文。"""
    paper_available, paper_unavailable_reason = _get_paper_deploy_availability(req)
    live_available, live_unavailable_reason = _get_live_deploy_availability(req)
    return {
        "paper_available": paper_available,
        "paper_unavailable_reason": paper_unavailable_reason,
        "live_available": live_available,
        "live_unavailable_reason": live_unavailable_reason,
    }


def _get_live_accounts(req) -> list[dict[str, Any]]:
    live_available, _ = _get_live_deploy_availability(req)
    if not live_available:
        return []
    return [{"id": "gateway:default", "name": "gateway:default"}]


def _render_deploy_result(message: str, is_error: bool = False) -> Any:
    """渲染策略投放结果提示。"""
    base_cls = "mt-3 rounded-lg px-3 py-2 text-sm"
    cls = (
        f"{base_cls} border border-red-200 bg-red-50 text-red-600"
        if is_error
        else f"{base_cls} border border-green-200 bg-green-50 text-green-600"
    )
    return Div(message, id="deploy-result", cls=cls, hx_swap_oob="true")


def _paper_deploy_modal(
    portfolio_id: str,
    principal: str = "1000000",
    error_message: str = "",
) -> Any:
    """渲染转入仿真确认弹窗。"""
    error_block = (
        P(error_message, cls="text-sm text-red-600") if error_message else None
    )
    return _strategy_dialog_modal(
        "确认转入仿真",
        Div(
            P("请输入仿真本金后确认转入仿真运行。", cls="text-sm text-gray-500"),
            error_block,
            Form(
                Input(type="hidden", name="portfolio_id", value=portfolio_id),
                Div(
                    fh.Label("仿真本金", cls="text-sm text-gray-500"),
                    Input(
                        name="paper_principal",
                        type="number",
                        min="1",
                        step="0.01",
                        value=principal,
                        cls="input input-sm w-full",
                        required=True,
                    ),
                    cls="space-y-2 mt-4",
                ),
                id="deploy-paper-form",
            ),
            cls="space-y-4",
        ),
        Div(
            Button(
                "取消",
                type="button",
                cls="btn btn-ghost",
                onclick=STRATEGY_MODAL_CLOSE_JS,
            ),
            Button(
                "确认转入仿真",
                type="button",
                cls="btn btn-primary",
                onclick="this.disabled=true;this.setAttribute('aria-busy','true');this.textContent='提交中...';",
                hx_post=f"/strategy/backtest/{portfolio_id}/deploy/paper",
                hx_target="#modal-container",
                hx_include="#deploy-paper-form",
            ),
            cls="flex justify-end gap-2",
        ),
        modal_id="deploy-paper-modal",
    )


def _live_deploy_modal(
    portfolio_id: str,
    live_accounts: list[dict[str, Any]],
) -> Any:
    """渲染转入实盘确认弹窗。"""
    if not live_accounts:
        return _strategy_dialog_modal(
            "无法转入实盘",
            Div(
                P("未检测到可用的实盘网关，请先配置并启动实盘网关。", cls="text-sm text-red-600"),
            ),
            Div(
                Button(
                    "关闭",
                    type="button",
                    cls="btn btn-ghost",
                    onclick=STRATEGY_MODAL_CLOSE_JS,
                ),
                cls="flex justify-end gap-2",
            ),
            modal_id="deploy-live-unavailable-modal",
            width_cls="max-w-md",
        )

    account_id = str(live_accounts[0].get("id") or "gateway:default")
    account_name = str(live_accounts[0].get("name") or account_id)
    return _strategy_dialog_modal(
        "确认转入实盘",
        Div(
            P("确认后会把当前回测参数转入实盘运行。", cls="text-sm text-gray-500"),
            P(f"实盘网关：{account_name}", cls="mt-3 text-sm text-gray-700"),
            Form(
                Input(type="hidden", name="live_account_id", value=account_id),
                id="deploy-live-form",
            ),
            cls="space-y-4",
        ),
        Div(
            Button(
                "取消",
                type="button",
                cls="btn btn-ghost",
                onclick=STRATEGY_MODAL_CLOSE_JS,
            ),
            Button(
                "确认转入实盘",
                type="button",
                cls="btn btn-secondary",
                onclick="this.disabled=true;this.setAttribute('aria-busy','true');this.textContent='提交中...';",
                hx_post=f"/strategy/backtest/{portfolio_id}/deploy/live",
                hx_target="#modal-container",
                hx_include="#deploy-live-form",
            ),
            cls="flex justify-end gap-2",
        ),
        modal_id="deploy-live-modal",
    )


def _delete_backtest_modal(portfolio_id: str) -> Any:
    """渲染删除回测确认弹窗。"""
    portfolio = db.get_portfolio(portfolio_id)
    name = portfolio.name if portfolio else "--"
    id_short = portfolio_id[:8]
    status, _ = _resolve_backtest_status(portfolio_id)
    is_running = status == "running"
    deployment_modes = strategy_runtime_manager.backtest_deployment_modes(portfolio_id)
    is_deployed = bool(deployment_modes)

    warning_block: Any = None
    if is_running:
        warning_block = P(
            "回测正在运行，无法删除。请先等待回测结束。",
            cls="text-sm text-amber-600",
        )
    elif is_deployed:
        warning_block = P(
            "此回测已投放，删除报告不影响投放运行。",
            cls="text-sm text-blue-600",
        )

    return _strategy_dialog_modal(
        "确认删除回测",
        Div(
            P(
                "确定要删除回测报告吗？此操作不可恢复。",
                cls="text-sm text-gray-700",
            ),
            P(
                f"策略：{name}",
                cls="text-sm text-gray-500 mt-2",
            ),
            P(
                f"ID：{id_short}",
                cls="text-sm text-gray-500",
            ),
            warning_block,
            cls="space-y-3",
        ),
        Div(
            Button(
                "取消",
                type="button",
                cls="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50",
                onclick=STRATEGY_MODAL_CLOSE_JS,
            ),
            Button(
                "确认删除",
                type="button",
                cls="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700",
                disabled=is_running,
                onclick="this.disabled=true;this.setAttribute('aria-busy','true');this.textContent='删除中...';",
                hx_post=f"/strategy/backtest/{portfolio_id}/delete",
                hx_target="#modal-container",
            ),
            cls="flex justify-end gap-2",
        ),
        modal_id="delete-backtest-modal",
        width_cls="max-w-md",
    )


@rt("/backtest/{portfolio_id}/delete/modal")
def delete_backtest_modal(portfolio_id: str):
    """删除回测确认弹窗路由。"""
    return _delete_backtest_modal(portfolio_id)


@rt("/backtest/{portfolio_id}/delete", methods=["POST"])
def delete_backtest_execute(portfolio_id: str):
    """执行删除回测。"""
    status, _ = _resolve_backtest_status(portfolio_id)
    if status == "running":
        return _strategy_dialog_modal(
            "无法删除",
            Div(
                P("回测正在运行，无法删除。", cls="text-sm text-red-600"),
            ),
            Div(
                Button(
                    "关闭",
                    type="button",
                    cls="btn btn-ghost",
                    onclick=STRATEGY_MODAL_CLOSE_JS,
                ),
                cls="flex justify-end gap-2",
            ),
            modal_id="delete-backtest-error-modal",
            width_cls="max-w-md",
        )
    db.delete_portfolio_cascade(portfolio_id)
    delete_saved_backtest_log(portfolio_id)
    strategy_runtime_manager.remove_backtest_run(portfolio_id)
    return Response(
        "",
        headers={"HX-Redirect": "/strategy"},
    )


@rt("/backtest/{portfolio_id}/deploy/paper/modal")
def deploy_backtest_to_paper_modal(portfolio_id: str):
    """渲染转入仿真确认弹窗。"""
    return _paper_deploy_modal(portfolio_id)


@rt("/backtest/{portfolio_id}/deploy/live/modal")
def deploy_backtest_to_live_modal(req, portfolio_id: str):
    """渲染转入实盘确认弹窗。"""
    return _live_deploy_modal(portfolio_id, _get_live_accounts(req))


@rt("/backtest/{portfolio_id}/deploy/paper", methods=["POST"])
async def deploy_backtest_to_paper(req, portfolio_id: str):
    form = await req.form()
    principal_raw = str(form.get("paper_principal", "1000000") or "1000000")
    try:
        principal = float(principal_raw)
    except ValueError:
        return _paper_deploy_modal(portfolio_id, principal=principal_raw, error_message="请输入有效的仿真本金")
    if principal <= 0:
        return _paper_deploy_modal(portfolio_id, principal=principal_raw, error_message="仿真本金必须大于 0")
    registry = _get_registry(req)
    if registry is None:
        return _paper_deploy_modal(portfolio_id, principal=principal_raw, error_message="运行时未初始化")
    existing_runtime = strategy_runtime_manager.get_active_backtest_deployment(portfolio_id, "paper")
    if existing_runtime is not None:
        return (
            Div(id="modal-container"),
            _render_deploy_result(
                f"该回测已在仿真中：{existing_runtime.portfolio_id}，策略ID={existing_runtime.strategy_id}",
                is_error=False,
            ),
            _build_backtest_action_cell(
                portfolio_id,
                hx_swap_oob=True,
                **_get_backtest_deploy_capabilities(req),
            ),
        )
    try:
        runtime = strategy_runtime_manager.deploy_to_paper(
            portfolio_id=portfolio_id,
            principal=principal,
            registry=registry,
            market_data=_get_market_data(req),
        )
        return (
            Div(id="modal-container"),
            _render_deploy_result(
                f"已转入仿真：{runtime.portfolio_id}，策略ID={runtime.strategy_id}",
                is_error=False,
            ),
            _build_backtest_action_cell(
                portfolio_id,
                hx_swap_oob=True,
                **_get_backtest_deploy_capabilities(req),
            ),
        )
    except Exception as e:
        return _paper_deploy_modal(portfolio_id, principal=principal_raw, error_message=f"转入仿真失败: {e}")


@rt("/backtest/{portfolio_id}/deploy/live", methods=["POST"])
async def deploy_backtest_to_live(req, portfolio_id: str):
    form = await req.form()
    account_id = str(form.get("live_account_id") or "gateway:default")
    registry = _get_registry(req)
    if registry is None:
        return _live_deploy_modal(portfolio_id, [])
    live_accounts = _get_live_accounts(req)
    if not live_accounts:
        return _live_deploy_modal(portfolio_id, [])
    existing_runtime = strategy_runtime_manager.get_active_backtest_deployment(portfolio_id, "live")
    if existing_runtime is not None:
        return (
            Div(id="modal-container"),
            _render_deploy_result(
                f"该回测已在实盘中：{existing_runtime.portfolio_id}，策略ID={existing_runtime.strategy_id}",
                is_error=False,
            ),
            _build_backtest_action_cell(
                portfolio_id,
                hx_swap_oob=True,
                **_get_backtest_deploy_capabilities(req),
            ),
        )
    try:
        runtime = strategy_runtime_manager.deploy_to_live(
            portfolio_id=portfolio_id,
            account_id=account_id,
            registry=registry,
            market_data=_get_market_data(req),
        )
        return (
            Div(id="modal-container"),
            _render_deploy_result(
                f"已转入实盘：{runtime.portfolio_id}，策略ID={runtime.strategy_id}",
                is_error=False,
            ),
            _build_backtest_action_cell(
                portfolio_id,
                hx_swap_oob=True,
                **_get_backtest_deploy_capabilities(req),
            ),
        )
    except Exception as e:
        return _strategy_dialog_modal(
            "转入实盘失败",
            Div(P(str(e), cls="text-sm text-red-600")),
            Div(
                Button(
                    "关闭",
                    type="button",
                    cls="btn btn-ghost",
                    onclick=STRATEGY_MODAL_CLOSE_JS,
                ),
                cls="flex justify-end gap-2",
            ),
            modal_id="deploy-live-error-modal",
            width_cls="max-w-md",
        )

# --- Grid Search Modal & Runner ---

@rt("/{name}/grid_search/modal")
def grid_search_modal(name: str):
    strategies = strategy_loader.load_from_cache()
    cls = strategies.get(name)
    if not cls:
        return "Strategy not found"

    default_params = getattr(cls, "PARAMS", {})

    param_inputs = []
    for k, v in default_params.items():
        # For grid search, we expect comma separated values
        param_inputs.append(
            Div(
                Span(f"{k} (逗号分隔)", cls="text-sm font-medium text-gray-500 w-32 shrink-0"),
                Input(
                    name=f"param_{k}",
                    value=str(v),
                    placeholder="例如: 10, 20, 30",
                    cls="input input-sm w-full",
                ),
                cls="flex items-center gap-3 mb-3"
            )
        )

    return Div(
        Div(
            H3(f"运行网格搜索 - {name}", cls="text-lg font-bold mb-4"),
            Form(
                Div(
                    Span("开始日期", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                    Input(
                        name="start_date",
                        type="date",
                        value="2024-01-01",
                        required=True,
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-3"
                ),
                Div(
                    Span("结束日期", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                    Input(
                        name="end_date",
                        type="date",
                        value=arrow.now().format("YYYY-MM-DD"),
                        required=True,
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-3"
                ),
                Div(
                    Span("并发数量", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
                    Input(
                        name="max_workers",
                        type="number",
                        value="4",
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-3"
                ),
                Div(
                    H4("参数网格", cls="text-sm font-semibold text-gray-600 mt-4 mb-2"),
                    P("输入多个值以逗号分隔，如: 5, 10, 20", cls="text-xs text-gray-500 mb-2"),
                    *param_inputs
                ),
                Div(
                    Button("取消", type="button", cls="btn btn-ghost", onclick=STRATEGY_MODAL_CLOSE_JS),
                    Button(
                        "开始运行",
                        type="button",
                        cls="btn btn-primary",
                        hx_post=f"/strategy/{name}/grid_search/run",
                        hx_target="#modal-container",
                        hx_include="closest form"
                    ),
                    cls="flex justify-end gap-2 mt-6"
                ),
            ),
            cls="bg-white p-6 rounded-xl shadow-xl max-w-lg w-full"
        ),
        cls="fixed inset-0 bg-black/50 flex items-center justify-center z-50",
        id="grid-search-modal"
    )

@rt("/{name}/grid_search/run", methods=["POST"])
async def run_grid_search(req, name: str):
    form = await req.form()

    try:
        start_date = arrow.get(form.get("start_date")).date()
        end_date = arrow.get(form.get("end_date")).date()
        max_workers = int(form.get("max_workers", 4))

        # Parse grid params
        param_grid = {}
        base_config = {}

        strategies = strategy_loader.load_from_cache()
        cls = strategies.get(name)
        if not cls:
            raise Exception("Strategy not found")

        for k, v in form.items():
            if k.startswith("param_"):
                param_name = k[6:]
                # Split by comma
                if ',' in v:
                    values = [x.strip() for x in v.split(',')]
                    # Try convert types
                    converted_values = []
                    for val in values:
                        try:
                            if '.' in val:
                                converted_values.append(float(val))
                            else:
                                converted_values.append(int(val))
                        except (TypeError, ValueError):
                            converted_values.append(val)
                    param_grid[param_name] = converted_values
                else:
                    # Single value, treat as base config
                    try:
                        if '.' in v:
                            base_config[param_name] = float(v)
                        else:
                            base_config[param_name] = int(v)
                    except (TypeError, ValueError):
                        base_config[param_name] = v

        gs = GridSearch(
            strategy_cls=cls,
            base_config=base_config,
            param_grid=param_grid,
            start_date=start_date,
            end_date=end_date,
            initial_cash=1000000,
            max_workers=max_workers
        )

        # Run grid search in a separate thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        results_df = await loop.run_in_executor(None, lambda: gs.run(save_logs=True))

        # Show results in a modal or redirect?
        # Let's show a summary table in a modal

        rows = []
        # Sort by annual_return desc
        if not results_df.is_empty():
            results_df = results_df.sort("annual_return", descending=True).head(10)
            for row in results_df.iter_rows(named=True):
                rows.append(
                    Tr(
                        Td(str(row["params"])),
                        Td(f"{row['annual_return']:.2%}"),
                        Td(f"{row['sharpe']:.2f}"),
                        Td(f"{row['max_drawdown']:.2%}"),
                    )
                )

        result_table = Table(
            Thead(Tr(Th("参数"), Th("年化"), Th("夏普"), Th("回撤"))),
            Tbody(*rows),
            cls=TableT.striped + " text-xs"
        )

        return Modal(
            ModalTitle("网格搜索结果 (Top 10)"),
            ModalBody(result_table),
            ModalFooter(
                Button("关闭", cls=ButtonT.primary, onclick=STRATEGY_MODAL_CLOSE_JS)
            ),
            open=True
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Div(
            Div(f"搜索失败: {str(e)}", cls="text-red-500 mb-4"),
            Button("关闭", cls=ButtonT.secondary, onclick="this.closest('.modal').remove()"),
            cls="p-4 bg-white rounded shadow"
        )

# --- Backtest Result View ---

@rt("/backtest/{portfolio_id}")
def backtest_result(req, session, portfolio_id: str):
    layout = MainLayout(title="回测报告", user=session.get("auth"))
    layout.header_active = "策略"
    active_tab = _normalize_backtest_tab(getattr(req, "query_params", {}).get("tab"))
    layout.sidebar_menu = _build_backtest_sidebar_menu(portfolio_id, active_tab)

    status, backtest_error = _resolve_backtest_status(portfolio_id)
    metrics_payload = _build_metrics_payload(portfolio_id)

    date_axis = _build_date_axis(portfolio_id)
    series_payload = _build_series_payload(portfolio_id, date_axis)

    metrics_items = [
        ("annual_return", "年化收益", "percent"),
        ("total_returns", "累计收益", "percent"),
        ("max_drawdown", "最大回撤", "percent"),
        ("volatility", "波动率", "percent"),
        ("sharpe", "夏普比率", "number"),
        ("sortino", "索提诺比率", "number"),
        ("calmar", "卡玛比率", "number"),
        ("alpha", "Alpha", "number"),
        ("beta", "Beta", "number"),
        ("win_rate", "胜率", "percent"),
        ("profit_factor", "盈亏比", "number"),
        ("payoff_ratio", "收益风险比", "number"),
        ("avg_return", "平均收益", "percent"),
        ("avg_win", "平均盈利", "percent"),
        ("avg_loss", "平均亏损", "percent"),
        ("best_day", "最佳单日", "percent"),
        ("worst_day", "最差单日", "percent"),
        ("tail_ratio", "尾部比", "number"),
        ("skew", "偏度", "number"),
        ("kurtosis", "峰度", "number"),
        ("value_at_risk", "VaR", "percent"),
        ("information_ratio", "信息比率", "number"),
    ]

    metrics_entries = []
    for key, label, fmt in metrics_items:
        value = metrics_payload.get(key)
        value_text = _format_percent(value) if fmt == "percent" else _format_number(value)
        if value is not None and value > 0:
            value_cls = "text-red-600"
        elif value is not None and value < 0:
            value_cls = "text-green-600"
        else:
            value_cls = "text-gray-700"
        metrics_entries.append(
            Div(
                Span(f"{label}:", cls="text-gray-500"),
                Span(value_text, id=f"metric_{key}", cls=f"{value_cls} ml-1"),
                cls="text-sm",
            )
        )
    metrics_text = Div(*metrics_entries, cls="flex flex-wrap gap-x-6 gap-y-2")

    error_panel = (
        Div(
            H3("运行错误", cls="text-sm font-semibold text-red-700 mb-2"),
            P(backtest_error, id="backtest_error", cls="text-sm text-red-600 whitespace-pre-wrap"),
            cls="mb-4 rounded-lg border border-red-200 bg-red-50 p-4",
        )
        if backtest_error
        else Div(id="backtest_error", cls="hidden")
    )

    filter_start_value = date_axis[0] if date_axis else ""
    filter_end_value = date_axis[-1] if date_axis else ""

    chart_id = f"chart_{portfolio_id}"
    date_axis_json = json.dumps(series_payload["date_axis"])
    total_series_json = json.dumps(series_payload["total"])
    benchmark_series_json = json.dumps(series_payload["benchmark"])
    daily_pnl_json = json.dumps(series_payload["daily_pnl"])
    trade_count_json = json.dumps(series_payload["trade_count"])
    metric_format_json = json.dumps({key: fmt for key, _, fmt in metrics_items})
    chart_script = Script(f"""
        var chart = echarts.init(document.getElementById('{chart_id}'));
        var dateAxis = {date_axis_json};
        var totalSeries = {total_series_json};
        var benchmarkSeries = {benchmark_series_json};
        var dailyPnlSeries = {daily_pnl_json};
        var tradeCountSeries = {trade_count_json};
        var seriesData = {{
            dateAxis: dateAxis,
            total: totalSeries,
            benchmark: benchmarkSeries,
            dailyPnl: dailyPnlSeries,
            tradeCount: tradeCountSeries
        }};
        var option = {{
            tooltip: {{ trigger: 'axis' }},
            grid: [
                {{ left: 60, right: 20, top: 40, height: 200 }},
                {{ left: 60, right: 20, top: 260, height: 110 }},
                {{ left: 60, right: 20, top: 400, height: 120 }}
            ],
            xAxis: [
                {{ type: 'category', data: dateAxis, boundaryGap: false, axisLabel: {{ show: false }} }},
                {{ type: 'category', data: dateAxis, boundaryGap: true, axisLabel: {{ show: false }}, gridIndex: 1 }},
                {{ type: 'category', data: dateAxis, boundaryGap: true, axisLabel: {{ show: true }}, gridIndex: 2 }}
            ],
            yAxis: [
                {{ type: 'value', scale: true }},
                {{ type: 'value', scale: true, gridIndex: 1 }},
                {{ type: 'value', scale: true, gridIndex: 2 }}
            ],
            dataZoom: [
                {{ type: 'inside', xAxisIndex: [0, 1, 2] }},
                {{ type: 'slider', xAxisIndex: [0, 1, 2], bottom: 0 }}
            ],
            series: [
                {{
                    name: '总资产',
                    type: 'line',
                    data: totalSeries,
                    smooth: true,
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    itemStyle: {{ color: '#d9534f' }}
                }},
                {{
                    name: '基准',
                    type: 'line',
                    data: benchmarkSeries,
                    smooth: true,
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    lineStyle: {{ type: 'dashed' }},
                    itemStyle: {{ color: '#9ca3af' }}
                }},
                {{
                    name: '每日盈亏',
                    type: 'bar',
                    data: dailyPnlSeries,
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    itemStyle: {{ color: '#5b8ff9' }}
                }},
                {{
                    name: '每日交易',
                    type: 'bar',
                    data: tradeCountSeries,
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    itemStyle: {{ color: '#30bf78' }}
                }}
            ]
        }};
        chart.setOption(option);
        window.addEventListener('resize', function() {{ chart.resize(); }});

        function fmtPercent(v) {{
            if (v === null || v === undefined || isNaN(v)) return "--";
            return (v * 100).toFixed(2) + "%";
        }}

        function fmtNumber(v) {{
            if (v === null || v === undefined || isNaN(v)) return "--";
            return Number(v).toFixed(2);
        }}

        function fmtValue(v, fmt) {{
            if (fmt === "percent") return fmtPercent(v);
            return fmtNumber(v);
        }}

        function metricColor(v) {{
            if (v > 0) return "text-red-600";
            if (v < 0) return "text-green-600";
            return "text-gray-700";
        }}

        function updateMetric(key, value, fmt) {{
            var el = document.getElementById('metric_' + key);
            if (!el) return;
            el.textContent = fmtValue(value, fmt);
            el.className = metricColor(value) + " ml-1";
        }}

        function getDateValue(id) {{
            var el = document.getElementById(id);
            return el ? el.value : "";
        }}

        function filterSeries(series) {{
            var start = getDateValue("filter_start");
            var end = getDateValue("filter_end");
            var filtered = {{
                dateAxis: [],
                total: [],
                benchmark: [],
                dailyPnl: [],
                tradeCount: []
            }};
            for (var i = 0; i < series.dateAxis.length; i++) {{
                var dt = series.dateAxis[i];
                if (start && dt < start) continue;
                if (end && dt > end) continue;
                filtered.dateAxis.push(dt);
                filtered.total.push(series.total[i]);
                filtered.benchmark.push(series.benchmark[i]);
                filtered.dailyPnl.push(series.dailyPnl[i]);
                filtered.tradeCount.push(series.tradeCount[i]);
            }}
            return filtered;
        }}

        function updateChart(series) {{
            var filtered = filterSeries(series);
            chart.setOption({{
                xAxis: [
                    {{ data: filtered.dateAxis }},
                    {{ data: filtered.dateAxis }},
                    {{ data: filtered.dateAxis }}
                ],
                series: [
                    {{ data: filtered.total }},
                    {{ data: filtered.benchmark }},
                    {{ data: filtered.dailyPnl }},
                    {{ data: filtered.tradeCount }}
                ]
            }});
        }}

        var filterStart = document.getElementById("filter_start");
        if (filterStart) {{
            filterStart.addEventListener("change", function() {{ updateChart(seriesData); }});
        }}
        var filterEnd = document.getElementById("filter_end");
        if (filterEnd) {{
            filterEnd.addEventListener("change", function() {{ updateChart(seriesData); }});
        }}
        updateChart(seriesData);

        function renderTrades(trades) {{
            var body = document.getElementById('trade_table_body');
            if (!body) return;
            var html = "";
            for (var i = 0; i < trades.length; i++) {{
                var t = trades[i];
                var color = t.side_value === 1 ? "text-red-500" : "text-green-500";
                html += "<tr>" +
                    "<td>" + t.tm + "</td>" +
                    "<td>" + t.asset + "</td>" +
                    "<td class='" + color + "'>" + t.side + "</td>" +
                    "<td>" + fmtNumber(t.price) + "</td>" +
                    "<td>" + fmtNumber(t.shares) + "</td>" +
                    "<td>" + fmtNumber(t.amount) + "</td>" +
                    "<td>" + fmtNumber(t.fee) + "</td>" +
                    "</tr>";
            }}
            body.innerHTML = html;
        }}

        function renderDailySummary(rows) {{
            var body = document.getElementById('daily_summary_body');
            if (!body) return;
            var html = "";
            for (var i = 0; i < rows.length; i++) {{
                var r = rows[i];
                html += "<tr>" +
                    "<td>" + r.dt + "</td>" +
                    "<td>" + fmtNumber(r.cash) + "</td>" +
                    "<td>" + fmtNumber(r.market_value) + "</td>" +
                    "<td>" + fmtNumber(r.total) + "</td>" +
                    "<td>" + fmtNumber(r.daily_pnl) + "</td>" +
                    "<td>" + fmtPercent(r.daily_return) + "</td>" +
                    "</tr>";
            }}
            body.innerHTML = html;
        }}

        function renderPositions(rows) {{
            var body = document.getElementById('positions_body');
            if (!body) return;
            var html = "";
            var lastDate = null;
            for (var i = 0; i < rows.length; i++) {{
                var r = rows[i];
                if (lastDate !== r.dt) {{
                    html += "<tr><td colspan='6' class='bg-gray-50 font-semibold'>" + r.dt + "</td></tr>";
                    lastDate = r.dt;
                }}
                html += "<tr>" +
                    "<td>" + r.asset + "</td>" +
                    "<td>" + fmtNumber(r.shares) + "</td>" +
                    "<td>" + fmtNumber(r.avail) + "</td>" +
                    "<td>" + fmtNumber(r.price) + "</td>" +
                    "<td>" + fmtNumber(r.mv) + "</td>" +
                    "<td>" + fmtNumber(r.profit) + "</td>" +
                    "</tr>";
            }}
            body.innerHTML = html;
        }}

        function renderLogs(rows) {{
            var logEl = document.getElementById('log_output');
            if (!logEl) return;
            var lines = [];
            for (var i = 0; i < rows.length; i++) {{
                var r = rows[i];
                var line = r.dt + " | " + (r.level || "INFO") + " | " + (r.source || "system") + " | " + (r.message || "");
                if (r.extra) {{
                    line += " | " + r.extra;
                }}
                lines.push(line);
            }}
            logEl.textContent = lines.length ? lines.join("\\n") : "暂无回测日志";
        }}

        function renderLogMeta(meta) {{
            if (!meta) return;
            var saveStatus = document.getElementById('log_save_status');
            if (saveStatus) {{
                if (meta.save_requested && meta.saved) {{
                    saveStatus.textContent = '已保存到文件，可重复加载';
                    saveStatus.className = 'text-xs text-green-600';
                }} else if (meta.save_requested) {{
                    saveStatus.textContent = '已启用文件保存，日志生成后会写入本地文件';
                    saveStatus.className = 'text-xs text-amber-600';
                }} else {{
                    saveStatus.textContent = '本次回测未启用文件保存';
                    saveStatus.className = 'text-xs text-gray-500';
                }}
            }}
            var savePath = document.getElementById('log_save_path');
            if (savePath && meta.saved_path) {{
                savePath.textContent = meta.saved_path;
            }}
        }}

        var wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
        var wsUrl = wsScheme + "://" + window.location.host + "/strategy/backtest/{portfolio_id}/ws";
        var ws = new WebSocket(wsUrl);

        ws.onmessage = function(event) {{
            try {{
                var data = JSON.parse(event.data);
                if (data.series) {{
                    var series = data.series;
                    seriesData = {{
                        dateAxis: series.date_axis,
                        total: series.total,
                        benchmark: series.benchmark,
                        dailyPnl: series.daily_pnl,
                        tradeCount: series.trade_count
                    }};
                    updateChart(seriesData);
                }}
                if (data.metrics) {{
                    var formats = {metric_format_json};
                    for (var key in formats) {{
                        updateMetric(key, data.metrics[key], formats[key]);
                    }}
                }}
                if (data.trades) {{
                    renderTrades(data.trades);
                }}
                if (data.daily_summary) {{
                    renderDailySummary(data.daily_summary);
                }}
                if (data.positions) {{
                    renderPositions(data.positions);
                }}
                if (data.logs) {{
                    renderLogs(data.logs);
                }}
                if (data.log_meta) {{
                    renderLogMeta(data.log_meta);
                }}
                var errorEl = document.getElementById('backtest_error');
                if (errorEl && data.error) {{
                    errorEl.textContent = data.error;
                    if (errorEl.parentElement) {{
                        errorEl.parentElement.classList.remove('hidden');
                    }}
                }}
                if (data.status && data.status !== 'running') {{
                    ws.close();
                }}
            }} catch (e) {{}}
        }};
    """)

    trade_rows = _build_trade_rows(portfolio_id, limit=200)
    positions_rows = _build_daily_positions(portfolio_id)
    trade_table = Table(
        Thead(Tr(Th("时间"), Th("标的"), Th("方向"), Th("价格"), Th("数量"), Th("成交额"), Th("费用"))),
        Tbody(
            *[
                Tr(
                    Td(row["tm"]),
                    Td(row["asset"]),
                    Td(
                        row["side"],
                        cls="text-red-500"
                        if row["side_value"] == OrderSide.BUY
                        else "text-green-500",
                    ),
                    Td(f"{row['price']:.2f}"),
                    Td(f"{row['shares']:.2f}"),
                    Td(f"{row['amount']:.2f}"),
                    Td(f"{row['fee']:.2f}"),
                )
                for row in trade_rows
            ],
            id="trade_table_body",
        ),
        cls=TableT.striped + " text-xs"
    )
    position_trs = []
    last_date = None
    for row in positions_rows:
        dt = row.get("dt")
        if dt != last_date:
            position_trs.append(
                Tr(Td(dt, colspan="6", cls="bg-gray-50 font-semibold"))
            )
            last_date = dt
        position_trs.append(
            Tr(
                Td(row.get("asset", "")),
                Td(f"{row.get('shares', 0):.2f}"),
                Td(f"{row.get('avail', 0):.2f}"),
                Td(f"{row.get('price', 0):.2f}"),
                Td(f"{row.get('mv', 0):.2f}"),
                Td(f"{row.get('profit', 0):.2f}"),
            )
        )
    positions_table = Table(
        Thead(Tr(Th("标的"), Th("持仓"), Th("可用"), Th("价格"), Th("市值"), Th("浮盈"))),
        Tbody(*position_trs, id="positions_body"),
        cls=TableT.striped + " text-xs"
    )

    overview_panel = Div(
        Div(
            H3("收益概述", cls="text-xl font-bold mb-3"),
            metrics_text,
            cls="mb-4",
            id="overview",
        ),
        Div(
            H3("收益曲线", cls="text-xl font-bold mb-4"),
                Div(
                    Div(
                        fh.Label("开始日期", cls="block text-xs text-gray-500 mb-1"),
                        Input(
                            id="filter_start",
                            type="date",
                            value=filter_start_value,
                            cls="input input-sm",
                        ),
                        cls="flex flex-col"
                    ),
                    Div(
                        fh.Label("结束日期", cls="block text-xs text-gray-500 mb-1"),
                        Input(
                            id="filter_end",
                            type="date",
                            value=filter_end_value,
                            cls="input input-sm",
                        ),
                        cls="flex flex-col"
                    ),
                cls="flex flex-wrap gap-4 mb-4"
            ),
            Div(id=chart_id, cls="w-full h-[560px] bg-white p-4 rounded-xl shadow-sm border border-gray-100"),
            chart_script,
            cls="mt-6"
        ),
    )

    trades_panel = Div(
        H3("交易详情", cls="text-xl font-bold mb-4"),
        trade_table,
        cls="bg-white p-6 rounded-lg shadow-sm border border-gray-100 mt-6",
        id="trades"
    )

    positions_panel = Div(
        H3("每日持仓", cls="text-xl font-bold mb-4"),
        positions_table,
        cls="bg-white p-6 rounded-lg shadow-sm border border-gray-100 mt-6",
        id="positions"
    )

    logs_panel = _build_log_panel(
        portfolio_id=portfolio_id,
        status=status,
        rows=_build_log_rows(portfolio_id, limit=200),
    )

    active_panel = {
        "overview": overview_panel,
        "trades": trades_panel,
        "positions": positions_panel,
        "logs": logs_panel,
    }[active_tab]

    layout.main_block = lambda: Div(
        Script(src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"),

        Div(
            Div(
                A("← 返回策略详情", href="javascript:history.back()", cls="text-gray-500 hover:text-gray-800 mb-4 inline-block"),
                error_panel,
                active_panel,

                cls="max-w-6xl mx-auto py-8"
            )
        ),
        _strategy_modal_script(),
        Div(id="modal-container"),
    )

    return layout.render()


@rt("/backtest/{portfolio_id}/logs/saved")
def load_saved_backtest_log_panel(portfolio_id: str):
    """加载已保存的回测日志面板。"""
    status, _ = _resolve_backtest_status(portfolio_id)
    try:
        rows = load_saved_backtest_logs(portfolio_id, limit=200)
        return _build_log_panel(
            portfolio_id=portfolio_id,
            status=status,
            rows=rows,
            source_label="已保存文件",
        )
    except Exception as exc:
        return _build_log_panel(
            portfolio_id=portfolio_id,
            status=status,
            rows=[],
            source_label="已保存文件",
            error_text=str(exc),
        )


async def backtest_ws(websocket: WebSocket):
    """回测报告 websocket 推送。

    Args:
        websocket: WebSocket 连接
    """
    await websocket.accept()
    portfolio_id = websocket.path_params.get("portfolio_id")
    if not portfolio_id:
        await websocket.close(code=1008)
        return
    try:
        while True:
            status, backtest_error = _resolve_backtest_status(portfolio_id)
            date_axis = _build_date_axis(portfolio_id)
            payload = {
                "status": status,
                "error": backtest_error,
                "metrics": _build_metrics_payload(portfolio_id),
                "series": _build_series_payload(portfolio_id, date_axis),
                "trades": _build_trade_rows(portfolio_id, limit=200),
                "daily_summary": _build_daily_summary(portfolio_id),
                "positions": _build_daily_positions(portfolio_id),
                "logs": _build_log_rows(portfolio_id, limit=200),
                "log_meta": _build_log_meta(portfolio_id),
            }
            await websocket.send_text(json.dumps(payload))
            if status != "running":
                await websocket.close()
                return
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        return


strategy_app.add_websocket_route("/backtest/{portfolio_id}/ws", backtest_ws)


def _scan_scope_list(scan_dirs: list[str]):
    """渲染策略扫描目录列表。"""
    return Ul(
        *[
            Li(path, cls="break-all")
            for path in scan_dirs
        ],
        cls="list-disc pl-5 space-y-1 text-xs text-gray-500",
    )


def _strategy_scan_toolbar():
    """渲染策略扫描与示例复制工具栏。"""
    return Div(
        Button(
            Span(
                Svg(
                    SvgPath(
                        d="M12 4v16m8-8H4",
                        **{
                            "stroke-linecap": "round",
                            "stroke-linejoin": "round",
                            "stroke-width": "2",
                        },
                    ),
                    cls="w-5 h-5",
                    fill="none",
                    stroke="currentColor",
                    viewBox="0 0 24 24",
                ),
                cls="flex items-center",
            ),
            Span("扫描策略列表"),
            cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 inline-flex items-center gap-2 border-0 shadow-none",
            type="button",
            hx_post="/strategy/scan/run",
            hx_target="#modal-container",
        ),
        Button(
            Span("复制示例策略"),
            cls="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 inline-flex items-center gap-2 border-0 shadow-none",
            type="button",
            title="复制内置示例到用户策略目录",
            hx_post="/strategy/scan/copy-examples",
            hx_target="#modal-container",
        ),
        Button(
            UkIcon("cog", size=20),
            cls="p-2 bg-transparent border-0 shadow-none text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg inline-flex items-center justify-center",
            type="button",
            title="配置扫描目录",
            hx_get="/strategy/scan/config-modal",
            hx_target="#modal-container",
        ),
        cls="flex items-center gap-2",
    )


def _normalize_scan_directory(directory: str) -> tuple[str, Path]:
    """校验并标准化用户策略目录。"""
    text = directory.strip()
    if not text:
        raise ValueError("目录不能为空")

    path = FilePath(text).expanduser()
    if not path.is_absolute():
        raise ValueError("必须使用绝对路径，例如: /Users/name/strategies")

    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"目录不存在: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"路径不是目录: {path}")
    return str(path), path


# 配置对话框路由
@rt("/scan/config-modal")
def config_modal_route(req):
    scan_dir = strategy_loader.get_user_scan_directory()
    return _config_modal_html(scan_dir, is_error=False)


# 扫描确认对话框
@rt("/scan/confirm")
def scan_confirm_modal(req):
    scan_dirs = strategy_loader.get_scan_directories()

    return Div(
        Div(
            Div(
                H3("确认扫描", cls="text-lg font-semibold text-gray-900 mb-4"),
                P("确定要扫描策略目录吗？", cls="text-gray-700"),
                P("系统会默认扫描内置示例目录，并合并您配置的用户目录。", cls="text-sm text-gray-500 mt-2"),
                Div(
                    P("当前扫描范围：", cls="text-sm text-gray-500 mt-2 mb-2"),
                    _scan_scope_list(scan_dirs),
                    cls="mb-4",
                ),
                Div(
                    Button(
                        "取消",
                        type="button",
                        cls="px-4 py-2 text-gray-600 hover:text-gray-800",
                        onclick=STRATEGY_MODAL_CLOSE_JS,
                    ),
                    Button(
                        "确定扫描",
                        type="button",
                        cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 ml-2",
                        hx_post="/strategy/scan/run",
                        hx_target="#modal-container",
                    ),
                    cls="flex justify-end",
                ),
                cls="bg-white rounded-lg shadow-xl p-6 w-96",
            ),
            cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
        ),
        id="scan-confirm-modal",
    )


# 执行扫描
@rt("/scan/run", methods=["POST"])
def run_scan(req):
    try:
        strategies = strategy_loader.scan_and_cache()
        strategy_count = len(strategies)
        scan_dirs = strategy_loader.get_scan_directories()
        if strategy_count == 0:
            return Div(
                Div(
                    Div(
                        H3("扫描完成", cls="text-lg font-semibold text-gray-900 mb-4"),
                        P("未发现任何策略", cls="text-amber-600 font-medium"),
                        Div(
                            P("本次扫描范围：", cls="text-sm text-gray-500 mt-2 mb-2"),
                            _scan_scope_list(scan_dirs),
                            cls="mb-4",
                        ),
                        Div(
                            Button(
                                "关闭",
                                type="button",
                                cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700",
                                onclick=STRATEGY_MODAL_CLOSE_JS,
                            ),
                            cls="flex justify-end",
                        ),
                        cls="bg-white rounded-lg shadow-xl p-6 w-96",
                    ),
                    cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
                ),
                id="scan-result-modal",
            )

        return Div(
            Div(
                Div(
                    H3("扫描完成", cls="text-lg font-semibold text-gray-900 mb-4"),
                    P(f"成功发现 {strategy_count} 个策略", cls="text-green-600 font-medium"),
                    P("内置示例目录已默认参与扫描", cls="text-sm text-gray-500 mt-2"),
                    Div(
                        P("本次扫描范围：", cls="text-sm text-gray-500 mt-2 mb-2"),
                        _scan_scope_list(scan_dirs),
                        cls="mb-4",
                    ),
                    P("策略列表将自动刷新", cls="text-sm text-gray-500 mt-2 mb-4"),
                    Div(
                        Button(
                            "关闭",
                            type="button",
                            cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700",
                            onclick=STRATEGY_MODAL_CLOSE_JS,
                        ),
                        cls="flex justify-end",
                    ),
                    cls="bg-white rounded-lg shadow-xl p-6 w-96",
                ),
                cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
            ),
            Script("setTimeout(() => location.reload(), 1200);"),
            id="scan-result-modal",
        )
    except Exception as e:
        logger.error(f"Failed to scan strategies: {e}")
        return Div(
            Div(
                Div(
                    H3("扫描失败", cls="text-lg font-semibold text-gray-900 mb-4"),
                    P(f"错误: {str(e)}", cls="text-red-600 mb-4"),
                    Div(
                        Button(
                            "关闭",
                            type="button",
                            cls="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700",
                            onclick=STRATEGY_MODAL_CLOSE_JS,
                        ),
                        cls="flex justify-end",
                    ),
                    cls="bg-white rounded-lg shadow-xl p-6 w-96",
                ),
                cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
            ),
            id="scan-error-modal",
        )


def _config_modal_html(
    scan_dir: str, is_error: bool = False, error_message: str = ""
):
    """配置对话框 HTML。"""
    title = "配置用户策略目录"
    builtin_dir = strategy_loader.get_builtin_scan_directory()
    if error_message:
        message = P(error_message, cls="text-red-600 mb-4")
    elif is_error:
        message = P("请输入有效的用户策略目录。", cls="text-red-600 mb-4")
    else:
        message = P(
            "这里仅用于设置用户策略目录；复制示例请回到策略列表页点击“复制示例策略”。",
            cls="text-sm text-gray-500 mb-4",
        )

    return Div(
        Div(
            Div(
                H3(title, cls="text-lg font-semibold text-gray-900 mb-4"),
                message,
                Div(
                    P("内置示例目录会始终参与扫描：", cls="text-sm text-gray-600"),
                    P(
                        builtin_dir,
                        cls="mt-1 break-all rounded-lg bg-gray-50 px-3 py-2 font-mono text-xs text-gray-500",
                    ),
                    cls="mb-4",
                ),
                Div(
                    Input(
                        id="scan-dir-input",
                        value=scan_dir,
                        placeholder="请输入绝对路径，例如: /Users/name/strategies",
                        cls="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                    ),
                    cls="mb-4",
                ),
                Div(
                    Button(
                        "取消",
                        type="button",
                        cls="px-4 py-2 text-gray-600 hover:text-gray-800",
                        onclick=STRATEGY_MODAL_CLOSE_JS,
                    ),
                    Button(
                        "保存",
                        type="button",
                        cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 ml-2",
                        hx_post="/strategy/scan/config",
                        hx_include="#scan-dir-input",
                        hx_target="#modal-container",
                    ),
                    cls="flex justify-end",
                ),
                cls="bg-white rounded-lg shadow-xl p-6 w-96",
            ),
            cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
        ),
        id="config-modal",
    )


# API 路由：配置扫描目录
@rt("/scan/config", methods=["POST"])
async def save_scan_config(req):
    directory = ""
    try:
        form = await req.form()
        directory = form.get("scan-dir-input", "").strip()
        directory, _ = _normalize_scan_directory(directory)

        strategy_loader.set_scan_directory(directory)

        return Modal(
            ModalTitle("配置已保存"),
            ModalBody(
                P(f"用户策略目录已设置为: {directory}", cls="text-green-600"),
                P("扫描时会同时包含内置示例目录。", cls="text-sm text-gray-500 mt-2"),
                P("页面即将刷新...", cls="text-sm text-gray-500 mt-2"),
            ),
            ModalFooter(
                Button(
                    "确定",
                    type="button",
                    cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700",
                    onclick="location.reload()"
                ),
            ),
            id="config-success-modal"
        )
    except (ValueError, FileNotFoundError, NotADirectoryError) as e:
        return _config_modal_html(
            directory,
            is_error=True,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to set scan directory: {e}")
        return _config_modal_html(
            directory,
            is_error=True,
            error_message=f"保存失败: {str(e)}",
        )


def _copy_requires_config_modal():
    """提示用户先配置策略目录。"""
    return Modal(
        ModalTitle("请先设置用户策略目录"),
        ModalBody(
            P("复制示例策略前，需要先配置用户策略目录。", cls="text-amber-600"),
            P("点击下方“去设置”后，保存目录，再回来点击“复制示例策略”。", cls="text-sm text-gray-500 mt-2"),
        ),
        ModalFooter(
            Button(
                "取消",
                type="button",
                cls="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200",
                onclick=STRATEGY_MODAL_CLOSE_JS,
            ),
            Button(
                "去设置",
                type="button",
                cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700",
                hx_get="/strategy/scan/config-modal",
                hx_target="#modal-container",
            ),
        ),
        id="copy-requires-config-modal",
    )


@rt("/scan/copy-examples", methods=["POST"])
async def copy_scan_examples(req):
    """复制内置示例策略到用户目录。"""
    try:
        directory = strategy_loader.get_user_scan_directory().strip()
        if not directory:
            return _copy_requires_config_modal()

        directory, _ = _normalize_scan_directory(directory)
        result = strategy_loader.copy_examples_to_directory(directory)
        title = "示例已复制" if result.copied_count else "示例已存在"
        summary = (
            f"已复制 {result.copied_count} 个文件到: {directory}"
            if result.copied_count
            else f"目标目录已包含全部示例文件: {directory}"
        )

        return Modal(
            ModalTitle(title),
            ModalBody(
                P(summary, cls="text-green-600"),
                P(
                    f"已跳过 {result.skipped_count} 个同名文件，不会覆盖您的本地修改。",
                    cls="text-sm text-gray-500 mt-2",
                ),
                P(f"目标策略目录: {directory}", cls="text-sm text-gray-500 mt-2 break-all"),
            ),
            ModalFooter(
                Button(
                    "关闭",
                    type="button",
                    cls="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200",
                    onclick="location.reload()",
                ),
                Button(
                    "立即扫描",
                    type="button",
                    cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700",
                    hx_post="/strategy/scan/run",
                    hx_target="#modal-container",
                ),
            ),
            id="copy-example-modal",
        )
    except (ValueError, FileNotFoundError, NotADirectoryError) as e:
        return Modal(
            ModalTitle("复制失败"),
            ModalBody(
                P(str(e), cls="text-red-600"),
                P("请先检查当前用户策略目录配置。", cls="text-sm text-gray-500 mt-2"),
            ),
            ModalFooter(
                Button(
                    "去设置",
                    type="button",
                    cls="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700",
                    hx_get="/strategy/scan/config-modal",
                    hx_target="#modal-container",
                ),
            ),
            id="copy-example-error-modal",
        )
    except Exception as e:
        logger.error(f"Failed to copy example strategies: {e}")
        return Modal(
            ModalTitle("复制失败"),
            ModalBody(P(f"复制失败: {str(e)}", cls="text-red-600")),
            ModalFooter(
                Button(
                    "关闭",
                    type="button",
                    cls="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200",
                    onclick=STRATEGY_MODAL_CLOSE_JS,
                ),
            ),
            id="copy-example-error-modal",
        )
