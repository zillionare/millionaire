"""Trade form and quote information components."""

from fasthtml.common import *
from fasthtml.common import (
    FT,
    Div,
    NotStr,
    Option,
    P,
    Script,
    Span,
    ft_hx,
)
from fasthtml.common import Select as _Select
from monsterui.all import *
from monsterui.all import (
    Button,
    Form,
    Input,
    UkIcon,
)

from quantide.web.components.trade_toast import TradeToast
from quantide.web.pages.trade_lightning import (
    TradeLightningSidebar,
    TradeReferencePanel,
)

_trade_toast = TradeToast


def AssetInfoBar(
    total: float = 0,
    cash: float = 0,
    market_value: float = 0,
    principal: float = 0,
) -> FT:
    """资产信息条"""
    cash_ratio = (cash / total * 100) if total > 0 else 0
    position_ratio = (market_value / total * 100) if total > 0 else 0
    pnl_pct = ((total - principal) / principal * 100) if principal > 0 else 0

    return Div(
        Div(
            Div(
                Span("总资产", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(
                    f"{total / 10000:.2f}万",
                    cls="font-bold text-gray-900 dark:text-white text-base ml-2",
                ),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("盈亏比例", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(
                    f"{pnl_pct:+.2f}%",
                    cls="font-bold text-gray-900 dark:text-white text-base ml-2",
                ),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("现金", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(
                    f"{cash / 10000:.2f}万",
                    cls="font-bold text-gray-900 dark:text-white text-base ml-2",
                ),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("现金比", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(
                    f"{cash_ratio:.1f}%",
                    cls="font-bold text-gray-900 dark:text-white text-base ml-2",
                ),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("市值", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(
                    f"{market_value / 10000:.2f}万",
                    cls="font-bold text-gray-900 dark:text-white text-base ml-2",
                ),
                cls="flex items-center space-x-2",
            ),
            Div(
                Span("仓位", cls="text-gray-600 dark:text-gray-400 text-sm"),
                Span(
                    f"{position_ratio:.1f}%",
                    cls="font-bold text-gray-900 dark:text-white text-base ml-2",
                ),
                cls="flex items-center space-x-2",
            ),
            cls="flex items-center justify-between text-sm px-6 py-4",
        ),
        cls="bg-white dark:bg-gray-800 rounded-lg shadow mb-6",
    )


def LightningTradePanel(
    portfolio_id: str,
    kind: str,
    cash: float = 0,
    total: float = 0,
    is_live: bool = True,
) -> FT:
    """闪电交易面板 - 符合 spec 的下单键盘。

    实盘显示闪电单；仿真只保留普通下单（补单/测试），并提示原因。
    """
    # 收紧输入区尺寸，并把更多宽度让给中间 speed dial 键盘。
    input_cls = (
        "flex-1 px-3 h-9 border border-gray-300 dark:border-gray-600 rounded-lg "
        "focus:ring-2 focus:ring-red-500 dark:bg-gray-700 dark:text-white text-sm"
    )
    select_cls = (
        "px-2 h-9 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 "
        "focus:ring-red-500 dark:bg-gray-700 dark:text-white text-sm"
    )
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
                            cls=(
                                "px-3 h-9 border border-l-0 border-gray-300 "
                                "dark:border-gray-600 rounded-r-lg bg-gray-100 "
                                "dark:bg-gray-700 text-gray-600 dark:text-gray-400 "
                                "hover:bg-gray-200 flex items-center justify-center"
                            ),
                        ),
                        Input(
                            type="hidden",
                            name="asset",
                            id="asset-code",
                        ),
                        Div(
                            id="asset-search-dropdown",
                            cls="hidden absolute top-full left-0 right-0 z-50",
                        ),
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
                    # Use raw ft_hx radio buttons to preserve border styling.
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
                            cls=(
                                "text-xs font-medium text-gray-700 dark:text-gray-300 "
                                "whitespace-nowrap"
                            ),
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
                        Span(
                            "预估数量 (股)",
                            cls="text-xs font-medium text-gray-700 dark:text-gray-300",
                        ),
                        Div(
                            "",
                            cls=(
                                "px-3 h-9 flex w-full items-center justify-end text-sm "
                                "font-medium text-gray-900 dark:text-white border "
                                "border-gray-300 dark:border-gray-600 rounded-lg "
                                "bg-white dark:bg-gray-700"
                            ),
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
                                cls=(
                                    "pos-btn px-2 py-1.5 text-xs bg-gray-100 "
                                    "dark:bg-gray-700 text-gray-700 dark:text-gray-300 "
                                    "rounded-lg hover:bg-gray-200 font-medium"
                                ),
                                data_fraction="0.25",
                            ),
                            Button(
                                "1/3",
                                type="button",
                                cls=(
                                    "pos-btn px-2 py-1.5 text-xs bg-gray-100 "
                                    "dark:bg-gray-700 text-gray-700 dark:text-gray-300 "
                                    "rounded-lg hover:bg-gray-200 font-medium"
                                ),
                                data_fraction="0.3333",
                            ),
                            Button(
                                "1/2",
                                type="button",
                                cls=(
                                    "pos-btn px-2 py-1.5 text-xs bg-gray-100 "
                                    "dark:bg-gray-700 text-gray-700 dark:text-gray-300 "
                                    "rounded-lg hover:bg-gray-200 font-medium"
                                ),
                                data_fraction="0.5",
                            ),
                            Button(
                                "全仓",
                                type="button",
                                cls=(
                                    "pos-btn px-2 py-1.5 text-xs bg-gray-100 "
                                    "dark:bg-gray-700 text-gray-700 dark:text-gray-300 "
                                    "rounded-lg hover:bg-gray-200 font-medium"
                                ),
                                data_fraction="1.0",
                            ),
                            cls="grid grid-cols-4 gap-1.5",
                        ),
                        cls="mb-2",
                    ),
                    # Row 7: Buy/Sell buttons with active state
                    Div(
                        Input(type="hidden", name="side", value="BUY", id="side-input"),
                        Input(
                            type="hidden", name="account_kind", value=kind, id="account-kind-input"
                        ),
                        Input(
                            type="hidden",
                            name="account_id",
                            value=portfolio_id,
                            id="account-id-input",
                        ),
                        Button(
                            Span("*", cls="absolute top-0 left-2 text-xs", id="buy-star"),
                            "买入",
                            type="button",
                            cls=(
                                "relative bg-red-600 hover:bg-red-700 text-white "
                                "font-bold py-2.5 px-4 rounded-lg text-base w-full"
                            ),
                            id="btn-buy",
                            data_side="BUY",
                            aria_pressed="true",
                        ),
                        Button(
                            Span("*", cls="absolute top-0 left-2 text-xs hidden", id="sell-star"),
                            "卖出",
                            type="button",
                            cls=(
                                "relative bg-green-600 hover:bg-green-700 text-white "
                                "font-bold py-2.5 px-4 rounded-lg text-base w-full "
                                "opacity-60"
                            ),
                            id="btn-sell",
                            data_side="SELL",
                            aria_pressed="false",
                        ),
                        cls="grid grid-cols-2 gap-2 pt-1",
                    ),
                    # Hidden submit for HTMX
                    Input(type="submit", cls="hidden", id="form-submit"),
                    id="trade-order-panel",
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
                                Div(
                                    "",
                                    cls=(
                                        "quick-price-display text-[11px] text-gray-400 "
                                        "leading-tight mt-0.5 min-h-4"
                                    ),
                                ),
                                type="button",
                                cls=(
                                    (
                                        "quick-price-btn aspect-square w-full flex "
                                        "flex-col items-center justify-center "
                                        "bg-[#f9fafb] dark:bg-gray-800 rounded-lg "
                                        "shadow-sm transition-transform "
                                        "active:scale-[0.98] disabled:opacity-40 "
                                        "disabled:cursor-not-allowed "
                                        "disabled:active:scale-100 "
                                    )
                                    + ("text-[#b71c1c]" if pct > 0 else "text-[#388e3c]")
                                ),
                                data_pct=str(pct),
                                data_market_order="true" if abs(pct) == 0.10 else "false",
                                disabled=True,
                            )
                            for row in [
                                [("涨停", 0.10), ("5%", 0.05), ("-1%", -0.01), ("-6%", -0.06)],
                                [("9%", 0.09), ("4%", 0.04), ("-2%", -0.02), ("-7%", -0.07)],
                                [("8%", 0.08), ("3%", 0.03), ("-3%", -0.03), ("-8%", -0.08)],
                                [("7%", 0.07), ("2%", 0.02), ("-4%", -0.04), ("-9%", -0.09)],
                                [("6%", 0.06), ("1%", 0.01), ("-5%", -0.05), ("跌停", -0.10)],
                            ]
                            for label, pct in row
                        ],
                        id="quick-price-grid",
                        cls="grid w-[220px] grid-cols-4 gap-1.5",
                    ),
                    cls="flex shrink-0 items-stretch",
                ),
                # 右边：闪电单（实盘）/ 补单说明（仿真）
                Div(
                    TradeReferencePanel(),
                    (
                        TradeLightningSidebar(portfolio_id)
                        if is_live
                        else Div(
                            Div(
                                UkIcon("zap-off", size=18, cls="text-gray-400"),
                                cls=(
                                    "flex h-8 w-8 items-center justify-center rounded-lg "
                                    "border border-gray-200 bg-gray-50"
                                ),
                            ),
                            P(
                                "闪电单仅用于实盘；仿真账户保留普通下单，用于补单与测试。",
                                cls="mt-3 text-sm text-gray-500",
                            ),
                            cls=(
                                "flex w-[260px] flex-col items-center justify-center "
                                "rounded-lg border border-gray-100 bg-gray-50 p-4"
                            ),
                        )
                    ),
                    cls="flex-[0.95] space-y-0",
                ),
                cls="flex gap-3",
            ),
            Script(src="/static/trade-panel.js"),
            hx_post="/trade/order",
            hx_target="#trade-toast-slot",
            id="trade-form",
            data_cash=str(cash),
            data_total=str(total),
        ),
        cls="bg-white dark:bg-gray-800 rounded-lg shadow mb-6 p-6",
    )
