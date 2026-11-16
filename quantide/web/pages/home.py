from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    Form,
    Input,
    Li,
    Nav,
    P,
    Span,
    Thead,
    Tr,
    Ul,
)

# Use FastHTML's plain Label for form elements to avoid MonsterUI's uk-label styling
from loguru import logger
from monsterui.all import *
from monsterui.all import H2, H3, Button, Table, Tbody, Td, Th, UkIcon
from starlette.requests import Request
from starlette.responses import RedirectResponse

from quantide.config.branding import get_branding
from quantide.config.features import supports_live_trading
from quantide.core.enums import BrokerKind, OrderSide, OrderStatus
from quantide.data.models import Position
from quantide.service.init_wizard import init_wizard
from quantide.service.registry import BrokerRegistry
from quantide.web.apis.broker import build_asset_overview
from quantide.web.application import fast_app
from quantide.web.components.account_positions import AccountPositionInfo
from quantide.web.components.account_summary import AssetSummary as AssetSummary
from quantide.web.components.legacy_trade_panel import LegacyTradeInputs
from quantide.web.services.trade_orders import submit_share_form
from quantide.web.session_data import SessionData
from quantide.web.theme import AppTheme

home_app, rt = fast_app(hdrs=AppTheme.headers())


def _safe_broker_attr(broker: Any, name: str, default: Any = None) -> Any:
    """Safely read a broker attribute.

    Args:
        broker: Broker-like object.
        name: Attribute name.
        default: Fallback value when unavailable.

    Returns:
        The attribute value or the fallback value.
    """
    try:
        return getattr(broker, name)
    except AttributeError:
        return default
    except Exception as exc:
        logger.warning(f"读取 broker.{name} 失败，已降级忽略: {exc}")
        return default


def _normalize_positions(positions: Any) -> list[Position]:
    """Normalize broker positions to a list.

    Args:
        positions: Broker positions in dict/list form.

    Returns:
        A list of positions.
    """
    if not positions:
        return []
    if isinstance(positions, dict):
        return list(positions.values())
    return list(positions)


def _build_broker_asset_overview(broker: Any) -> dict[str, Any] | None:
    """Build asset overview from a broker with graceful fallback.

    Args:
        broker: Broker-like object.

    Returns:
        Asset overview dict or None.
    """
    asset = _safe_broker_attr(broker, "asset")
    if asset is not None:
        return build_asset_overview(asset)

    total = _safe_broker_attr(broker, "total_assets")
    if total is None:
        return None

    cash = _safe_broker_attr(broker, "cash", 0)
    principal = _safe_broker_attr(broker, "principal", 0)
    market_value = total - cash
    pnl = total - principal
    pnl_pct = pnl / principal if principal else 0
    return {
        "total": total,
        "cash": cash,
        "frozen_cash": 0,
        "market_value": market_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


def AccountTabs() -> Any:
    return Div(Ul(Li(A("我的资产", cls="active", href="#")), cls="uk-tab"), cls="mb-4")


def PositionInfo(positions: list[Position] | None = None) -> Any:
    return AccountPositionInfo(positions, refresh_url="/home/positions")


def TradePanel() -> Any:
    # 交易操作面板 (中国红风格)

    return Div(
        Form(
            Div(
                Ul(
                    Li(
                        A(
                            UkIcon("plus-circle", size=14),
                            " 买入",
                            href="#",
                            cls="flex items-center text-xs",
                            onclick=(
                                "document.getElementById('side').value='BUY'; "
                                "this.closest('ul').querySelectorAll('li').forEach(li => "
                                "li.classList.remove('uk-active')); "
                                "this.parentElement.classList.add('uk-active');"
                            ),
                        ),
                        cls="uk-active",
                    ),
                    Li(
                        A(
                            UkIcon("minus-circle", size=14),
                            " 卖出",
                            href="#",
                            cls="flex items-center text-xs",
                            onclick=(
                                "document.getElementById('side').value='SELL'; "
                                "this.closest('ul').querySelectorAll('li').forEach(li => "
                                "li.classList.remove('uk-active')); "
                                "this.parentElement.classList.add('uk-active');"
                            ),
                        )
                    ),
                    cls="uk-tab uk-child-width-expand mb-4 bg-white/10 rounded-lg p-0.5",
                    style="border-bottom: none;",
                )
            ),
            Input(type="hidden", id="side", name="side", value="BUY"),
            # Inputs
            LegacyTradeInputs(
                "买入价格",
                (
                    "uk-button-default w-full bg-white text-red-700 font-bold border-none "
                    "hover:bg-gray-100"
                ),
            ),
            hx_post="/home/order",
            hx_target="#position-info",
            hx_swap="outerHTML",
        ),
        cls="p-6 rounded-xl shadow-xl h-full",
    )


def BrokerList(items: list[dict[str, Any]]) -> Any:
    links = []
    for it in items:
        href = f"/home?kind={it['kind']}&id={it['id']}"
        links.append(Li(A(f"{it['kind']}:{it['id']}", href=href, cls="text-xs")))
    return Div(
        H3("实例列表", cls="text-sm font-bold mb-2"),
        Ul(*links, cls="uk-list uk-list-striped"),
        cls="bg-white p-3 rounded-xl shadow-sm border border-gray-100 mb-4",
    )


def _format_amount(value: float | None) -> str:
    """格式化金额数值。

    Args:
        value: 金额数值

    Returns:
        str: 格式化文本
    """
    if value is None:
        return "--"
    return f"{value:,.2f}"


def _format_amount_wan(value: float | None) -> str:
    """格式化万元显示。

    Args:
        value: 金额数值

    Returns:
        str: 格式化文本
    """
    if value is None:
        return "--"
    return f"{value / 10000:,.2f}"


def _format_percent(value: float | None) -> str:
    """格式化百分比显示。

    Args:
        value: 百分比数值

    Returns:
        str: 格式化文本
    """
    if value is None:
        return "--"
    return f"{value * 100:.2f}%"


def _position_tag(profit_pct: float) -> tuple[str, str]:
    """生成持仓预警标签。

    Args:
        profit_pct: 盈亏比例

    Returns:
        tuple[str, str]: 标签文本和样式
    """
    if profit_pct <= -0.05:
        return "风险", "bg-red-100 text-red-800"
    if profit_pct <= 0:
        return "关注", "bg-gray-100 text-gray-700"
    return "正常", "bg-green-100 text-green-800"


def OverviewCards(asset_overview: dict[str, Any] | None = None) -> Any:
    """构建首页资产概览卡片。

    Args:
        asset_overview: 资产概览数据

    Returns:
        Div: 资产概览卡片区域
    """
    asset_overview = asset_overview or {}
    total = asset_overview.get("total")
    market_value = asset_overview.get("market_value")
    cash = asset_overview.get("cash")
    pnl = asset_overview.get("pnl")
    pnl_pct = asset_overview.get("pnl_pct")
    cash_pct = None
    if total and total != 0:
        cash_pct = cash / total if cash is not None else None

    return Div(
        Div(
            Div(
                P("总资产", cls="text-sm text-gray-600"),
                P(f"{_format_amount_wan(total)}万", cls="text-2xl font-bold text-gray-900 mt-1"),
            ),
            Div(
                Span(f"↑ {_format_percent(pnl_pct)}", cls="text-green-600"),
                Span("较昨日", cls="ml-2 text-gray-600"),
                cls="mt-4 flex items-center text-sm",
            ),
            cls="bg-white rounded-lg shadow p-6",
        ),
        Div(
            Div(
                P("持仓市值", cls="text-sm text-gray-600"),
                P(
                    f"{_format_amount_wan(market_value)}万",
                    cls="text-2xl font-bold text-gray-900 mt-1",
                ),
            ),
            Div(
                Span(f"↑ {_format_percent(pnl_pct)}", cls="text-green-600"),
                Span("较昨日", cls="ml-2 text-gray-600"),
                cls="mt-4 flex items-center text-sm",
            ),
            cls="bg-white rounded-lg shadow p-6",
        ),
        Div(
            Div(
                P("可用资金", cls="text-sm text-gray-600"),
                P(f"{_format_amount_wan(cash)}万", cls="text-2xl font-bold text-gray-900 mt-1"),
            ),
            Div(
                Span(f"占比 {_format_percent(cash_pct)}", cls="text-gray-600"),
                cls="mt-4 flex items-center text-sm",
            ),
            cls="bg-white rounded-lg shadow p-6",
        ),
        Div(
            Div(
                P("今日盈亏", cls="text-sm text-gray-600"),
                P(f"{_format_amount_wan(pnl)}万", cls="text-2xl font-bold text-green-600 mt-1"),
            ),
            Div(
                Span(f"↑ {_format_percent(pnl_pct)}", cls="text-green-600"),
                Span("收益率", cls="ml-2 text-gray-600"),
                cls="mt-4 flex items-center text-sm",
            ),
            cls="bg-white rounded-lg shadow p-6",
        ),
        cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6",
    )


def PositionTable(positions: list[Position] | None = None) -> Any:
    """构建持仓明细表格。

    Args:
        positions: 持仓列表

    Returns:
        Div: 持仓表格区域
    """
    rows = []
    if positions:
        for p in positions:
            cost = p.mv - p.profit
            profit_pct = p.profit / cost if cost else 0
            tag_text, tag_cls = _position_tag(profit_pct)
            current_price = p.mv / p.shares if p.shares else 0
            rows.append(
                Tr(
                    Td(
                        Span(
                            tag_text,
                            cls=(
                                "inline-flex items-center px-2 py-1 rounded text-xs "
                                "font-medium "
                                f"{tag_cls}"
                            ),
                        )
                    ),
                    Td(p.asset, cls="text-gray-900"),
                    Td(p.asset, cls="text-gray-900"),
                    Td(f"{p.shares:,.0f}", cls="text-gray-900"),
                    Td(f"{p.avail:,.0f}", cls="text-gray-900"),
                    Td(f"{p.price:,.2f}", cls="text-gray-900"),
                    Td(f"{current_price:,.2f}", cls="text-gray-900"),
                    Td(f"{p.mv / 10000:,.2f}", cls="text-gray-900"),
                    Td(
                        f"{p.profit / 10000:,.2f} ({profit_pct * 100:.2f}%)",
                        cls="text-green-600" if p.profit >= 0 else "text-red-600",
                    ),
                    Td(Button("卖出", cls="text-green-600 hover:underline")),
                    cls="border-t border-gray-200",
                )
            )
    else:
        rows.append(
            Tr(
                Td("暂无持仓", colspan="10", cls="py-6 text-center text-gray-500"),
                cls="border-t border-gray-200",
            )
        )

    return Div(
        Div(
            H2("持仓明细", cls="text-lg font-semibold text-gray-900"),
            cls="p-6 border-b border-gray-200",
        ),
        Div(
            Div(
                Table(
                    Thead(
                        Tr(
                            Th("AI预警", cls="pb-3 font-medium w-16"),
                            Th("股票代码", cls="pb-3 font-medium"),
                            Th("股票名称", cls="pb-3 font-medium"),
                            Th("持仓数量", cls="pb-3 font-medium"),
                            Th("可用", cls="pb-3 font-medium"),
                            Th("成本价", cls="pb-3 font-medium"),
                            Th("现价", cls="pb-3 font-medium"),
                            Th("市值(万)", cls="pb-3 font-medium"),
                            Th("盈亏(万)", cls="pb-3 font-medium"),
                            Th("操作", cls="pb-3 font-medium"),
                            cls="text-left text-sm text-gray-600",
                        )
                    ),
                    Tbody(*rows, cls="text-sm"),
                    cls="w-full",
                ),
                cls="overflow-x-auto",
            ),
            cls="p-6",
        ),
        cls="bg-white rounded-lg shadow mb-6",
    )


def _order_status_badge(status: OrderStatus) -> tuple[str, str]:
    """构建订单状态标签。

    Args:
        status: 订单状态

    Returns:
        tuple[str, str]: 文本与样式
    """
    if status == OrderStatus.SUCCEEDED:
        return "已成交", "bg-green-100 text-green-800"
    if status == OrderStatus.PART_SUCC:
        return "部分成交", "bg-gray-100 text-gray-800"
    if status == OrderStatus.CANCELED:
        return "已撤单", "bg-gray-100 text-gray-600"
    if status == OrderStatus.JUNK:
        return "废单", "bg-red-100 text-red-800"
    return "待成交", "bg-gray-100 text-gray-700"


def _home_order_row(order: Any) -> Any:
    """Render one row with its display values and available actions."""
    side = order.get("side", OrderSide.BUY)
    if isinstance(side, int):
        side = OrderSide(side)
    status = order.get("status", OrderStatus.UNREPORTED)
    if isinstance(status, int):
        status = OrderStatus(status)
    status_text, status_cls = _order_status_badge(status)
    return Tr(
        Td(order.get("tm", ""), cls="py-4 text-gray-900"),
        Td(order.get("asset", ""), cls="py-4 text-gray-900"),
        Td(order.get("asset", ""), cls="py-4 text-gray-900"),
        Td(
            Span(
                "买入" if side == OrderSide.BUY else "卖出",
                cls="text-red-600 font-medium"
                if side == OrderSide.BUY
                else "text-green-600 font-medium",
            )
        ),
        Td(_format_amount(order.get("price")), cls="py-4 text-gray-900"),
        Td(f"{order.get('shares', 0):,.0f}", cls="py-4 text-gray-900"),
        Td(f"{order.get('filled', 0):,.0f}", cls="py-4 text-gray-900"),
        Td(
            Span(
                status_text,
                cls=f"inline-flex items-center px-2 py-1 rounded text-xs font-medium {status_cls}",
            ),
            cls="py-4",
        ),
        Td(
            Button(
                "撤单",
                cls="text-[#e41815] hover:underline"
                if status not in [OrderStatus.SUCCEEDED, OrderStatus.CANCELED]
                else "text-gray-400 cursor-not-allowed",
                disabled=status in [OrderStatus.SUCCEEDED, OrderStatus.CANCELED],
            ),
            cls="py-4",
        ),
        cls="border-t border-gray-200",
    )


def OrderTable(orders: list[dict[str, Any]] | None = None) -> Any:
    """构建当日委托表格。

    Args:
        orders: 订单数据

    Returns:
        Div: 当日委托区域
    """
    rows: list[Any] = []
    if orders:
        rows.extend(_home_order_row(order) for order in orders)
    else:
        rows.append(
            Tr(
                Td("暂无委托", colspan="9", cls="py-6 text-center text-gray-500"),
                cls="border-t border-gray-200",
            )
        )

    return Div(
        Div(
            H2("当日委托", cls="text-lg font-semibold text-gray-900"),
            cls="p-6 border-b border-gray-200",
        ),
        Div(
            Div(
                Table(
                    Thead(
                        Tr(
                            Th("时间", cls="pb-3 font-medium"),
                            Th("股票代码", cls="pb-3 font-medium"),
                            Th("股票名称", cls="pb-3 font-medium"),
                            Th("方向", cls="pb-3 font-medium"),
                            Th("委托价", cls="pb-3 font-medium"),
                            Th("委托量", cls="pb-3 font-medium"),
                            Th("成交量", cls="pb-3 font-medium"),
                            Th("状态", cls="pb-3 font-medium"),
                            Th("操作", cls="pb-3 font-medium"),
                            cls="text-left text-sm text-gray-600",
                        )
                    ),
                    Tbody(*rows, cls="text-sm"),
                    cls="w-full",
                ),
                cls="overflow-x-auto",
            ),
            cls="p-6",
        ),
        cls="bg-white rounded-lg shadow",
    )


def NoAccountDialog() -> Any:
    """无账户提示对话框"""
    branding = get_branding()
    return Div(
        Div(
            Div(
                # 图标
                Div(
                    UkIcon("alert-circle", size=48, cls="text-[#e41815]"),
                    cls="flex justify-center mb-4",
                ),
                # 标题
                H3(
                    f"欢迎使用 {branding.product_name}",
                    cls="text-xl font-semibold text-gray-900 text-center mb-2",
                ),
                # 说明
                P(
                    "您还没有配置任何交易账号。请创建至少一个模拟交易账户或配置实盘账户，才能开始使用系统。",
                    cls="text-gray-600 text-center mb-6",
                ),
                # 按钮组
                Div(
                    A(
                        "跳转账号管理",
                        href="/system/accounts",
                        cls=(
                            "px-4 py-2 border border-gray-300 text-gray-700 rounded-lg "
                            "hover:bg-gray-50 font-medium"
                        ),
                    ),
                    A(
                        "创建模拟交易账户",
                        href="/system/accounts?create_sim=1",
                        cls=(
                            "px-4 py-2 bg-[#e41815] text-white rounded-lg "
                            "hover:bg-[#c91412] font-medium"
                        ),
                    ),
                    cls="flex justify-center space-x-3",
                ),
                cls="bg-white p-8 rounded-lg shadow-lg max-w-md w-full mx-4",
            ),
            cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
            id="no-account-dialog",
        ),
        cls="max-w-[1400px] mx-auto w-full",
    )


def _should_show_no_account_dialog(accounts: list[dict[str, Any]]) -> bool:
    """首页不主动弹出账号创建对话框。

    交易账号创建属于交易入口流程的一部分，不应在用户访问首页时抢占界面。
    """
    return False


def _should_redirect_to_strategy() -> bool:
    """首页是否应重定向到策略页。

    等价于 `not live_trading_available`（即 `not gateway_enabled`）。
    函数体保留以维持调用点语义清晰；`get_feature_status()["live_trading"]`
    已封装 dev-stub 模式、gateway 配置与连接性测试为单一标志。
    """
    try:
        return not bool(init_wizard.get_feature_status().get("live_trading"))
    except Exception:
        return True


def main_block(
    asset_overview: dict[str, Any] | None = None,
    brokers: list[dict[str, Any]] | None = None,
    positions: list[Position] | None = None,
    orders: list[dict[str, Any]] | None = None,
    show_no_account_dialog: bool = False,
) -> Any:
    if show_no_account_dialog:
        return NoAccountDialog()

    return Div(
        Div(
            Nav(
                A("首页", href="#", cls="hover:text-[#e41815]"),
                Span(" / ", cls="text-gray-400"),
                Span("概览", cls="text-gray-900 font-medium"),
                cls="flex w-fit items-center justify-start space-x-2 text-sm text-gray-600",
            ),
            cls="mb-4",
        ),
        OverviewCards(asset_overview),
        PositionTable(positions),
        OrderTable(orders),
        cls="max-w-[1400px] mx-auto w-full",
    )


def _get_broker(req: Request) -> Any:
    reg = req.scope.get("registry")
    if not reg:
        return None
    kind, account_id = req.query_params.get("kind"), req.query_params.get("id")
    if kind and account_id:
        return _home_account_broker(reg, kind, account_id)
    session = req.scope.get("session", {})
    kind, account_id = session.get("active_account_kind"), session.get("active_account_id")
    if kind and account_id:
        if str(kind).lower() in {"qmt", "live"} and not supports_live_trading():
            return None
        broker = _home_account_broker(reg, BrokerKind(kind), account_id)
        if broker:
            return broker
    default = reg.get_default()
    return _home_account_broker(reg, *default) if default else None


def _home_account_broker(reg: Any, kind: Any, account_id: Any) -> Any:
    if str(kind).lower() in {"qmt", "live"} and not supports_live_trading():
        return None
    return reg.get(kind, account_id)


def _auto_select_account(reg: BrokerRegistry, session: dict[str, Any]) -> tuple[str, str] | None:
    """自动选择活动账户

    优先级：
    1. 实盘账户（只允许一个）
    2. 最后创建的模拟账户

    Returns:
        (kind, account_id) 或 None
    """
    if reg is None:
        return None

    # 检查是否有实盘账户
    live_accounts = reg.list_by_kind(BrokerKind.QMT) if supports_live_trading() else []
    if live_accounts:
        # 实盘账户只允许一个，选择第一个
        info = live_accounts[0]
        account_id = info.get("id")
        if account_id:
            return (BrokerKind.QMT.value, account_id)

    # 检查模拟账户，选择最后创建的
    sim_accounts = reg.list_by_kind(BrokerKind.SIMULATION)
    if sim_accounts:
        # 选择最后一个（最后创建的）
        info = sim_accounts[-1]
        account_id = info.get("id")
        if account_id:
            return (BrokerKind.SIMULATION.value, account_id)

    return None


@rt("/", methods="get")
def index(req: Request, session: SessionData) -> Any:
    if _should_redirect_to_strategy():
        return RedirectResponse("/strategy/", status_code=303)
    return RedirectResponse("/trade/live/", status_code=303)


@rt("/positions")
async def get_positions(req: Request) -> Any:
    broker = _get_broker(req)
    positions = _normalize_positions(_safe_broker_attr(broker, "positions", [])) if broker else []
    return PositionInfo(positions)


@rt("/order", methods=["POST"])
async def place_order(req: Request) -> Any:
    broker = _get_broker(req)
    if not broker:
        return "Broker not found"

    try:
        await submit_share_form(broker, await req.form())

        # Return updated components with OOB swap
        positions = _normalize_positions(_safe_broker_attr(broker, "positions", []))

        # Build overview manually or use helper if possible
        overview = _build_broker_asset_overview(broker) or {
            "total": 0,
            "cash": 0,
            "frozen_cash": 0,
            "market_value": 0,
            "pnl": 0,
            "pnl_pct": 0,
        }

        return (PositionInfo(positions), AssetSummary(overview, hx_swap_oob="true"))
    except Exception as e:
        logger.exception(e)
        # Show the error in the position panel.
        # Actually returning a simple div will replace PositionInfo.
        # Better to use hx-swap-oob to show error in a specific container.
        # But for simplicity:
        return Div(f"Error: {str(e)}", cls="text-red-500 font-bold p-4 bg-red-100 rounded")
