"""回测成交对 K 线弹窗组件。

按成交对展示个股 K 线与买卖点：
- 初始化窗口回看买入日之前 120 根 K 线；
- 有卖出的成交对额外展示卖出日之后一个月的走势；
- K 线与均线均为前复权口径（复权锚点为该股票最新一根 K 线）；
- 右侧面板展示交易信息与决策特征取值。
"""

import bisect
import datetime
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import polars as pl
from fasthtml.common import Button, Div, P, Script, Span

from quantide.core.enums import OrderSide
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.trade_pairs import TradePair, build_trade_pairs
from quantide.web.components.asset_label import resolve_asset_name
from quantide.web.template_assets import render_asset

TRADE_KLINE_LOOKBACK_BARS = 120
TRADE_KLINE_POST_SELL_BARS = 20
TRADE_KLINE_HISTORY_CALENDAR_DAYS = 700
TRADE_KLINE_MA_PERIODS = (5, 10, 20, 30, 120, 250)
TRADE_KLINE_CHART_ID = "trade-kline-chart"
TRADE_KLINE_PANEL_ID = "trade-kline-panel"
TRADE_KLINE_FEATURE_LOOKBACK_DAYS = 150
TRADE_KLINE_PANEL_SUMMARY = "summary"
TRADE_KLINE_PANEL_BUY = "buy"
TRADE_KLINE_PANEL_SELL = "sell"

TRADE_KLINE_PANEL_LABELS = {
    TRADE_KLINE_PANEL_SUMMARY: "摘要",
    TRADE_KLINE_PANEL_BUY: "买入归因",
    TRADE_KLINE_PANEL_SELL: "卖出归因",
}


def _resolve_trade_attribution(
    active_panel: str,
    asset: str,
    buy_attribution: dict[str, Any] | None,
    buy_dt: datetime.date,
    pair: TradePair,
    portfolio_id: str,
    sell_attribution: dict[str, Any] | None,
    sell_dt: datetime.date | None,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve trade attribution."""
    if active_panel == TRADE_KLINE_PANEL_BUY:
        buy_attribution = _decision_attribution(portfolio_id, asset, buy_dt, pair.buy_tm)
        if buy_attribution is None:
            active_panel = TRADE_KLINE_PANEL_SUMMARY
    elif active_panel == TRADE_KLINE_PANEL_SELL and sell_dt is not None:
        sell_attribution = _decision_attribution(portfolio_id, asset, sell_dt, pair.sell_tm)
        if sell_attribution is None:
            active_panel = TRADE_KLINE_PANEL_SUMMARY
    return active_panel, buy_attribution, sell_attribution


def _portfolio_supports_attribution(portfolio_id: str) -> bool:
    """该回测所用策略是否支持逐次预测归因。"""
    from quantide.service.attribution import supports_attribution
    from quantide.service.discovery import strategy_loader

    portfolio = db.get_portfolio(portfolio_id)
    if portfolio is None:
        return False
    strategy_cls = strategy_loader.load_from_cache().get(portfolio.name or "")
    return supports_attribution(strategy_cls)


def _signal_date_for(
    decision_date: datetime.date, decision_tm: datetime.datetime | None
) -> datetime.date:
    """推算决策时可��的因子日期。

    开盘决策（09:30 及之前）只能用上一交易日的完整 K 线；盘中决策
    （如 14:55 的障碍止损）可以用当日 K 线。
    """
    from quantide.data.models.calendar import calendar

    if decision_tm is not None and decision_tm.time() > datetime.time(9, 30):
        return decision_date
    try:
        return calendar.day_shift(decision_date, -1)
    except Exception:
        return decision_date - datetime.timedelta(days=1)


def _decision_attribution(
    portfolio_id: str,
    asset: str,
    decision_date: datetime.date,
    decision_tm: datetime.datetime | None = None,
) -> dict[str, Any] | None:
    """计算某次决策的预测归因（按策略能力动态加载）。"""
    from quantide.service.attribution import explain_prediction

    signal_date = _signal_date_for(decision_date, decision_tm)
    return explain_prediction(portfolio_id, asset, signal_date)


def _trade_date(tm: object) -> datetime.date | None:
    """从成交时间中提取交易日。"""
    if isinstance(tm, datetime.datetime):
        return tm.date()
    if isinstance(tm, datetime.date):
        return tm
    if isinstance(tm, str):
        try:
            return datetime.datetime.fromisoformat(tm).date()
        except ValueError:
            return None
    return None


def _load_raw_bars(asset: str, start: datetime.date, end: datetime.date) -> pl.DataFrame:
    """加载区间内的原始日线（含复权因子）。"""
    df = daily_bars.get_bars_in_range(
        start,
        end,
        assets=[asset],
        adjust=None,
        eager_mode=True,
    )
    if isinstance(df, pl.LazyFrame):
        df = df.collect()
    if df is None or df.height == 0:
        return pl.DataFrame()
    if "adjust" not in df.columns:
        df = df.with_columns(pl.lit(1.0).alias("adjust"))
    return df.with_columns(pl.col("date").cast(pl.Date).alias("date")).sort("date")


def _qfq_frame(raw: pl.DataFrame) -> tuple[pl.DataFrame, float]:
    """把原始日线换算为前复权口径。

    Args:
        raw: 含 ``adjust`` 复权因子的原始日线。

    Returns:
        tuple: (前复权日线, 复权锚点因子)。
    """
    if raw.is_empty():
        return raw, 1.0
    anchor = float(raw["adjust"][-1] or 1.0) or 1.0
    df = raw.with_columns(
        [
            (pl.col("adjust") / anchor * pl.col("open")).alias("open"),
            (pl.col("adjust") / anchor * pl.col("high")).alias("high"),
            (pl.col("adjust") / anchor * pl.col("low")).alias("low"),
            (pl.col("adjust") / anchor * pl.col("close")).alias("close"),
        ]
    )
    return df, anchor


def _qfq_price(
    raw: pl.DataFrame,
    anchor: float,
    price: float,
    day: datetime.date | None,
) -> float:
    """把成交价换算到前复权口径。"""
    if raw.is_empty() or not day:
        return price
    factor_rows = raw.filter(pl.col("date") <= pl.lit(day))
    if factor_rows.is_empty():
        return price
    factor = float(factor_rows["adjust"][-1] or 1.0) or 1.0
    return price * factor / anchor


def _build_markers(
    portfolio_id: str,
    asset: str,
    raw: pl.DataFrame,
    anchor: float,
    buy_tid: str,
    sell_tid: str | None,
) -> list[dict[str, Any]]:
    """收集该股票在窗口内的买卖点（换算到前复权口径）。"""
    markers: list[dict[str, Any]] = []
    trades_df = db.trades_all(portfolio_id)
    if trades_df is None or trades_df.is_empty():
        return markers
    for row in trades_df.filter(pl.col("asset") == asset).iter_rows(named=True):
        trade_dt = _trade_date(row.get("tm"))
        if trade_dt is None:
            continue
        side_value = int(row.get("side") or 0)
        tid = str(row.get("tid") or "")
        markers.append(
            {
                "tid": tid,
                "dt": trade_dt.isoformat(),
                "price": _qfq_price(raw, anchor, float(row.get("price") or 0), trade_dt),
                "raw_price": float(row.get("price") or 0),
                "shares": float(row.get("shares") or 0),
                "side": "sell" if side_value == int(OrderSide.SELL) else "buy",
                "side_value": side_value,
                "current": tid in {buy_tid, sell_tid},
                "focus": tid == buy_tid,
            }
        )
    markers.sort(key=lambda item: item["dt"])
    return markers


def _find_pair(
    portfolio_id: str,
    buy_tid: str,
    sell_tid: str | None,
) -> TradePair | None:
    """在成交对列表中定位目标成交对。"""
    for pair in build_trade_pairs(portfolio_id):
        if pair.buy_tid == buy_tid and (sell_tid is None or pair.sell_tid == sell_tid):
            return pair
    return None


def build_trade_kline_payload(
    portfolio_id: str,
    buy_tid: str,
    sell_tid: str | None = None,
    panel: str = TRADE_KLINE_PANEL_SUMMARY,
) -> dict[str, Any] | None:
    """Build a pair chart from a visible price window and optional attribution."""
    pair = _find_pair(portfolio_id, buy_tid, sell_tid)
    if pair is None:
        return None
    buy_dt = _trade_date(pair.buy_tm)
    sell_dt = _trade_date(pair.sell_tm) if pair.sell_tm else None
    if buy_dt is None:
        return None
    window = _trade_chart_window(pair.asset, buy_dt, sell_dt)
    if window is None:
        return None
    bars = [_chart_bar(row) for row in window.frame.iter_rows(named=True)]
    markers = _build_markers(
        portfolio_id, pair.asset, window.raw, window.anchor, buy_tid, pair.sell_tid
    )
    if bars:
        markers = [marker for marker in markers if marker["dt"] >= bars[0]["dt"]]
    return {
        "asset": pair.asset,
        "name": resolve_asset_name(pair.asset),
        "pair": _pair_chart_values(pair, buy_dt, sell_dt),
        "bars": bars,
        "markers": markers,
        "ma_periods": list(TRADE_KLINE_MA_PERIODS),
        "lookback_bars": TRADE_KLINE_LOOKBACK_BARS,
        "initial_bars": len(bars),
        "post_trend_bars": window.post_count,
        "post_start_dt": bars[len(bars) - window.post_count]["dt"] if window.post_count else "",
        "post_sell_trend": sell_dt is not None,
        **_trade_attribution_payload(portfolio_id, pair, panel, buy_dt, sell_dt),
    }


def _chart_script(payload: dict[str, Any]) -> str:
    """生成 ECharts 初始化脚本。"""
    bars = payload.get("bars") or []
    dates = [bar["dt"] for bar in bars]
    ohlc = [[bar["open"], bar["close"], bar["low"], bar["high"]] for bar in bars]
    volumes = [bar["volume"] for bar in bars]
    ma_periods = payload.get("ma_periods") or list(TRADE_KLINE_MA_PERIODS)
    ma_series = {
        str(period): [
            None if bar["ma"].get(str(period)) is None else round(bar["ma"][str(period)], 4)
            for bar in bars
        ]
        for period in ma_periods
    }
    markers = payload.get("markers") or []
    buy_points, sell_points, marker_map = _chart_markers(markers, dates)

    post_start_dt = payload.get("post_start_dt") or ""
    mark_area: list[list[dict[str, str]]] = []
    if post_start_dt and post_start_dt in dates:
        post_dates = [dt for dt in dates if dt >= post_start_dt]
        if post_dates:
            mark_area = [[{"xAxis": post_dates[0]}, {"xAxis": post_dates[-1]}]]

    legend = ["K线", "成交量", "买入", "卖出"] + [f"MA{p}" for p in ma_periods]

    return render_asset(
        "trade-kline.js.tmpl",
        TRADE_KLINE_CHART_ID=TRADE_KLINE_CHART_ID,
        value_1=json.dumps(dates),
        value_2=json.dumps(ohlc),
        value_3=json.dumps(volumes),
        value_4=json.dumps([round(bar.get("pct") or 0, 4) for bar in bars]),
        ma_series_js=json.dumps(ma_series),
        value_6=json.dumps(marker_map),
        value_7=json.dumps([str(p) for p in ma_periods]),
        value_8=json.dumps(mark_area),
        value_9=json.dumps(buy_points, ensure_ascii=False),
        value_10=json.dumps(sell_points, ensure_ascii=False),
        legend_js=json.dumps(legend),
    )


def _format_number(value: object, digits: int = 2) -> str:
    """格式化面板数值。"""
    if value is None:
        return "—"
    try:
        return f"{float(cast(float | int | str, value)):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _panel_row(label: str, value: str) -> Any:
    """构建面板的一行（标签 + 数值）。"""
    return Div(
        Span(label, cls="text-xs text-gray-500 truncate"),
        Span(value, cls="text-xs text-gray-900 font-medium text-right tabular-nums"),
        cls="flex items-center justify-between gap-2 py-0.5",
    )


def _render_summary_panel(payload: dict[str, Any]) -> Any:
    """构建「摘要」面板：只显示交易信息。"""
    pair = payload.get("pair") or {}
    trade_rows = [
        _panel_row("买入日期", str(pair.get("buy_dt") or "—")),
        _panel_row("卖出日期", str(pair.get("sell_dt") or "持仓中")),
        _panel_row("买入价(实际成交)", _format_number(pair.get("buy_price"))),
        _panel_row("卖出价(实际成交)", _format_number(pair.get("sell_price"))),
        _panel_row("买入金额", _format_number(pair.get("buy_amount"))),
        _panel_row("费用", _format_number(pair.get("fee"))),
    ]
    if pair.get("status") == "closed":
        rate = pair.get("return_rate")
        trade_rows.append(
            _panel_row("收益率", "—" if rate is None else f"{float(rate) * 100:.2f}%")
        )
        trade_rows.append(
            _panel_row(
                "持仓天数",
                "—" if pair.get("holding_days") is None else str(pair.get("holding_days")),
            )
        )
    else:
        trade_rows.append(_panel_row("浮动盈亏", _format_number(pair.get("unrealized_pnl"))))
    return Div(
        Div("交易信息", cls="text-xs font-semibold text-gray-700 mb-1"),
        *trade_rows,
    )


def _render_panel_tabs(payload: dict[str, Any], tab_urls: dict[str, str] | None) -> Any:
    """构建右侧面板的页签条。"""
    available = payload.get("available_panels") or [TRADE_KLINE_PANEL_SUMMARY]
    active = payload.get("active_panel") or TRADE_KLINE_PANEL_SUMMARY
    tabs: list[Any] = []
    for key in available:
        label = TRADE_KLINE_PANEL_LABELS.get(key, key)
        if key == active:
            tabs.append(
                Span(
                    label,
                    cls="px-2 py-1 text-xs font-semibold text-white bg-gray-700 rounded",
                )
            )
            continue
        url = (tab_urls or {}).get(key)
        if not url:
            tabs.append(Span(label, cls="px-2 py-1 text-xs text-gray-500"))
            continue
        tabs.append(
            Button(
                label,
                type="button",
                hx_get=url,
                hx_target="#modal-container",
                cls=(
                    "px-2 py-1 text-xs text-gray-600 border border-gray-300 rounded "
                    "hover:bg-gray-100"
                ),
            )
        )
    return Div(*tabs, cls="flex items-center gap-1 mb-2")


def _render_attribution_panel(attribution: dict[str, Any], title: str) -> Any:
    """构建归因面板：概览 + 特征（名称/特征值/归因权重）。"""
    rows: list[Any] = [
        _panel_row("决策日", str(attribution.get("date", ""))),
        _panel_row("模型", str(attribution.get("engine", ""))),
        _panel_row("最终得分", f"{float(attribution.get('score') or 0):+.4f}"),
        _panel_row(
            "截面排名",
            f"#{attribution.get('rank')} / {attribution.get('cross_section')}",
        ),
        _panel_row("基线分", f"{float(attribution.get('baseline') or 0):+.4f}"),
    ]
    feature_rows = [
        Div(
            Span(item["name"], cls="text-xs text-gray-600 truncate"),
            Span(
                "—" if item.get("value") is None else f"{float(item['value']):+.4f}",
                cls="text-xs text-gray-400 text-right tabular-nums w-20",
            ),
            Span(
                f"{float(item.get('total') or 0):+.4f}",
                cls="text-xs text-gray-900 font-medium text-right tabular-nums w-20",
            ),
            cls="flex items-center justify-between gap-2 py-0.5 border-b border-gray-100",
        )
        for item in attribution.get("features") or []
    ]
    return Div(
        Div(title, cls="text-xs font-semibold text-gray-700 mb-1"),
        *rows,
        Div(
            "特征 / 特征值 / 归因权重",
            cls="text-xs font-semibold text-gray-700 mb-1 mt-2",
        ),
        *feature_rows,
    )


def _render_active_panel(payload: dict[str, Any]) -> Any:
    """渲染当前页签的内容。"""
    active = payload.get("active_panel") or TRADE_KLINE_PANEL_SUMMARY
    if active == TRADE_KLINE_PANEL_BUY and payload.get("buy_attribution"):
        return _render_attribution_panel(payload["buy_attribution"], "买入归因")
    if active == TRADE_KLINE_PANEL_SELL and payload.get("sell_attribution"):
        return _render_attribution_panel(payload["sell_attribution"], "卖出归因")
    return _render_summary_panel(payload)


def render_trade_kline_chart(
    payload: dict[str, Any], tab_urls: dict[str, str] | None = None
) -> Any:
    """渲染 K 线图容器与右侧信息面板。

    Args:
        payload: :func:`build_trade_kline_payload` 生成的数据。
        tab_urls: 各页签对应的弹窗 URL（由页面层提供）。

    Returns:
        Any: 可直接放入弹窗主体的节点。
    """
    bars = payload.get("bars") or []
    pair = payload.get("pair") or {}

    if not bars:
        return Div(
            Div(
                Span(
                    f"{payload.get('name', '')} {payload.get('asset', '')}",
                    cls="text-sm font-semibold text-gray-900",
                ),
                Span(
                    f"｜{str(pair.get('buy_tm', ''))[:19]} 买入",
                    cls="text-sm text-gray-600 ml-2",
                ),
                cls="flex items-center flex-wrap gap-1",
            ),
            P("该区间没有行情数据，无法绘制 K 线。", cls="text-sm text-gray-500 py-8 text-center"),
        )

    summary = Div(
        Span(
            f"K 线与均线为前复权口径，共 {len(bars)} 根"
            + (
                (
                    "（主窗口 "
                    f"{payload.get('lookback_bars', 0)}"
                    " 根 + 卖出后 "
                    f"{payload.get('post_trend_bars', 0)}"
                    " 根）"
                )
                if payload.get("post_sell_trend")
                else f"（回看 {payload.get('lookback_bars', 0)} 根）"
            ),
            cls="text-xs text-gray-500",
        ),
        cls="flex items-center flex-wrap gap-1 mb-3",
    )

    return Div(
        summary,
        Div(
            Div(id=TRADE_KLINE_CHART_ID, cls="w-full h-[520px]"),
            Div(
                _render_panel_tabs(payload, tab_urls),
                Div(
                    _render_active_panel(payload),
                    cls="max-h-[478px] overflow-y-auto pr-1",
                ),
                id=TRADE_KLINE_PANEL_ID,
                cls="w-80 shrink-0 pl-3 border-l border-gray-200",
            ),
            cls="flex gap-2 items-start",
        ),
        Script(_chart_script(payload)),
    )


@dataclass
class _TradeChartWindow:
    raw: pl.DataFrame
    frame: pl.DataFrame
    anchor: float
    post_count: int


def _trade_chart_window(
    asset: str, buy_dt: datetime.date, sell_dt: datetime.date | None
) -> _TradeChartWindow | None:
    """Compute indicators on full history before clipping the visible trade window."""
    history_start = buy_dt - datetime.timedelta(days=TRADE_KLINE_HISTORY_CALENDAR_DAYS)
    raw = _load_raw_bars(asset, history_start, max(daily_bars.end or buy_dt, buy_dt))
    if raw.is_empty():
        raw = _load_raw_bars(asset, history_start, buy_dt)
    if raw.is_empty():
        return None
    qfq, anchor = _qfq_frame(raw)
    end = buy_dt if sell_dt is None else max(sell_dt, buy_dt)
    pre = qfq.filter(pl.col("date") <= pl.lit(end))
    start = (
        pre.row(max(0, pre.height - TRADE_KLINE_LOOKBACK_BARS), named=True)["date"]
        if pre.height
        else end
    )
    qfq = _chart_indicators(qfq)
    frame = qfq.filter(
        (pl.col("date") >= pl.lit(min(buy_dt, start))) & (pl.col("date") <= pl.lit(end))
    )
    post = (
        qfq.filter(pl.col("date") > pl.lit(end)).head(TRADE_KLINE_POST_SELL_BARS)
        if sell_dt
        else qfq.head(0)
    )
    return _TradeChartWindow(raw, pl.concat([frame, post]), anchor, post.height)


def _chart_indicators(qfq: pl.DataFrame) -> pl.DataFrame:
    return qfq.with_columns(
        [
            pl.col("close")
            .rolling_mean(window_size=period, min_samples=period)
            .over("asset")
            .alias(f"ma{period}")
            for period in TRADE_KLINE_MA_PERIODS
        ]
    ).with_columns(
        ((pl.col("close") / pl.col("close").shift(1).over("asset") - 1.0) * 100.0)
        .fill_null(0.0)
        .alias("pct")
    )


def _chart_bar(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dt": str(row.get("date")),
        **{
            key: float(row.get(key) or 0)
            for key in ("open", "high", "low", "close", "volume", "pct")
        },
        "ma": {str(period): row.get(f"ma{period}") for period in TRADE_KLINE_MA_PERIODS},
    }


def _pair_chart_values(
    pair: TradePair, buy_dt: datetime.date, sell_dt: datetime.date | None
) -> dict[str, Any]:
    return {
        "buy_tid": pair.buy_tid,
        "sell_tid": pair.sell_tid,
        "buy_tm": str(pair.buy_tm),
        "sell_tm": str(pair.sell_tm) if pair.sell_tm else "",
        "buy_dt": buy_dt.isoformat(),
        "sell_dt": sell_dt.isoformat() if sell_dt else "",
        "shares": pair.shares,
        "buy_price": pair.buy_price,
        "sell_price": pair.sell_price,
        "buy_amount": pair.buy_amount,
        "sell_amount": pair.sell_amount,
        "fee": pair.fee,
        "pnl": pair.pnl,
        "return_rate": pair.return_rate,
        "holding_days": pair.holding_days,
        "status": pair.status,
        "unrealized_pnl": pair.unrealized_pnl,
    }


def _trade_attribution_payload(
    portfolio_id: str,
    pair: TradePair,
    panel: str,
    buy_dt: datetime.date,
    sell_dt: datetime.date | None,
) -> dict[str, Any]:
    panels = [TRADE_KLINE_PANEL_SUMMARY]
    if _portfolio_supports_attribution(portfolio_id):
        panels.append(TRADE_KLINE_PANEL_BUY)
        if sell_dt is not None:
            panels.append(TRADE_KLINE_PANEL_SELL)
    active = panel if panel in panels else TRADE_KLINE_PANEL_SUMMARY
    active, buy, sell = _resolve_trade_attribution(
        active, pair.asset, None, buy_dt, pair, portfolio_id, None, sell_dt
    )
    return {
        "buy_attribution": buy,
        "sell_attribution": sell,
        "available_panels": panels,
        "active_panel": active,
    }


def _marker_point(
    marker: Mapping[str, Any], dates: Sequence[str], date_index: Mapping[str, int]
) -> dict[str, Any] | None:
    """Align a trade marker to its visible bar without inventing out-of-range trades."""
    index = date_index.get(marker["dt"])
    if index is None:
        position = bisect.bisect_right(dates, marker["dt"]) - 1
        if position < 0:
            return None
        if position == len(dates) - 1 and marker["dt"] > dates[-1] and not marker.get("current"):
            return None
        index = position
    point: dict[str, Any] = {"value": [index, marker["price"]], "trade": marker}
    if marker.get("focus"):
        point["label"] = {
            "show": True,
            "formatter": "本次买入",
            "position": "top",
            "color": "#111827",
            "fontSize": 10,
            "fontWeight": "bold",
        }
    elif marker.get("current"):
        point["label"] = {
            "show": True,
            "formatter": "本次卖出",
            "position": "bottom",
            "color": "#111827",
            "fontSize": 10,
            "fontWeight": "bold",
        }
    return point


def _chart_markers(
    markers: Sequence[Mapping[str, Any]], dates: Sequence[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[Mapping[str, Any]]]]:
    date_index = {dt: index for index, dt in enumerate(dates)}
    buy_points: list[Any] = []
    sell_points: list[Any] = []
    marker_map: dict[Any, list[Any]] = {}
    for marker in markers:
        point = _marker_point(marker, dates, date_index)
        if point is None:
            continue
        (buy_points if marker["side"] == "buy" else sell_points).append(point)
        marker_map.setdefault(marker["dt"], []).append(marker)
    return buy_points, sell_points, marker_map
