"""交易主页面 - 符合 livetrade-default.html 原型

包含：
1. 资产信息条
2. 闪电交易面板
3. 持仓明细
4. 当日委托
"""

from fasthtml.common import *
from fasthtml.common import Select as _Select
from monsterui.all import *
from starlette.responses import HTMLResponse, RedirectResponse

from quantide.core.enums import BrokerKind, OrderSide, OrderStatus
from quantide.data.models.stocks import stock_list
from quantide.data.sqlite import Position, Order
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
    # 统一行高：所有输入控件使用 h-10 (40px)
    input_cls = "flex-1 px-3 h-10 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-red-500 dark:bg-gray-700 dark:text-white"
    select_cls = "px-2 h-10 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-red-500 dark:bg-gray-700 dark:text-white text-sm"
    # radio button 使用原生样式，避免 MonsterUI 的 uk-input 边框
    radio_cls = "w-4 h-4 text-red-600 focus:ring-red-500 cursor-pointer"

    # Search icon SVG
    search_svg = NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">'
        '<circle cx="11" cy="11" r="8"></circle>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>'
    )

    return Div(
        Form(
            Div(
                # 左边：下单输入区（2/5）
                Div(
                    # Row 1: Code input with fuzzy search dropdown
                    Div(
                        Div(
                            Input(
                                type="text",
                                name="asset_display",
                                placeholder="请输入股票名、拼音或者代码",
                                cls=f"{input_cls} pr-10",
                                id="asset-display",
                                autocomplete="off",
                                hx_get="/trade/search",
                                hx_trigger="keyup changed delay:200ms",
                                hx_target="#asset-search-dropdown",
                                hx_swap="outerHTML",
                                hx_vals='js:{"q": document.getElementById("asset-display").value}',
                            ),
                            Input(
                                type="hidden",
                                name="asset",
                                id="asset-code",
                            ),
                            search_svg,
                            Div(id="asset-search-dropdown", cls="hidden"),
                            cls="relative flex-1",
                        ),
                        cls="flex items-center mb-3",
                    ),
                    # Row 2: Price mode + Price (use _Select to avoid MonsterUI Uk_select)
                    Div(
                        _Select(
                            Option("限价", value="LIMIT", selected=True),
                            Option("市价", value="MARKET"),
                            name="price_mode",
                            cls=f"{select_cls} w-24",
                            id="price-mode-select",
                        ),
                        Input(
                            type="text",
                            name="price",
                            placeholder="价格",
                            value="0.00",
                            cls=f"{input_cls} text-right text-lg font-medium",
                            id="price-input",
                        ),
                        cls="flex items-center gap-2 mb-3",
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
                            Span("按金额下单", cls="ml-1 text-sm text-gray-700 dark:text-gray-300"),
                            cls="flex items-center cursor-pointer h-10",
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
                            Span("按数量下单", cls="ml-1 text-sm text-gray-700 dark:text-gray-300"),
                            cls="flex items-center cursor-pointer h-10",
                        ),
                        cls="flex items-center gap-4 mb-3",
                    ),
                    # Row 4: Dynamic label input
                    Div(
                        Span(
                            "买入金额（万元）",
                            cls="text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap",
                            id="value-label",
                        ),
                        Input(
                            type="text",
                            name="value",
                            placeholder="",
                            cls=f"{input_cls} text-right text-lg font-medium",
                            id="value-input",
                        ),
                        cls="flex items-center gap-2 mb-3",
                    ),
                    # Row 5: Estimated shares
                    Div(
                        Span("预估数量", cls="text-sm font-medium text-gray-700 dark:text-gray-300"),
                        Span(
                            "--",
                            cls="text-sm font-medium text-gray-900 dark:text-white ml-auto",
                            id="est-shares",
                        ),
                        cls="flex items-center mb-3 px-3 py-2 bg-gray-50 dark:bg-gray-700 rounded-lg",
                    ),
                    # Row 6: Position fraction buttons (ordered: 1/4, 1/3, 1/2, 全仓)
                    Div(
                        Div(
                            Button(
                                "1/4",
                                type="button",
                                cls="pos-btn px-2 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 font-medium",
                                data_fraction="0.25",
                            ),
                            Button(
                                "1/3",
                                type="button",
                                cls="pos-btn px-2 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 font-medium",
                                data_fraction="0.3333",
                            ),
                            Button(
                                "1/2",
                                type="button",
                                cls="pos-btn px-2 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 font-medium",
                                data_fraction="0.5",
                            ),
                            Button(
                                "全仓",
                                type="button",
                                cls="pos-btn px-2 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 font-medium",
                                data_fraction="1.0",
                            ),
                            cls="grid grid-cols-4 gap-2",
                        ),
                        cls="mb-3",
                    ),
                    # Row 7: Buy/Sell buttons with active state
                    Div(
                        Input(type="hidden", name="side", value="BUY", id="side-input"),
                        Button(
                            Span("*", cls="absolute top-0 left-2 text-xs"),
                            "买入",
                            type="button",
                            cls="relative bg-red-600 hover:bg-red-700 text-white font-bold py-3 px-4 rounded-lg text-lg w-full",
                            id="btn-buy",
                            data_side="BUY",
                        ),
                        Button(
                            Span("*", cls="absolute top-0 left-2 text-xs hidden", id="sell-star"),
                            "卖出",
                            type="button",
                            cls="relative bg-green-600 hover:bg-green-700 text-white font-bold py-3 px-4 rounded-lg text-lg w-full opacity-60",
                            id="btn-sell",
                            data_side="SELL",
                        ),
                        cls="grid grid-cols-2 gap-3 pt-2",
                    ),
                    # Hidden submit for HTMX
                    Input(type="submit", cls="hidden", id="form-submit"),
                    cls="col-span-5 space-y-3",
                ),
                # 中间：价格快捷输入区
                Div(
                    # 顶部标题行：快捷价格 + 参考价格按钮 + 实时价格
                    Div(
                        Span("快捷价格", cls="text-sm font-medium text-gray-700 dark:text-gray-300"),
                        Div(
                            *[
                                Button(
                                    label,
                                    type="button",
                                    cls="ref-price-btn px-1.5 py-0.5 text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded hover:bg-gray-200 font-medium",
                                )
                                for label in ["昨收", "MA5", "MA10", "MA20", "MA30", "MA60", "现价"]
                            ],
                            cls="flex gap-1",
                        ),
                        Span("实时: 0.00", cls="text-xs text-gray-500 dark:text-gray-400"),
                        cls="flex items-center justify-between mb-2 gap-2",
                    ),
                    # 中间主体：4x5 涨跌百分比按钮网格
                    Div(
                        *[
                            Button(
                                Div(label, cls="text-xs font-medium leading-tight"),
                                Div("--", cls="quick-price-display text-[10px] text-gray-400 leading-tight mt-0.5"),
                                type="button",
                                cls=(
                                    "quick-price-btn w-full px-1 py-1 rounded font-medium text-center "
                                    + ("bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 hover:bg-red-200" if label == "涨停" else
                                       "bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 hover:bg-green-200" if label == "跌停" else
                                       "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200")
                                ),
                                data_pct=str(pct),
                            )
                            for row in [
                                [("涨停", 0.10), ("9", 0.09), ("8", 0.08), ("7", 0.07)],
                                [("6", 0.06), ("5", 0.05), ("4", 0.04), ("3", 0.03)],
                                [("2", 0.02), ("1", 0.01), ("-1", -0.01), ("-2", -0.02)],
                                [("-3", -0.03), ("-4", -0.04), ("-5", -0.05), ("-6", -0.06)],
                                [("-7", -0.07), ("-8", -0.08), ("-9", -0.09), ("跌停", -0.10)],
                            ]
                            for label, pct in row
                        ],
                        cls="grid grid-cols-4 gap-1",
                    ),
                    cls="space-y-2",
                ),
                # 右边：候选股票池（2/5）
                Div(
                    Div(
                        H3("候选票池", cls="text-base font-semibold text-gray-900 dark:text-white"),
                        Input(type="text", placeholder="搜索股票...", cls="w-32 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-red-500 dark:bg-gray-600 dark:text-white"),
                        cls="flex items-center justify-between mb-3",
                    ),
                    # 候选股票列表
                    Div(
                        Div(
                            Div(
                                Div("平安银行", cls="text-sm font-medium text-gray-900 dark:text-white"),
                                Div("000001.SZ", cls="text-xs text-gray-500 dark:text-gray-400"),
                                cls="",
                            ),
                            Div("13.80", cls="text-sm font-medium text-red-600"),
                            cls="p-2 bg-white dark:bg-gray-800 rounded-lg cursor-pointer hover:ring-2 hover:ring-red-500 transition-all flex items-center justify-between",
                        ),
                        Div(
                            Div(
                                Div("贵州茅台", cls="text-sm font-medium text-gray-900 dark:text-white"),
                                Div("600519.SH", cls="text-xs text-gray-500 dark:text-gray-400"),
                                cls="",
                            ),
                            Div("1688.00", cls="text-sm font-medium text-green-600"),
                            cls="p-2 bg-white dark:bg-gray-800 rounded-lg cursor-pointer hover:ring-2 hover:ring-red-500 transition-all flex items-center justify-between",
                        ),
                        cls="space-y-2",
                    ),
                    cls="col-span-3 bg-gray-50 dark:bg-gray-700 rounded-lg p-4",
                ),
                cls="grid grid-cols-12 gap-4",
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
                    const sellStar = document.getElementById('sell-star');
                    const cash = parseFloat(form.dataset.cash) || 0;
                    const assetDisplay = document.getElementById('asset-display');
                    const assetCode = document.getElementById('asset-code');
                    const searchDropdown = document.getElementById('asset-search-dropdown');

                    function updatePriceMode() {
                        if (priceMode.value === 'MARKET') {
                            priceInput.disabled = true;
                            priceInput.value = '';
                            priceInput.placeholder = '市价';
                            priceInput.classList.add('bg-gray-100');
                        } else {
                            priceInput.disabled = false;
                            if (priceInput.placeholder === '市价') {
                                priceInput.value = '0.00';
                            }
                            priceInput.placeholder = '价格';
                            priceInput.classList.remove('bg-gray-100');
                        }
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
                            btnBuy.classList.remove('opacity-60');
                            btnSell.classList.add('opacity-60');
                            sellStar.classList.add('hidden');
                        } else {
                            btnSell.classList.remove('opacity-60');
                            btnBuy.classList.add('opacity-60');
                            sellStar.classList.remove('hidden');
                        }
                    }

                    function updateEstShares() {
                        const price = parseFloat(priceInput.value) || 0;
                        const value = parseFloat(valueInput.value) || 0;
                        const mode = document.querySelector('input[name="order_mode"]:checked').value;
                        const isMarket = priceMode.value === 'MARKET';

                        if ((price <= 0 && !isMarket) || value <= 0) {
                            estShares.textContent = '--';
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

                        estShares.textContent = shares + ' 股';
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
                        sideInput.value = 'BUY';
                        updateActiveSide();
                        updateLabel();
                        document.getElementById('form-submit').click();
                    });

                    btnSell.addEventListener('click', function() {
                        sideInput.value = 'SELL';
                        updateActiveSide();
                        updateLabel();
                        document.getElementById('form-submit').click();
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
                        searchDropdown.classList.add('hidden');
                        // Auto-fill price if available
                        const price = item.dataset.price;
                        if (price && price !== '') {
                            priceInput.value = price;
                            updateEstShares();
                            updateQuickPrices();
                        }
                    }

                    function attachSearchItemListeners() {
                        document.querySelectorAll('.asset-search-item').forEach(function(item) {
                            item.addEventListener('click', function() {
                                selectAsset(this);
                            });
                        });
                    }

                    // Re-attach listeners after HTMX swaps in new dropdown content
                    document.body.addEventListener('htmx:afterSwap', function(evt) {
                        if (evt.detail.target.id === 'asset-search-dropdown') {
                            attachSearchItemListeners();
                            searchDropdown.classList.remove('hidden');
                        }
                    });

                    // Close dropdown when clicking outside
                    document.addEventListener('click', function(evt) {
                        if (!assetDisplay.contains(evt.target) && !searchDropdown.contains(evt.target)) {
                            searchDropdown.classList.add('hidden');
                        }
                    });

                    // Clear hidden code when user manually edits display field
                    assetDisplay.addEventListener('input', function() {
                        assetCode.value = '';
                    });

                    // --- Quick price button handlers ---
                    function updateQuickPrices() {
                        const basePrice = parseFloat(priceInput.value) || 0;
                        document.querySelectorAll('.quick-price-btn').forEach(function(btn) {
                            const display = btn.querySelector('.quick-price-display');
                            const pct = parseFloat(btn.dataset.pct);
                            if (basePrice <= 0 || isNaN(pct)) {
                                display.textContent = '--';
                                return;
                            }
                            const newPrice = basePrice * (1 + pct);
                            display.textContent = newPrice.toFixed(2);
                        });
                    }

                    // Click quick price button to set price
                    document.querySelectorAll('.quick-price-btn').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            const basePrice = parseFloat(priceInput.value) || 0;
                            const pct = parseFloat(this.dataset.pct);
                            if (basePrice > 0 && !isNaN(pct)) {
                                priceInput.value = (basePrice * (1 + pct)).toFixed(2);
                                updateEstShares();
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
                    priceInput.addEventListener('input', updateQuickPrices);

                    // Initial state
                    updateActiveSide();
                    updateLabel();
                    updateQuickPrices();
                })();
                """
            ),
            hx_post=f"/trade/order",
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
                        Button("卖出", cls="uk-button uk-button-small bg-green-600 text-white hover:bg-green-700"),
                    ),
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
                hx_get=f"/trade/positions",
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
                hx_get=f"/trade/orders",
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
        if side == "BUY":
            if order_mode == "AMOUNT":
                amount = value * 10000
                if hasattr(broker, "buy_amount"):
                    await broker.buy_amount(asset, amount, price if price > 0 else None)
                else:
                    shares = int(value * 10000 / price) if price > 0 else int(value)
                    await broker.buy(asset, shares, price)
            else:
                shares = int(value) * 100
                await broker.buy(asset, shares, price)
        else:
            if order_mode == "AMOUNT":
                amount = value * 10000
                if hasattr(broker, "sell_amount"):
                    await broker.sell_amount(asset, amount, price if price > 0 else None)
                else:
                    shares = int(value * 10000 / price) if price > 0 else int(value)
                    await broker.sell(asset, shares, price)
            else:
                shares = int(value) * 100
                await broker.sell(asset, shares, price)

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

    # 查询最新价格
    from quantide.data.models.daily_bars import daily_bars
    import datetime

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
            pass
        items.append(
            Div(
                Div(name, cls="text-sm font-medium text-gray-900 dark:text-white"),
                Div(f"{asset} · {pinyin}", cls="text-xs text-gray-500 dark:text-gray-400"),
                cls="asset-search-item px-3 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700",
                data_asset=asset,
                data_name=name,
                data_display=display,
                data_price=price,
            )
        )

    return HTMLResponse(to_xml(Div(
        *items,
        id="asset-search-dropdown",
        cls="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto",
    )))


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
