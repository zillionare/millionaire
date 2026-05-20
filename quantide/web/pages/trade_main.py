"""交易主页面 - 符合 livetrade-default.html 原型。

包含：
1. 资产信息条
2. 闪电交易面板
3. 持仓明细
4. 当日委托
"""

import datetime

import polars as pl
from fasthtml.common import *
from fasthtml.common import Select as _Select
from monsterui.all import *
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from quantide.core.enums import BrokerKind, OrderSide, OrderStatus
from quantide.data.fetchers.registry import get_data_fetcher
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.stocks import stock_list
from quantide.data.sqlite import Order, Position
from quantide.service.registry import BrokerRegistry
from quantide.web.layouts.main import MainLayout


def _get_registry(req) -> BrokerRegistry:
    return req.scope.get("registry")


def _get_all_accounts(reg: BrokerRegistry) -> list[dict]:
    """获取所有账号列表"""
    accounts = []
    for kind in [BrokerKind.QMT, BrokerKind.SIMULATION]:
        for info in reg.list_by_kind(kind):
            accounts.append({
                "id": info.get("id"),
                "name": info.get("name") or info.get("id"),
                "kind": kind.value,
                "label": "实盘" if kind == BrokerKind.QMT else "仿真",
                "status": info.get("status", False),
                "is_live": kind == BrokerKind.QMT,
            })
    return accounts


def _get_active_account(reg: BrokerRegistry, session: dict) -> dict | None:
    """获取当前活动账号"""
    kind_str = session.get("active_account_kind")
    account_id = session.get("active_account_id")

    if not kind_str or not account_id:
        default = reg.get_default() if reg else None
        if not default:
            return None
        kind_str, account_id = default

    kind = BrokerKind(kind_str) if isinstance(kind_str, str) else kind_str
    broker = reg.get(kind, account_id) if reg else None

    if broker:
        name = ""
        status = True
        if hasattr(broker, "portfolio_name"):
            name = broker.portfolio_name
        if hasattr(broker, "status"):
            status = broker.status
        return {
            "id": account_id,
            "name": name or account_id,
            "kind": kind_str if isinstance(kind_str, str) else kind_str.value,
            "label": "实盘" if (kind == BrokerKind.QMT or kind_str == BrokerKind.QMT.value) else "仿真",
            "status": status,
            "is_live": kind == BrokerKind.QMT or kind_str == BrokerKind.QMT.value,
        }
    return None


def _format_trade_metric(value: float | None) -> str:
    """Format a trade metric for compact UI display.

    Args:
        value: The numeric value to format.

    Returns:
        A two-decimal string, or an empty string when unavailable.
    """
    if value is None:
        return ""
    return f"{value:.2f}"


def _extract_recent_trade_dates(
    calendar_frame, end: datetime.date, periods: int
) -> list[datetime.date]:
    """Extract recent open trade dates from a fetcher calendar response.

    Args:
        calendar_frame: Calendar data returned by the data fetcher.
        end: Preferred end date for the lookup window.
        periods: Number of dates to keep.

    Returns:
        A sorted list of recent trade dates.
    """
    if calendar_frame is None or calendar_frame.empty:
        return []

    dates: list[datetime.date] = []
    for index, row in calendar_frame.iterrows():
        if not bool(row.get("is_open", 1)):
            continue
        raw_date = row.get("date", index)
        if hasattr(raw_date, "date"):
            raw_date = raw_date.date()
        dates.append(raw_date)

    if not dates:
        return []

    dates = sorted(set(dates))
    eligible_dates = [trade_date for trade_date in dates if trade_date <= end]
    return (eligible_dates or dates)[-periods:]


def _resolve_trade_reference_dates(
    fetcher, end: datetime.date, periods: int
) -> list[datetime.date]:
    """Resolve fallback trade dates for the trade panel.

    Args:
        fetcher: Active market data fetcher.
        end: Preferred end date.
        periods: Number of trade dates to retrieve.

    Returns:
        A list of trade dates for fetcher fallback queries.
    """
    start = end - datetime.timedelta(days=periods * 3)
    try:
        trade_dates = calendar.get_trade_dates(start, end)[-periods:]
    except Exception:
        trade_dates = []
    if trade_dates:
        return trade_dates

    lookback_start = end - datetime.timedelta(days=max(periods * 30, 365 * 3))
    try:
        calendar_frame = fetcher.fetch_calendar(lookback_start)
    except Exception:
        return [end]

    resolved_dates = _extract_recent_trade_dates(calendar_frame, end, periods)
    return resolved_dates or [end]


def _build_asset_stats(asset: str) -> dict[str, str | bool]:
    """Build reference price stats for the selected asset.

    Args:
        asset: The selected stock code.

    Returns:
        A payload suitable for the trade reference panel.
    """
    payload: dict[str, str | bool] = {
        "visible": False,
        "close": "",
        "ma5": "",
        "ma10": "",
        "ma20": "",
        "ma30": "",
        "ma60": "",
        "current": "",
    }
    bars = _load_trade_reference_bars(asset, datetime.date.today(), 60)
    if bars.is_empty():
        return payload

    ordered = bars.sort("date")
    closes = [float(value) for value in ordered.get_column("close").to_list()]
    if not closes:
        return payload

    payload["visible"] = True
    payload["close"] = _format_trade_metric(closes[-1])
    payload["current"] = _format_trade_metric(closes[-1])
    for period in (5, 10, 20, 30, 60):
        if len(closes) >= period:
            payload[f"ma{period}"] = _format_trade_metric(sum(closes[-period:]) / period)
    return payload


def _load_trade_reference_bars(
    asset: str, end: datetime.date, periods: int
) -> pl.DataFrame:
    """Load recent bars for the trade panel from local storage or fetcher fallback.

    Args:
        asset: Stock code.
        end: End date.
        periods: Number of trade dates to retrieve.

    Returns:
        A date-sorted Polars DataFrame.
    """
    try:
        bars = daily_bars.get_bars(periods, end=end, assets=[asset], eager_mode=True, adjust=None)
    except Exception:
        bars = pl.DataFrame()
    if not bars.is_empty():
        return bars.sort("date")

    try:
        fetcher = get_data_fetcher()
        trade_dates = _resolve_trade_reference_dates(fetcher, end, periods)
        fallback_frame, _ = fetcher.fetch_bars_ext(trade_dates)
    except Exception:
        return pl.DataFrame()
    if fallback_frame is None or fallback_frame.empty:
        return pl.DataFrame()

    fallback = pl.from_pandas(fallback_frame).filter(pl.col("asset") == asset)
    if fallback.is_empty():
        return fallback
    return fallback.with_columns(pl.col("date").cast(pl.Date)).sort("date")


def _trade_result_has_order(result) -> bool:
    """Return whether a broker call produced an actual order.

    Args:
        result: Broker trade result object.

    Returns:
        True when an order id or trade rows are present.
    """
    if result is None:
        return False
    if getattr(result, "qt_oid", None):
        return True
    trades = getattr(result, "trades", None) or []
    return len(trades) > 0


def AssetInfoBar(total: float = 0, cash: float = 0, market_value: float = 0):
    """资产信息条"""
    cash_ratio = (cash / total * 100) if total > 0 else 0
    position_ratio = (market_value / total * 100) if total > 0 else 0

    return Div(
        Div(
            Div(
                Span("总资产", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(f"{total/10000:.2f}万", cls="font-bold text-gray-900 dark:text-white text-base ml-2"),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("现金", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(f"{cash/10000:.2f}万", cls="font-bold text-gray-900 dark:text-white text-base ml-2"),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("现金比", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(f"{cash_ratio:.1f}%", cls="font-bold text-gray-900 dark:text-white text-base ml-2"),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("市值", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(f"{market_value/10000:.2f}万", cls="font-bold text-gray-900 dark:text-white text-base ml-2"),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("仓位", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(f"{position_ratio:.1f}%", cls="font-bold text-gray-900 dark:text-white text-base ml-2"),
                cls="flex items-center space-x-2",
            ),
            cls="flex items-center justify-between text-sm px-6 py-4",
        ),
        cls="bg-white dark:bg-gray-800 rounded-lg shadow mb-6",
    )


def LightningTradePanel(portfolio_id: str, kind: str, cash: float = 0, total: float = 0):
    """闪电交易面板 - 符合 spec 的下单键盘"""
    # 收紧输入区尺寸，并把更多宽度让给中间 speed dial 键盘。
    input_cls = "flex-1 px-3 h-9 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-red-500 dark:bg-gray-700 dark:text-white text-sm"
    select_cls = "px-2 h-9 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-red-500 dark:bg-gray-700 dark:text-white text-sm"
    metric_row_cls = "grid grid-cols-[88px_minmax(0,1fr)] items-center gap-2 mb-2"
    # radio button 使用原生样式，避免 MonsterUI 的 uk-input 边框
    radio_cls = "w-4 h-4 text-red-600 focus:ring-red-500 cursor-pointer"

    # Search icon SVG
    search_svg = NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<circle cx="11" cy="11" r="8"></circle>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>'
    )

    return Div(
        Form(
            Div(
                # 左边：下单输入区（2/5）
                Div(
                    # Row 1: Code input with search button
                    Div(
                        Input(
                            type="text",
                            name="asset_display",
                            placeholder="请输入股票名、拼音或者代码",
                            cls=f"{input_cls} rounded-r-none text-sm",
                            id="asset-display",
                            autocomplete="off",
                            hx_get="/trade/search",
                            hx_trigger="input changed delay:200ms",
                            hx_target="#asset-search-dropdown",
                            hx_swap="outerHTML",
                            hx_vals='js:{"q": document.getElementById("asset-display").value}',
                        ),
                        Button(
                            search_svg,
                            type="button",
                            cls="px-3 h-9 border border-l-0 border-gray-300 dark:border-gray-600 rounded-r-lg bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 flex items-center justify-center",
                        ),
                        Input(
                            type="hidden",
                            name="asset",
                            id="asset-code",
                        ),
                        Div(id="asset-search-dropdown", cls="hidden absolute top-full left-0 right-0 z-50"),
                        cls="flex items-center mb-2 relative",
                    ),
                    # Row 2: Price mode + Price (use _Select to avoid MonsterUI Uk_select)
                    Div(
                        _Select(
                            Option("限价", value="LIMIT", selected=True),
                            Option("市价", value="MARKET"),
                            name="price_mode",
                            cls=f"{select_cls} w-24 rounded-r-none",
                            id="price-mode-select",
                        ),
                        Div(
                            Input(
                                type="text",
                                name="price",
                                placeholder="价格",
                                cls=f"{input_cls} text-right text-base font-medium rounded-l-none",
                                id="price-input",
                            ),
                            Div(
                                "",
                                cls=(
                                    "pointer-events-none absolute right-1 top-full pt-1 text-right "
                                    "text-[80%] italic text-gray-500 dark:text-gray-400"
                                ),
                                id="price-change-hint",
                            ),
                            cls="relative flex-1",
                        ),
                        cls="flex items-start mb-6",
                    ),
                    # Row 3: Order mode radio buttons (raw ft_hx to avoid MonsterUI uk-input/uk-label borders)
                    Div(
                        ft_hx(
                            "label",
                            ft_hx(
                                "input",
                                type="radio",
                                name="order_mode",
                                value="AMOUNT",
                                checked="",
                                cls=radio_cls,
                                id="order-mode-amount",
                            ),
                            Span("按金额下单", cls="ml-1 text-xs text-gray-700 dark:text-gray-300"),
                            cls="flex items-center cursor-pointer h-8",
                        ),
                        ft_hx(
                            "label",
                            ft_hx(
                                "input",
                                type="radio",
                                name="order_mode",
                                value="QUANTITY",
                                cls=radio_cls,
                                id="order-mode-quantity",
                            ),
                            Span("按数量下单", cls="ml-1 text-xs text-gray-700 dark:text-gray-300"),
                            cls="flex items-center cursor-pointer h-8",
                        ),
                        cls="flex items-center gap-3 mb-2",
                    ),
                    # Row 4: Dynamic label input
                    Div(
                        Span(
                            "买入金额（万元）",
                            cls="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap",
                            id="value-label",
                        ),
                        Input(
                            type="text",
                            name="value",
                            placeholder="",
                            cls=f"{input_cls} text-right text-base font-medium",
                            id="value-input",
                        ),
                        cls=metric_row_cls,
                    ),
                    # Row 5: Estimated shares
                    Div(
                        Span("预估数量 (股)", cls="text-xs font-medium text-gray-700 dark:text-gray-300"),
                        Div(
                            "",
                            cls="px-3 h-9 flex w-full items-center justify-end text-sm font-medium text-gray-900 dark:text-white border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700",
                            id="est-shares",
                        ),
                        cls=metric_row_cls,
                    ),
                    # Row 6: Position fraction buttons (ordered: 1/4, 1/3, 1/2, 全仓)
                    Div(
                        Div(
                            Button(
                                "1/4",
                                type="button",
                                cls="pos-btn px-2 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 font-medium",
                                data_fraction="0.25",
                            ),
                            Button(
                                "1/3",
                                type="button",
                                cls="pos-btn px-2 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 font-medium",
                                data_fraction="0.3333",
                            ),
                            Button(
                                "1/2",
                                type="button",
                                cls="pos-btn px-2 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 font-medium",
                                data_fraction="0.5",
                            ),
                            Button(
                                "全仓",
                                type="button",
                                cls="pos-btn px-2 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 font-medium",
                                data_fraction="1.0",
                            ),
                            cls="grid grid-cols-4 gap-1.5",
                        ),
                        cls="mb-2",
                    ),
                    # Row 7: Buy/Sell buttons with active state
                    Div(
                        Input(type="hidden", name="side", value="BUY", id="side-input"),
                        Button(
                            Span("*", cls="absolute top-0 left-2 text-xs", id="buy-star"),
                            "买入",
                            type="button",
                            cls="relative bg-red-600 hover:bg-red-700 text-white font-bold py-2.5 px-4 rounded-lg text-base w-full",
                            id="btn-buy",
                            data_side="BUY",
                            aria_pressed="true",
                        ),
                        Button(
                            Span("*", cls="absolute top-0 left-2 text-xs hidden", id="sell-star"),
                            "卖出",
                            type="button",
                            cls="relative bg-green-600 hover:bg-green-700 text-white font-bold py-2.5 px-4 rounded-lg text-base w-full opacity-60",
                            id="btn-sell",
                            data_side="SELL",
                            aria_pressed="false",
                        ),
                        cls="grid grid-cols-2 gap-2 pt-1",
                    ),
                    # Hidden submit for HTMX
                    Input(type="submit", cls="hidden", id="form-submit"),
                    cls="w-[236px] flex-shrink-0 space-y-2",
                ),
                # 中间：价格快捷输入区
                Div(
                    # 4x5 价格快捷按钮网格
                    Div(
                        *[
                            Button(
                                Div(
                                    label,
                                    cls=(
                                        "text-sm font-medium leading-tight whitespace-nowrap"
                                        if abs(pct) == 0.10
                                        else "text-base font-medium leading-tight"
                                    ),
                                ),
                                Div("", cls="quick-price-display text-[11px] text-gray-400 leading-tight mt-0.5 min-h-4"),
                                type="button",
                                cls=(
                                    "quick-price-btn aspect-square w-full flex flex-col items-center justify-center "
                                    "bg-[#f9fafb] dark:bg-gray-800 rounded-lg shadow-sm transition-transform active:scale-[0.98] "
                                    + ("text-[#b71c1c]" if pct > 0 else "text-[#388e3c]")
                                ),
                                data_pct=str(pct),
                                data_market_order="true" if abs(pct) == 0.10 else "false",
                            )
                            for row in [
                                [("涨停", 0.10), ("5", 0.05), ("-1", -0.01), ("-6", -0.06)],
                                [("9", 0.09), ("4", 0.04), ("-2", -0.02), ("-7", -0.07)],
                                [("8", 0.08), ("3", 0.03), ("-3", -0.03), ("-8", -0.08)],
                                [("7", 0.07), ("2", 0.02), ("-4", -0.04), ("-9", -0.09)],
                                [("6", 0.06), ("1", 0.01), ("-5", -0.05), ("跌停", -0.10)],
                            ]
                            for label, pct in row
                        ],
                        cls="grid h-full w-[196px] grid-cols-4 gap-1",
                    ),
                    cls="flex shrink-0 items-stretch",
                ),
                # 右边：闪电单
                Div(
                    # Stats row
                    Div(
                        *[
                            Div(
                                Div(label, cls="text-[11px] text-gray-500 dark:text-gray-400 mb-1"),
                                Div("", cls="text-xs font-medium text-gray-700 dark:text-gray-300 min-h-4", id=f"ref-{key}"),
                                cls="bg-[#f9fafb] dark:bg-gray-700 rounded-md py-1.5 px-1 text-center flex-1 min-w-0",
                            )
                            for label, key in [
                                ("昨收", "close"),
                                ("MA5", "ma5"),
                                ("MA10", "ma10"),
                                ("MA20", "ma20"),
                                ("MA30", "ma30"),
                                ("MA60", "ma60"),
                                ("现价", "current"),
                            ]
                        ],
                        cls="flex gap-1 mb-2",
                        id="reference-price-panel",
                    ),
                    # List header
                    Div(
                        H3("闪电单", cls="text-base font-semibold text-gray-900 dark:text-white m-0"),
                        Div(
                            Button(
                                NotStr('<svg width="16" height="16" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'),
                                type="button",
                                cls="w-6 h-6 flex items-center justify-center border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-100",
                            ),
                            Button(
                                NotStr('<svg width="16" height="16" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none"><line x1="5" y1="12" x2="19" y2="12"></line></svg>'),
                                type="button",
                                cls="w-6 h-6 flex items-center justify-center border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-100",
                            ),
                            cls="flex gap-1",
                        ),
                        cls="flex items-center justify-between bg-[#e0e0e0] dark:bg-gray-600 px-4 py-2.5 rounded-t-lg",
                    ),
                    # Stock list
                    Div(
                        *[
                            Div(
                                Span(code, cls="text-xs font-bold text-gray-900 dark:text-white w-20"),
                                Div(Span(name, cls="text-xs text-gray-600 dark:text-gray-400"), cls="flex items-center"),
                                Span(tags, cls="text-[11px] text-gray-400 dark:text-gray-500 mr-2") if tags else Span("", cls="text-[11px] mr-2"),
                                Div(
                                    NotStr('<svg class="w-6 h-6 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l15-15Z"></path></svg>'),
                                    NotStr('<svg class="w-6 h-6 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><line x1="8" y1="12" x2="16" y2="12"></line></svg>'),
                                    cls="flex items-center",
                                ),
                                cls="grid grid-cols-[80px_1fr_auto_auto] items-center py-2.5 px-4 border-b border-gray-100 dark:border-gray-700 last:border-b-0 even:bg-[#f9fafb] dark:even:bg-gray-700/50",
                            )
                            for code, name, tags in [
                                ("600777", "新潮能源", "天然气、白酒、地产"),
                                ("000001", "新潮能源", ""),
                                ("000002", "新潮能源", ""),
                                ("000004", "新潮能源", ""),
                                ("000004", "新潮能源", ""),
                            ]
                        ],
                        cls="bg-white dark:bg-gray-800 rounded-b-lg",
                    ),
                    cls="flex-[0.95] space-y-0",
                ),
                cls="flex gap-3",
            ),
            Script(
                """
                (function() {
                    const form = document.getElementById('trade-form');
                    const priceMode = document.getElementById('price-mode-select');
                    const priceInput = document.getElementById('price-input');
                    const orderModeAmount = document.getElementById('order-mode-amount');
                    const orderModeQuantity = document.getElementById('order-mode-quantity');
                    const valueLabel = document.getElementById('value-label');
                    const valueInput = document.getElementById('value-input');
                    const estShares = document.getElementById('est-shares');
                    const sideInput = document.getElementById('side-input');
                    const btnBuy = document.getElementById('btn-buy');
                    const btnSell = document.getElementById('btn-sell');
                    const buyStar = document.getElementById('buy-star');
                    const sellStar = document.getElementById('sell-star');
                    const priceChangeHint = document.getElementById('price-change-hint');
                    const formSubmit = document.getElementById('form-submit');
                    const cash = parseFloat(form.dataset.cash) || 0;
                    const assetDisplay = document.getElementById('asset-display');
                    const assetCode = document.getElementById('asset-code');
                    let searchDropdown = document.getElementById('asset-search-dropdown');
                    const referenceValues = {
                        close: document.getElementById('ref-close'),
                        ma5: document.getElementById('ref-ma5'),
                        ma10: document.getElementById('ref-ma10'),
                        ma20: document.getElementById('ref-ma20'),
                        ma30: document.getElementById('ref-ma30'),
                        ma60: document.getElementById('ref-ma60'),
                        current: document.getElementById('ref-current'),
                    };
                    let selectedAssetStats = null;
                    let activeSearchIndex = -1;
                    let limitPlaceholderPrice = '';
                    let lastQuickPricePct = null;
                    let lastQuickPriceValue = '';

                    function refreshSearchDropdown() {
                        searchDropdown = document.getElementById('asset-search-dropdown');
                        return searchDropdown;
                    }

                    function getSearchItems() {
                        const dropdown = refreshSearchDropdown();
                        if (!dropdown) {
                            return [];
                        }
                        return Array.from(dropdown.querySelectorAll('.asset-search-item'));
                    }

                    function hideSearchDropdown() {
                        activeSearchIndex = -1;
                        const dropdown = refreshSearchDropdown();
                        if (!dropdown) {
                            return;
                        }
                        dropdown.classList.add('hidden');
                        dropdown.innerHTML = '';
                    }

                    function setActiveSearchIndex(index) {
                        const items = getSearchItems();
                        if (!items.length) {
                            activeSearchIndex = -1;
                            return;
                        }
                        const normalizedIndex = Math.max(0, Math.min(index, items.length - 1));
                        activeSearchIndex = normalizedIndex;
                        items.forEach(function(item, itemIndex) {
                            item.classList.toggle('bg-gray-100', itemIndex === normalizedIndex);
                            item.classList.toggle('dark:bg-gray-700', itemIndex === normalizedIndex);
                        });
                    }

                    function clearReferencePrices() {
                        selectedAssetStats = null;
                        limitPlaceholderPrice = '';
                        clearQuickPriceSelection();
                        Object.values(referenceValues).forEach(function(node) {
                            node.textContent = '';
                        });
                        updateLimitPricePlaceholder();
                        updatePriceChangeHint();
                    }

                    function updateCurrentReferencePrice() {
                        if (!selectedAssetStats) {
                            referenceValues.current.textContent = '';
                            return;
                        }
                        const currentPrice = parseFloat(priceInput.value);
                        if (!isNaN(currentPrice) && currentPrice > 0) {
                            referenceValues.current.textContent = currentPrice.toFixed(2);
                            return;
                        }
                        referenceValues.current.textContent = selectedAssetStats.current || '';
                    }

                    function clearQuickPriceSelection() {
                        lastQuickPricePct = null;
                        lastQuickPriceValue = '';
                    }

                    function getReferenceClosePrice() {
                        if (selectedAssetStats) {
                            const closePrice = parseFloat(selectedAssetStats.close || '');
                            if (!isNaN(closePrice) && closePrice > 0) {
                                return closePrice;
                            }
                        }
                        const placeholderPrice = parseFloat(limitPlaceholderPrice || '');
                        return !isNaN(placeholderPrice) && placeholderPrice > 0 ? placeholderPrice : 0;
                    }

                    function setLimitPlaceholderPrice(value) {
                        const parsed = parseFloat(value || '');
                        if (isNaN(parsed) || parsed <= 0) {
                            limitPlaceholderPrice = '';
                        } else {
                            limitPlaceholderPrice = parsed.toFixed(2);
                        }
                        updateLimitPricePlaceholder();
                    }

                    function updateLimitPricePlaceholder() {
                        if (priceMode.value === 'MARKET') {
                            priceInput.placeholder = '市价';
                            return;
                        }
                        priceInput.placeholder = limitPlaceholderPrice || '价格';
                    }

                    function updatePriceChangeHint() {
                        if (priceMode.value !== 'LIMIT') {
                            priceChangeHint.textContent = '';
                            return;
                        }
                        if (lastQuickPricePct !== null && priceInput.value === lastQuickPriceValue) {
                            const quickPct = lastQuickPricePct * 100;
                            const sign = quickPct > 0 ? '+' : '';
                            priceChangeHint.textContent = sign + quickPct.toFixed(2) + '%';
                            return;
                        }
                        const closePrice = parseFloat(selectedAssetStats && selectedAssetStats.close || '');
                        const limitPrice = parseFloat(priceInput.value);
                        if (isNaN(closePrice) || closePrice <= 0 || isNaN(limitPrice) || limitPrice <= 0) {
                            priceChangeHint.textContent = '';
                            return;
                        }
                        const deltaPct = ((limitPrice - closePrice) / closePrice) * 100;
                        const sign = deltaPct > 0 ? '+' : '';
                        priceChangeHint.textContent = sign + deltaPct.toFixed(2) + '%';
                    }

                    function applyReferencePrices(stats) {
                        if (!stats || !stats.visible) {
                            clearReferencePrices();
                            return;
                        }
                        selectedAssetStats = stats;
                        setLimitPlaceholderPrice(stats.current || stats.close || '');
                        referenceValues.close.textContent = stats.close || '';
                        referenceValues.ma5.textContent = stats.ma5 || '';
                        referenceValues.ma10.textContent = stats.ma10 || '';
                        referenceValues.ma20.textContent = stats.ma20 || '';
                        referenceValues.ma30.textContent = stats.ma30 || '';
                        referenceValues.ma60.textContent = stats.ma60 || '';
                        updateCurrentReferencePrice();
                    }

                    async function fetchAssetStats(asset) {
                        if (!asset) {
                            clearReferencePrices();
                            return;
                        }
                        try {
                            const response = await fetch('/trade/asset-stats?asset=' + encodeURIComponent(asset), {
                                headers: {'X-Requested-With': 'fetch'}
                            });
                            if (!response.ok) {
                                clearReferencePrices();
                                return;
                            }
                            const stats = await response.json();
                            if (assetCode.value !== asset) {
                                return;
                            }
                            applyReferencePrices(stats);
                        } catch (error) {
                            clearReferencePrices();
                        }
                    }

                    function updatePriceMode() {
                        if (priceMode.value === 'MARKET') {
                            priceInput.disabled = true;
                            priceInput.value = '';
                            priceInput.classList.add('bg-gray-100');
                        } else {
                            priceInput.disabled = false;
                            priceInput.classList.remove('bg-gray-100');
                        }
                        updateLimitPricePlaceholder();
                        updatePriceChangeHint();
                        updateEstShares();
                    }

                    function updateLabel() {
                        const side = sideInput.value;
                        const mode = document.querySelector('input[name="order_mode"]:checked').value;
                        if (side === 'BUY') {
                            valueLabel.textContent = mode === 'AMOUNT' ? '买入金额（万元）' : '买入手数';
                        } else {
                            valueLabel.textContent = mode === 'AMOUNT' ? '卖出金额（万元）' : '卖出手数';
                        }
                    }

                    function updateActiveSide() {
                        const side = sideInput.value;
                        if (side === 'BUY') {
                            buyStar.classList.remove('hidden');
                            btnBuy.classList.remove('opacity-60');
                            btnBuy.setAttribute('aria-pressed', 'true');
                            btnSell.classList.add('opacity-60');
                            btnSell.setAttribute('aria-pressed', 'false');
                            sellStar.classList.add('hidden');
                        } else {
                            buyStar.classList.add('hidden');
                            btnSell.classList.remove('opacity-60');
                            btnSell.setAttribute('aria-pressed', 'true');
                            btnBuy.classList.add('opacity-60');
                            btnBuy.setAttribute('aria-pressed', 'false');
                            sellStar.classList.remove('hidden');
                        }
                    }

                    function setOrderMode(mode) {
                        const useQuantity = mode === 'QUANTITY';
                        orderModeAmount.checked = !useQuantity;
                        orderModeQuantity.checked = useQuantity;
                    }

                    function resetTradeDraftForSideSwitch() {
                        setOrderMode('AMOUNT');
                        priceMode.value = 'LIMIT';
                        priceInput.value = '';
                        updatePriceMode();
                        valueInput.value = '';
                        updateLabel();
                        updateEstShares();
                        updateCurrentReferencePrice();
                        updateQuickPrices();
                    }

                    function activateTradeSide(nextSide, resetDraft) {
                        const changed = sideInput.value !== nextSide;
                        sideInput.value = nextSide;
                        updateActiveSide();
                        updateLabel();
                        if (changed && resetDraft) {
                            resetTradeDraftForSideSwitch();
                        }
                    }

                    function handleTradeSubmitIntent(nextSide) {
                        if (sideInput.value !== nextSide) {
                            activateTradeSide(nextSide, true);
                            return;
                        }
                        formSubmit.click();
                    }

                    function updateEstShares() {
                        const price = parseFloat(priceInput.value) || 0;
                        const value = parseFloat(valueInput.value) || 0;
                        const mode = document.querySelector('input[name="order_mode"]:checked').value;
                        const isMarket = priceMode.value === 'MARKET';

                        if ((price <= 0 && !isMarket) || value <= 0) {
                            estShares.textContent = '';
                            return;
                        }

                        let shares;
                        if (mode === 'AMOUNT') {
                            const amountYuan = value * 10000;
                            const p = isMarket ? 1 : price;
                            shares = Math.floor(amountYuan / p / 100) * 100;
                        } else {
                            shares = Math.floor(value) * 100;
                        }

                        estShares.textContent = shares > 0 ? (shares + ' 股') : '';
                    }

                    function getQuickPriceBase() {
                        return getReferenceClosePrice();
                    }

                    function setPosition(fraction) {
                        const price = parseFloat(priceInput.value) || 0;
                        const mode = document.querySelector('input[name="order_mode"]:checked').value;
                        const isMarket = priceMode.value === 'MARKET';

                        if (price <= 0 && !isMarket) return;

                        if (mode === 'AMOUNT') {
                            const amountYuan = cash * fraction;
                            valueInput.value = (amountYuan / 10000).toFixed(4).replace(/\\.?0+$/, '');
                        } else {
                            const p = isMarket ? 1 : price;
                            const amountYuan = cash * fraction;
                            const shares = Math.floor(amountYuan / p / 100) * 100;
                            valueInput.value = Math.floor(shares / 100);
                        }

                        updateEstShares();
                    }

                    // Event listeners
                    priceMode.addEventListener('change', updatePriceMode);
                    orderModeAmount.addEventListener('change', function() {
                        updateLabel();
                        updateEstShares();
                    });
                    orderModeQuantity.addEventListener('change', function() {
                        updateLabel();
                        updateEstShares();
                    });
                    valueInput.addEventListener('input', updateEstShares);
                    priceInput.addEventListener('input', updateEstShares);

                    btnBuy.addEventListener('click', function() {
                        handleTradeSubmitIntent('BUY');
                    });

                    btnSell.addEventListener('click', function() {
                        handleTradeSubmitIntent('SELL');
                    });

                    document.querySelectorAll('.pos-btn').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            setPosition(parseFloat(this.dataset.fraction));
                        });
                    });

                    // --- Asset search dropdown handlers ---
                    function selectAsset(item) {
                        assetDisplay.value = item.dataset.display;
                        assetCode.value = item.dataset.asset;
                        hideSearchDropdown();
                        // Auto-fill price if available
                        const price = item.dataset.price;
                        if (price && price !== '') {
                            setLimitPlaceholderPrice(price);
                        }
                        clearQuickPriceSelection();
                        priceInput.value = '';
                        updatePriceChangeHint();
                        updateEstShares();
                        updateQuickPrices();
                        fetchAssetStats(item.dataset.asset);
                    }

                    function hydrateTradeFromPosition(row) {
                        const asset = row.dataset.asset || '';
                        if (!asset) {
                            return;
                        }
                        assetDisplay.value = row.dataset.display || asset;
                        assetCode.value = asset;
                        hideSearchDropdown();
                        priceMode.value = 'LIMIT';
                        clearQuickPriceSelection();
                        priceInput.value = '';
                        updatePriceMode();
                        const rowPrice = parseFloat(row.dataset.price || '');
                        setLimitPlaceholderPrice(
                            !isNaN(rowPrice) && rowPrice > 0 ? rowPrice.toFixed(2) : ''
                        );
                        const availLots = parseFloat(row.dataset.availLots || '');
                        if (!isNaN(availLots) && availLots > 0) {
                            setOrderMode('QUANTITY');
                            valueInput.value = String(availLots);
                        } else {
                            setOrderMode('AMOUNT');
                            valueInput.value = '';
                        }
                        activateTradeSide('SELL', false);
                        updateLabel();
                        updateEstShares();
                        updateCurrentReferencePrice();
                        updateQuickPrices();
                        fetchAssetStats(asset);
                    }

                    document.body.addEventListener('htmx:afterSwap', function(evt) {
                        if (evt.detail.target.id === 'asset-search-dropdown') {
                            const dropdown = refreshSearchDropdown();
                            if (dropdown && dropdown.innerText.trim() !== '') {
                                dropdown.classList.remove('hidden');
                                setActiveSearchIndex(0);
                            }
                        }
                    });

                    document.body.addEventListener('click', function(evt) {
                        const sellTrigger = evt.target.closest('.position-sell-btn');
                        if (sellTrigger) {
                            evt.preventDefault();
                            evt.stopPropagation();
                            const positionRow = sellTrigger.closest('.trade-position-row');
                            if (positionRow) {
                                hydrateTradeFromPosition(positionRow);
                            }
                            return;
                        }
                        const item = evt.target.closest('.asset-search-item');
                        if (!item) {
                            return;
                        }
                        evt.preventDefault();
                        selectAsset(item);
                    });

                    document.body.addEventListener('dblclick', function(evt) {
                        const positionRow = evt.target.closest('.trade-position-row');
                        if (!positionRow) {
                            return;
                        }
                        evt.preventDefault();
                        hydrateTradeFromPosition(positionRow);
                    });

                    document.body.addEventListener('keydown', function(evt) {
                        const item = evt.target.closest('.asset-search-item');
                        if (!item || (evt.key !== 'Enter' && evt.key !== ' ')) {
                            return;
                        }
                        evt.preventDefault();
                        evt.stopPropagation();
                        selectAsset(item);
                    });

                    // Close dropdown when clicking outside
                    document.addEventListener('click', function(evt) {
                        const dropdown = refreshSearchDropdown();
                        if (!dropdown) {
                            return;
                        }
                        if (!assetDisplay.contains(evt.target) && !dropdown.contains(evt.target)) {
                            searchDropdown.classList.add('hidden');
                        }
                    });

                    // Clear hidden code when user manually edits display field
                    assetDisplay.addEventListener('input', function() {
                        assetCode.value = '';
                        clearReferencePrices();
                        priceInput.value = '';
                        if (assetDisplay.value.trim() === '') {
                            hideSearchDropdown();
                        }
                    });

                    assetDisplay.addEventListener('keydown', function(evt) {
                        const items = getSearchItems();
                        const dropdownVisible = !searchDropdown.classList.contains('hidden') && items.length > 0;
                        if (evt.key === 'Escape') {
                            evt.preventDefault();
                            hideSearchDropdown();
                            return;
                        }
                        if (evt.key === 'ArrowDown' && dropdownVisible) {
                            evt.preventDefault();
                            setActiveSearchIndex(activeSearchIndex + 1);
                            return;
                        }
                        if (evt.key === 'ArrowUp' && dropdownVisible) {
                            evt.preventDefault();
                            setActiveSearchIndex(activeSearchIndex - 1);
                            return;
                        }
                        if (evt.key !== 'Enter') {
                            return;
                        }
                        evt.preventDefault();
                        evt.stopPropagation();
                        if (!dropdownVisible) {
                            return;
                        }
                        const selectedItem = items[Math.max(activeSearchIndex, 0)];
                        if (selectedItem) {
                            selectAsset(selectedItem);
                        }
                    });

                    // --- Quick price button handlers ---
                    function updateQuickPrices() {
                        const basePrice = getQuickPriceBase();
                        document.querySelectorAll('.quick-price-btn').forEach(function(btn) {
                            const display = btn.querySelector('.quick-price-display');
                            const pct = parseFloat(btn.dataset.pct);
                            if (btn.dataset.marketOrder === 'true' || basePrice <= 0 || isNaN(pct)) {
                                display.textContent = '';
                                return;
                            }
                            const newPrice = basePrice * (1 + pct);
                            display.textContent = newPrice.toFixed(2);
                        });
                    }

                    // Click quick price button to set price
                    document.querySelectorAll('.quick-price-btn').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            const basePrice = getQuickPriceBase();
                            const pct = parseFloat(this.dataset.pct);
                            if (this.dataset.marketOrder === 'true') {
                                clearQuickPriceSelection();
                                priceMode.value = 'MARKET';
                                updatePriceMode();
                                updateCurrentReferencePrice();
                                updateQuickPrices();
                                return;
                            }
                            if (basePrice > 0 && !isNaN(pct)) {
                                const nextPrice = (basePrice * (1 + pct)).toFixed(2);
                                priceMode.value = 'LIMIT';
                                updatePriceMode();
                                priceInput.value = nextPrice;
                                lastQuickPricePct = pct;
                                lastQuickPriceValue = nextPrice;
                                updateEstShares();
                                updateCurrentReferencePrice();
                                updatePriceChangeHint();
                                updateQuickPrices();
                            }
                        });
                    });

                    // Click reference price button (placeholder)
                    document.querySelectorAll('.ref-price-btn').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            // Reference price buttons are placeholders
                            // In a real implementation, these would fetch
                            // 昨收/MA5/MA10/etc. from market data
                        });
                    });

                    // Update quick price displays when price changes
                    priceInput.addEventListener('input', function() {
                        if (priceInput.value !== lastQuickPriceValue) {
                            clearQuickPriceSelection();
                        }
                        updateQuickPrices();
                        updateCurrentReferencePrice();
                        updatePriceChangeHint();
                    });

                    // Initial state
                    clearReferencePrices();
                    updateActiveSide();
                    updateLabel();
                    updateEstShares();
                    updateQuickPrices();
                })();
                """
            ),
            hx_post="/trade/order",
            hx_target="#trade-result",
            id="trade-form",
            data_cash=str(cash),
            data_total=str(total),
        ),
        Div(id="trade-result"),
        cls="bg-white dark:bg-gray-800 rounded-lg shadow mb-6 p-6",
    )


def PositionTable(positions: list[Position]):
    """持仓明细表格"""
    headers = ["证券代码", "证券名称", "当前持股", "可用股数", "市值", "最新价", "成本价", "盈亏", "盈亏比例", "操作"]

    rows = []
    if positions:
        for p in positions:
            pnl_pct = (p.profit / (p.mv - p.profit) * 100) if (p.mv - p.profit) != 0 else 0
            current_price = p.mv / p.shares if p.shares > 0 else 0
            color_cls = "text-red-600" if p.profit > 0 else ("text-green-600" if p.profit < 0 else "")
            avail_lots = int(p.avail / 100) if p.avail >= 100 and p.avail % 100 == 0 else ""

            rows.append(
                Tr(
                    Td(p.asset),
                    Td(p.asset),  # TODO: 获取证券名称
                    Td(f"{p.shares:,}"),
                    Td(f"{p.avail:,}"),
                    Td(f"{p.mv:,.2f}"),
                    Td(f"{current_price:,.2f}"),
                    Td(f"{p.price:,.2f}"),
                    Td(f"{p.profit:,.2f}", cls=color_cls),
                    Td(f"{pnl_pct:.2f}%", cls=color_cls),
                    Td(
                        Button(
                            "卖出",
                            type="button",
                            cls="position-sell-btn uk-button uk-button-small bg-green-600 text-white hover:bg-green-700",
                        ),
                    ),
                    cls="trade-position-row cursor-pointer",
                    data_asset=p.asset,
                    data_display=p.asset,
                    data_price=f"{current_price:.2f}" if current_price > 0 else "",
                    data_avail_lots=str(avail_lots),
                )
            )
    else:
        rows.append(
            Tr(
                Td("暂无持仓", colspan=len(headers), cls="text-center py-10 text-gray-500")
            )
        )

    return Div(
        Div(
            H3("持仓明细", cls="text-lg font-semibold text-gray-900 dark:text-white"),
            Button(
                UkIcon("refresh-cw", size=16),
                " 刷新",
                cls="uk-button uk-button-primary uk-button-small",
                style="background-color: #d32f2f;",
                hx_get="/trade/positions",
                hx_target="#position-table",
            ),
            cls="flex items-center justify-between mb-4 px-6 pt-4",
        ),
        Table(
            Thead(Tr(*[Th(h, cls="text-xs font-bold bg-gray-50") for h in headers])),
            Tbody(*rows),
            cls="uk-table uk-table-divider uk-table-small uk-table-hover",
        ),
        id="position-table",
        cls="bg-white dark:bg-gray-800 rounded-lg shadow mb-6 overflow-hidden",
    )


def TodayOrdersTable(orders: list[Order]):
    """当日委托表格"""
    headers = ["时间", "代码", "名称", "方向", "委托价", "委托量", "成交量", "状态", "操作"]

    rows = []
    if orders:
        for o in orders:
            side_color = "text-red-600" if o.side == OrderSide.BUY else "text-green-600"
            side_text = "买入" if o.side == OrderSide.BUY else "卖出"

            status_map = {
                OrderStatus.PENDING: ("待成交", "text-yellow-600"),
                OrderStatus.PARTIAL: ("部分成交", "text-blue-600"),
                OrderStatus.FILLED: ("已成交", "text-green-600"),
                OrderStatus.CANCELLED: ("已撤单", "text-gray-500"),
                OrderStatus.REJECTED: ("已拒绝", "text-red-600"),
            }
            status_text, status_color = status_map.get(o.status, ("未知", "text-gray-500"))

            rows.append(
                Tr(
                    Td(o.tm.strftime("%H:%M:%S") if hasattr(o, 'tm') else "--"),
                    Td(o.asset),
                    Td(o.asset),  # TODO: 获取证券名称
                    Td(side_text, cls=side_color),
                    Td(f"{o.price:,.2f}"),
                    Td(f"{o.shares:,}"),
                    Td(f"{o.filled:,}"),
                    Td(status_text, cls=status_color),
                    Td(
                        Button(
                            "撤单",
                            cls="uk-button uk-button-small uk-button-default",
                            hx_post=f"/trade/cancel/{o.qtoid}",
                            hx_confirm="确定要撤单吗？",
                        ) if o.status in [OrderStatus.PENDING, OrderStatus.PARTIAL] else "",
                    ),
                )
            )
    else:
        rows.append(
            Tr(
                Td("暂无当日委托", colspan=len(headers), cls="text-center py-10 text-gray-500")
            )
        )

    return Div(
        Div(
            H3("当日委托", cls="text-lg font-semibold text-gray-900 dark:text-white"),
            Button(
                UkIcon("refresh-cw", size=16),
                " 刷新",
                cls="uk-button uk-button-primary uk-button-small",
                style="background-color: #d32f2f;",
                hx_get="/trade/orders",
                hx_target="#today-orders",
            ),
            cls="flex items-center justify-between mb-4 px-6 pt-4",
        ),
        Table(
            Thead(Tr(*[Th(h, cls="text-xs font-bold bg-gray-50") for h in headers])),
            Tbody(*rows),
            cls="uk-table uk-table-divider uk-table-small uk-table-hover",
        ),
        id="today-orders",
        cls="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden",
    )


def NoAccountView():
    """无账号视图"""
    return Div(
        Div(
            UkIcon("alert-circle", size=48, cls="text-yellow-500 mb-4"),
            H2("暂无交易账号", cls="text-2xl font-bold text-gray-900 mb-4"),
            P("您还没有配置任何交易账号。请先创建或配置账号。", cls="text-gray-600 mb-6"),
            Div(
                A(
                    UkIcon("plus", size=16),
                    " 创建仿真账号",
                    href="/trade/simulation",
                    cls="uk-button uk-button-primary mr-4",
                    style="background-color: #d32f2f;",
                ),
                A(
                    UkIcon("settings", size=16),
                    " 账号管理",
                    href="/system/accounts",
                    cls="uk-button uk-button-default",
                ),
                cls="flex justify-center gap-4",
            ),
            cls="text-center py-16",
        ),
        cls="max-w-2xl mx-auto bg-white rounded-xl shadow-sm border border-gray-100 p-8",
    )


def SelectAccountView(accounts: list[dict]):
    """选择账号视图"""
    live_accounts = [a for a in accounts if a["is_live"]]
    sim_accounts = [a for a in accounts if not a["is_live"]]

    def AccountCard(account: dict):
        return Div(
            Div(
                Div(
                    Span(
                        "实盘" if account["is_live"] else "仿真",
                        cls=f"px-2 py-1 text-xs font-medium rounded-full {'bg-red-100 text-red-700' if account['is_live'] else 'bg-blue-100 text-blue-700'}"
                    ),
                    Span(
                        "在线" if account["status"] else "离线",
                        cls=f"ml-2 text-xs {'text-green-600' if account['status'] else 'text-gray-400'}"
                    ),
                    cls="mb-2",
                ),
                H4(account["name"], cls="text-lg font-semibold text-gray-900"),
                P(f"ID: {account['id'][:16]}...", cls="text-xs text-gray-500"),
                cls="mb-4",
            ),
            Form(
                Input(type="hidden", name="kind", value=account["kind"]),
                Input(type="hidden", name="id", value=account["id"]),
                Button(
                    "设为活动账号",
                    type="submit",
                    cls="uk-button uk-button-primary w-full",
                    style="background-color: #d32f2f;",
                ),
                hx_post="/trade/set-active",
                hx_target="body",
                hx_swap="outerHTML",
            ),
            cls="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow",
        )

    return Div(
        Div(
            H2("选择活动账号", cls="text-2xl font-bold text-gray-900 mb-2"),
            P("请选择一个账号作为当前活动账号，所有交易操作将与该账号关联。", cls="text-gray-600 mb-6"),
            cls="mb-6",
        ),
        Div(
            Div(
                H3("实盘账号", cls="text-lg font-semibold text-gray-900 mb-4"),
                Div(
                    *[AccountCard(a) for a in live_accounts],
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                ) if live_accounts else P("暂无实盘账号", cls="text-gray-500 italic"),
                cls="mb-8",
            ),
            Div(
                H3("仿真账号", cls="text-lg font-semibold text-gray-900 mb-4"),
                Div(
                    *[AccountCard(a) for a in sim_accounts],
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                ) if sim_accounts else P("暂无仿真账号", cls="text-gray-500 italic"),
                cls="mb-8",
            ),
            Div(
                A(
                    UkIcon("settings", size=16),
                    " 管理账号",
                    href="/system/accounts",
                    cls="uk-button uk-button-default",
                ),
                cls="flex justify-center",
            ),
            cls="max-w-6xl mx-auto",
        ),
        cls="p-6",
    )


def trade_main_page(request):
    """交易主页面 - 符合 livetrade-default.html 原型"""
    from starlette.responses import HTMLResponse

    session = request.scope.get("session", {})
    layout = MainLayout(title="交易", user=session.get("auth"))
    layout.header_active = "交易"
    layout.set_sidebar_active("/trade")

    reg = _get_registry(request)

    # 获取所有账号
    accounts = _get_all_accounts(reg) if reg else []

    # 如果没有配置任何账号
    if not accounts:
        def main_block():
            return Div(NoAccountView(), cls="p-6")
        layout.main_block = main_block
        return HTMLResponse(to_xml(layout.render()))

    # 获取活动账号
    active_account = _get_active_account(reg, session)

    # 如果没有活动账号，显示选择页面
    if not active_account:
        def main_block():
            return SelectAccountView(accounts)
        layout.main_block = main_block
        return HTMLResponse(to_xml(layout.render()))

    # 获取账号数据
    portfolio_id = active_account["id"]
    kind = active_account["kind"]

    broker = reg.get(BrokerKind(kind), portfolio_id) if reg else None

    # 获取资产信息
    total = cash = market_value = 0
    positions = []
    orders = []

    if broker:
        if hasattr(broker, "asset") and broker.asset:
            total = broker.asset.total
            cash = broker.asset.cash
            market_value = broker.asset.market_value
        elif hasattr(broker, "total_assets"):
            # SimulationBroker 等没有 asset 属性
            total = broker.total_assets
            cash = broker.cash if hasattr(broker, "cash") else 0
            market_value = total - cash
        if hasattr(broker, "positions"):
            positions = list(broker.positions.values()) if isinstance(broker.positions, dict) else broker.positions
        if hasattr(broker, "orders"):
            orders = list(broker.orders.values()) if isinstance(broker.orders, dict) else broker.orders

    def main_block():
        return Div(
            # 账号信息
            Div(
                Div(
                    Span("★", cls="text-yellow-500 mr-1"),
                    Span(f"当前账号: {active_account['name']}", cls="font-medium"),
                    Span(f"({active_account['label']})", cls="ml-2 text-sm text-gray-500"),
                    cls="flex items-center mb-4 px-6",
                ),
            ),
            # 资产信息条
            AssetInfoBar(total, cash, market_value),
            # 闪电交易面板
            LightningTradePanel(portfolio_id, kind, cash, total),
            # 持仓明细
            PositionTable(positions),
            # 当日委托
            TodayOrdersTable(orders),
            cls="p-6",
        )

    layout.main_block = main_block
    return HTMLResponse(to_xml(layout.render()))


async def place_order_trade(req):
    """处理交易下单请求

    根据表单数据中的下单方式（金额/数量）和价格模式（限价/市价），
    调用对应的 broker 方法执行买入或卖出操作。

    Args:
        req: HTTP 请求对象

    Returns:
        HTMLResponse: 包含下单结果的 HTML 响应
    """
    reg = _get_registry(req)
    broker = None
    if reg:
        session = req.scope.get("session", {})
        active_kind = session.get("active_account_kind")
        active_id = session.get("active_account_id")
        if active_kind and active_id:
            broker = reg.get(BrokerKind(active_kind), active_id)
        else:
            default = reg.get_default()
            if default:
                broker = reg.get(default[0], default[1])

    def _render(div):
        return HTMLResponse(to_xml(div))

    if not broker:
        return _render(Div("未找到可用的交易账号", cls="text-red-500 p-4 bg-red-100 rounded"))

    form = await req.form()
    side = form.get("side", "BUY")
    asset = form.get("asset", "").strip()
    price_mode = form.get("price_mode", "LIMIT")
    order_mode = form.get("order_mode", "AMOUNT")
    price_str = form.get("price", "0")
    value_str = form.get("value", "0")

    if not asset:
        return _render(Div("请输入股票代码", cls="text-red-500 p-4 bg-red-100 rounded"))

    price = 0.0
    if price_mode == "LIMIT":
        try:
            price = float(price_str)
        except ValueError:
            return _render(Div("价格格式错误", cls="text-red-500 p-4 bg-red-100 rounded"))
        if price <= 0:
            return _render(Div("价格必须大于0", cls="text-red-500 p-4 bg-red-100 rounded"))

    try:
        value = float(value_str)
    except ValueError:
        return _render(Div("金额/数量格式错误", cls="text-red-500 p-4 bg-red-100 rounded"))

    if value <= 0:
        return _render(Div("金额/数量必须大于0", cls="text-red-500 p-4 bg-red-100 rounded"))

    try:
        result = None
        if side == "BUY":
            if order_mode == "AMOUNT":
                amount = value * 10000
                if hasattr(broker, "buy_amount"):
                    result = await broker.buy_amount(asset, amount, price if price > 0 else 0)
                else:
                    shares = int(value * 10000 / price) if price > 0 else int(value)
                    result = await broker.buy(asset, shares, price)
            else:
                shares = int(value) * 100
                result = await broker.buy(asset, shares, price)
        else:
            if order_mode == "AMOUNT":
                amount = value * 10000
                if hasattr(broker, "sell_amount"):
                    result = await broker.sell_amount(asset, amount, price if price > 0 else 0)
                else:
                    shares = int(value * 10000 / price) if price > 0 else int(value)
                    result = await broker.sell(asset, shares, price)
            else:
                shares = int(value) * 100
                result = await broker.sell(asset, shares, price)

        if not _trade_result_has_order(result):
            return _render(
                Div(
                    "未生成有效委托，请检查价格、数量和持仓后重试",
                    cls="text-red-500 p-4 bg-red-100 rounded",
                )
            )

        side_text = "买入" if side == "BUY" else "卖出"
        return _render(Div(
            f"{side_text}委托已提交: {asset}",
            cls="text-green-600 p-4 bg-green-100 rounded",
        ))
    except Exception as e:
        return _render(Div(f"下单失败: {str(e)}", cls="text-red-500 p-4 bg-red-100 rounded"))


async def search_trade_assets(req):
    """搜索股票代码/名称/拼音，返回 HTMX 下拉列表 HTML。

    Args:
        req: HTTP 请求对象，包含查询参数 q

    Returns:
        HTMLResponse: 搜索结果下拉列表 HTML
    """
    query = req.query_params.get("q", "").strip()

    if not query:
        return HTMLResponse(to_xml(Div(id="asset-search-dropdown", cls="hidden")))

    try:
        result_df = stock_list.fuzzy_search(query, id_only=False)
    except Exception:
        return HTMLResponse(to_xml(Div(id="asset-search-dropdown", cls="hidden")))

    if result_df is None or len(result_df) == 0:
        return HTMLResponse(to_xml(Div(
            Div("无匹配结果", cls="px-3 py-2 text-sm text-gray-500"),
            id="asset-search-dropdown",
            cls="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto",
        )))

    today = datetime.date.today()
    items = []
    for _, row in result_df.iterrows():
        asset = row.get("asset", "")
        name = row.get("name", "")
        pinyin = row.get("pinyin", "")
        display = f"{name}（{asset}）"
        # 尝试获取最新收盘价
        price = ""
        try:
            close, up_limit, down_limit = daily_bars.get_price(asset, today)
            if close and close > 0:
                price = str(close)
        except Exception:
            fallback_bars = _load_trade_reference_bars(asset, today, 1)
            if not fallback_bars.is_empty():
                price = str(fallback_bars.row(0, named=True).get("close", ""))
        items.append(
            Div(
                Div(name, cls="text-sm font-medium text-gray-900 dark:text-white"),
                Div(f"{asset} · {pinyin}", cls="text-xs text-gray-500 dark:text-gray-400"),
                cls="asset-search-item px-3 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700",
                data_asset=asset,
                data_name=name,
                data_display=display,
                data_price=price,
                tabindex="0",
                role="button",
            )
        )

    return HTMLResponse(to_xml(Div(
        *items,
        id="asset-search-dropdown",
        cls="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto",
    )))


async def trade_asset_stats(req):
    """Return reference price stats for the selected asset.

    Args:
        req: HTTP request carrying the asset query parameter.

    Returns:
        JSONResponse: Compact stats payload for the trade panel.
    """
    asset = req.query_params.get("asset", "").strip()
    return JSONResponse(_build_asset_stats(asset) if asset else _build_asset_stats(""))


async def set_active_account(req, session):
    """设置活动账号"""
    form = await req.form()
    kind = form.get("kind")
    account_id = form.get("id")

    if not kind or not account_id:
        return Div("参数错误", cls="text-red-500 p-4")

    session["active_account_kind"] = kind
    session["active_account_id"] = account_id

    return RedirectResponse(url="/trade", status_code=303)
