"""实盘交易页面"""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    Span,
    Tr,
)

# Use FastHTML's plain Label for form elements to avoid MonsterUI's uk-label styling
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    H3,
    Button,
    Form,
    Input,
    Td,
    UkIcon,
)

from quantide.core.enums import BrokerKind
from quantide.data.models import Asset, Position
from quantide.web.application import fast_app
from quantide.web.components.account_positions import AccountPositionInfo
from quantide.web.components.account_summary import AssetSummary as AssetSummary
from quantide.web.components.account_summary import build_asset_overview
from quantide.web.components.data_tables import AccountDetailTable
from quantide.web.components.legacy_trade_panel import LegacyTradeInputs
from quantide.web.layouts.main import MainLayout
from quantide.web.services.trade_orders import submit_share_form
from quantide.web.theme import AppTheme

live_app, rt = fast_app(hdrs=AppTheme.headers())


def _get_registry(req) -> Any:
    return req.scope.get("registry")


def _build_asset_overview(asset: Asset | None) -> dict:
    if asset is None:
        return {
            key: 0 for key in ("total", "cash", "frozen_cash", "market_value", "pnl", "pnl_pct")
        }
    return build_asset_overview(asset)


def GatewayConnectionStatus(connected: bool = False):
    status_cls = "text-green-600" if connected else "text-red-600"
    status_text = "已连接" if connected else "未连接"
    icon = "check-circle" if connected else "x-circle"

    return Div(
        Div(
            UkIcon(icon, size=20, cls=status_cls),
            Span(f" Gateway {status_text}", cls=f"font-medium {status_cls}"),
            cls="flex items-center gap-2",
        ),
        cls="bg-white p-3 rounded-lg shadow-sm border border-gray-100 mb-4",
    )


def PositionInfo(positions: list[Position] | None = None, portfolio_id: str = ""):
    return AccountPositionInfo(positions, refresh_url=f"/trade/live/{portfolio_id}/positions")


def TradePanel(portfolio_id: str):
    """实盘下单面板：白底、红色买入、绿色卖出。"""
    return Div(
        Form(
            Div(
                Div(
                    Button(
                        UkIcon("plus-circle", size=14),
                        "买入",
                        type="button",
                        onclick=(
                            "document.getElementById('side').value='BUY'; "
                            "this.closest('div').querySelectorAll('button').forEach(b=>b."
                            "classList.remove('active')); this.classList.add('active');"
                        ),
                        cls=(
                            "flex-1 rounded-md px-3 py-2 text-sm font-medium transition "
                            "bg-[#e41815] text-white"
                        ),
                    ),
                    Button(
                        UkIcon("minus-circle", size=14),
                        "卖出",
                        type="button",
                        onclick=(
                            "document.getElementById('side').value='SELL'; "
                            "this.closest('div').querySelectorAll('button').forEach(b=>b."
                            "classList.remove('active')); this.classList.add('active');"
                        ),
                        cls=(
                            "flex-1 rounded-md px-3 py-2 text-sm font-medium transition "
                            "bg-green-600 text-white"
                        ),
                    ),
                    cls="grid grid-cols-2 gap-2 mb-4",
                )
            ),
            Input(type="hidden", id="side", name="side", value="BUY"),
            LegacyTradeInputs(
                "委托价格",
                (
                    "inline-flex w-full items-center justify-center gap-2 rounded-lg "
                    "bg-[#e41815] px-4 py-2.5 text-sm font-semibold text-white transition "
                    "hover:bg-[#c91412]"
                ),
            ),
            hx_post=f"/trade/live/{portfolio_id}/order",
            hx_target="#position-info",
            hx_swap="outerHTML",
        ),
        cls="p-6 rounded-xl border border-gray-100 bg-white shadow-sm h-full",
    )


def PortfolioList(portfolios: list[dict], gateway_connected: bool = False):
    headers = ["账户ID", "账户名称", "初始资金", "总资产", "收益率", "状态", "操作"]

    rows = []
    if portfolios:
        for pf in portfolios:
            portfolio_id = pf.get("portfolio_id", "")
            name = pf.get("name", "")
            principal = pf.get("principal", 0)
            total = pf.get("total", 0)
            pnl_pct = pf.get("pnl_pct", 0)
            status = pf.get("status", True)

            status_text = "运行中" if status else "已停止"
            status_cls = "text-green-600" if status else "text-gray-500"

            rows.append(
                Tr(
                    Td(portfolio_id[:8] + "..."),
                    Td(name),
                    Td(f"{principal:,.2f}"),
                    Td(f"{total:,.2f}"),
                    Td(
                        f"{pnl_pct * 100:.2f}%",
                        cls="text-red-500" if pnl_pct > 0 else "text-green-500",
                    ),
                    Td(status_text, cls=status_cls),
                    Td(
                        A(
                            "详情",
                            href=f"/trade/live/{portfolio_id}",
                            cls="uk-button uk-button-primary uk-button-small",
                        ),
                        cls="flex gap-2",
                    ),
                )
            )
    else:
        rows.append(
            Tr(
                Td(
                    "暂无实盘账户",
                    colspan=len(headers),
                    cls="text-center py-10 text-gray-500",
                )
            )
        )

    return Div(
        Div(
            H3("实盘账户列表", cls="text-lg font-bold mb-0"),
            Button(
                UkIcon("plus", size=16),
                " 接入说明",
                cls="uk-button-primary uk-button-small flex items-center gap-1",
                hx_get="/trade/live/create",
                hx_target="#create-modal",
                hx_swap="innerHTML",
            ),
            cls="flex justify-between items-center mb-4",
        ),
        GatewayConnectionStatus(gateway_connected),
        AccountDetailTable(headers, rows),
        cls="bg-white p-4 rounded-xl shadow-sm border border-gray-100",
    )


def CreatePortfolioModal():
    return Div(
        Div(
            H3("Gateway 接入说明", cls="text-lg font-bold mb-4"),
            Div(
                Div(
                    UkIcon("alert-triangle", cls="text-gray-600 mr-2"),
                    P(
                        "主体工程的实盘路径已收敛到 qmt-gateway。这里不再创建本地 QMT 账户。",
                        cls="text-sm text-gray-600",
                    ),
                    cls="flex items-start mb-4 p-3 bg-gray-50 rounded-lg",
                ),
            ),
            Div(
                P(
                    (
                        "发布态实盘能力只通过 gateway 提供。请在 Windows + QMT "
                        "机器上启动 qmt-gateway，并完成登录与连接配置。"
                    ),
                    cls="text-sm text-gray-700 mb-3",
                ),
                P(
                    "当 gateway 可用后，主体会自动在实盘列表中显示 gateway 账户。",
                    cls="text-sm text-gray-700 mb-4",
                ),
                Div(
                    Button(
                        "关闭",
                        type="button",
                        cls="uk-button uk-button-primary",
                        onclick="document.getElementById('create-modal').innerHTML = ''",
                    ),
                    cls="flex justify-end",
                ),
            ),
            cls="bg-white p-6 rounded-xl shadow-xl max-w-md",
        ),
        cls="fixed inset-0 bg-black/50 flex items-center justify-center z-50",
        id="create-modal-content",
    )


@rt("/")
def live_list(req, session):
    layout = MainLayout(title="实盘交易", user=session.get("auth"))
    layout.sidebar_menu = [
        {
            "title": "交易",
            "children": [
                {"title": "仿真", "url": "/trade/paper"},
                {"title": "实盘", "url": "/trade/live"},
            ],
        }
    ]

    reg = _get_registry(req)
    portfolios = []
    gateway_connected = False

    portfolios, gateway_connected = _live_portfolios(reg)

    def main_block():
        return Div(
            PortfolioList(portfolios, gateway_connected),
            Div(id="create-modal"),
            cls="p-4",
        )

    layout.main_block = main_block
    return layout.render()


@rt("/create")
def show_create_modal():
    return CreatePortfolioModal()


@rt("/create", methods=["POST"])
async def create_portfolio(req):
    return Div(
        "主体工程已移除本地QMT账户创建，请通过 gateway 进行实盘接入。", cls="text-gray-500 p-4"
    )


@rt("/{portfolio_id}")
def portfolio_detail(req, session, portfolio_id: str):
    layout = MainLayout(title="实盘账户详情", user=session.get("auth"))
    layout.sidebar_menu = [
        {
            "title": "交易",
            "children": [
                {"title": "仿真", "url": "/trade/paper"},
                {"title": "实盘", "url": "/trade/live"},
            ],
        }
    ]

    reg = _get_registry(req)
    broker = reg.get(BrokerKind.QMT, portfolio_id) if reg else None

    asset_overview = None
    positions = []
    gateway_connected = False

    if broker:
        if hasattr(broker, "asset"):
            asset_overview = _build_asset_overview(broker.asset)
        if hasattr(broker, "positions"):
            positions = (
                list(broker.positions.values())
                if isinstance(broker.positions, dict)
                else broker.positions
            )
        if hasattr(broker, "is_connected"):
            gateway_connected = broker.is_connected

    def main_block():
        return Div(
            Div(
                A(
                    UkIcon("arrow-left", size=16),
                    " 返回列表",
                    href="/trade/live",
                    cls="text-sm text-gray-600 hover:text-gray-900 inline-flex items-center gap-1",
                ),
                A(
                    "对照 →",
                    href=f"/tracking/{portfolio_id}",
                    cls="text-xs font-medium text-[#e41815] hover:text-[#c91412]",
                ),
                cls="mb-4 flex items-center gap-3",
            ),
            GatewayConnectionStatus(gateway_connected),
            AssetSummary(asset_overview),
            Div(
                Div(PositionInfo(positions, portfolio_id), cls="w-3/4 pr-4"),
                Div(TradePanel(portfolio_id), cls="w-1/4"),
                cls="flex",
            ),
            cls="p-4",
        )

    layout.main_block = main_block
    return layout.render()


@rt("/{portfolio_id}/positions")
def get_positions(req, portfolio_id: str):
    reg = _get_registry(req)
    broker = reg.get(BrokerKind.QMT, portfolio_id) if reg else None
    positions = list(broker.positions.values()) if broker and hasattr(broker, "positions") else []
    return PositionInfo(positions, portfolio_id)


@rt("/{portfolio_id}/order", methods=["POST"])
async def place_order(req, portfolio_id: str):
    reg = _get_registry(req)
    broker = reg.get(BrokerKind.QMT, portfolio_id) if reg else None

    if not broker:
        return Div("Broker not found", cls="text-red-500 p-4")

    try:
        await submit_share_form(broker, await req.form())

        positions = list(broker.positions.values()) if hasattr(broker, "positions") else []

        overview = _build_asset_overview(broker.asset if hasattr(broker, "asset") else None)

        return (
            PositionInfo(positions, portfolio_id),
            AssetSummary(overview, hx_swap_oob="true"),
        )
    except Exception as e:
        logger.exception(e)
        return Div(f"下单失败: {str(e)}", cls="text-red-500 font-bold p-4 bg-red-100 rounded")


def _live_portfolios(reg):
    """Read the gateway accounts and their latest connection status."""
    portfolios, gateway_connected = [], False
    if reg:
        brokers = reg.list_by_kind(BrokerKind.QMT)
        for broker_info in brokers:
            portfolio_id = broker_info.get("id")
            broker = reg.get(BrokerKind.QMT, portfolio_id)
            if broker:
                portfolios.append(_live_account_summary(broker_info, portfolio_id, broker))

                if hasattr(broker, "is_connected"):
                    gateway_connected = broker.is_connected
    return portfolios, gateway_connected


def _live_account_summary(broker_info, portfolio_id, broker):
    """Read one account capital snapshot."""
    asset = broker.asset if hasattr(broker, "asset") else None
    pnl_pct = 0
    total = 0
    principal = 0
    if asset:
        total = asset.total
        principal = asset.principal
        pnl_pct = (total - principal) / principal if principal > 0 else 0

    return {
        "portfolio_id": portfolio_id,
        "name": broker_info.get("name", ""),
        "principal": principal,
        "total": total,
        "pnl_pct": pnl_pct,
        "status": broker_info.get("status", True),
    }
