"""仿真（paper）交易页面。"""
from typing import Any

from fasthtml.common import *
from loguru import logger

from quantide.core.enums import BrokerKind
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.live import (
    AssetSummary,
    PositionInfo,
    TradePanel,
)
from quantide.web.theme import AppTheme

paper_app, rt = fast_app(hdrs=AppTheme.headers())


def _get_registry(req) -> Any:
    return req.scope.get("registry")


def _resolve_account_id(req) -> str | None:
    """从 query string 读取 account_id。"""
    params = req.query_params
    return params.get("account_id") or None


def _resolve_default_paper_account(req) -> str | None:
    """无 account_id 时取第一个 SIMULATION 账户。"""
    reg = _get_registry(req)
    if reg is None:
        return None
    sims = reg.list_by_kind(BrokerKind.SIMULATION)
    if not sims:
        return None
    return sims[0].get("id")


@rt("/")
def paper_list(req, session):
    """`GET /trade/paper/` 入口。

    行为：
    * 无 `?account_id=` 且有且仅有一个 SIMULATION 账户：直接渲染该账户
    * 无 `?account_id=` 且有多个 SIMULATION 账户：渲染账户选择列表
    * 无 `?account_id=` 且无 SIMULATION 账户：渲染空态
    * 有 `?account_id=`：按 ID 加载
    """
    reg = _get_registry(req)
    if reg is None:
        return _render_no_registry(session)

    sims = reg.list_by_kind(BrokerKind.SIMULATION)
    requested = _resolve_account_id(req)

    layout = MainLayout(title="仿真交易", user=session.get("auth"))

    if requested:
        broker = reg.get(BrokerKind.SIMULATION, requested)
        if broker is None:
            return Div(
                H2("未找到该仿真账户", cls="text-lg font-bold"),
                P(f"账户 ID: {requested}", cls="text-sm text-gray-600"),
                A("返回仿真列表", href="/trade/paper/", cls="text-blue-600"),
                cls="p-6",
            )
        return _render_paper_account(layout, broker)

    if not sims:
        return _render_empty_paper(layout)

    if len(sims) == 1:
        only = sims[0]
        broker = reg.get(BrokerKind.SIMULATION, only.get("id"))
        if broker is None:
            return _render_empty_paper(layout)
        return _render_paper_account(layout, broker)

    return _render_paper_picker(layout, sims)


def _render_paper_account(layout: MainLayout, broker: Any) -> Any:
    account_id = broker.portfolio_id
    name = getattr(broker, "portfolio_name", account_id)

    asset_overview = {
        "total": getattr(broker, "total_assets", 0),
        "cash": getattr(broker, "cash", 0),
        "frozen_cash": 0,
        "market_value": getattr(broker, "total_assets", 0) - getattr(broker, "cash", 0),
        "pnl": getattr(broker, "total_assets", 0) - getattr(broker, "principal", 0),
        "pnl_pct": (
            (getattr(broker, "total_assets", 0) - getattr(broker, "principal", 0))
            / getattr(broker, "principal", 1)
            if getattr(broker, "principal", 0)
            else 0
        ),
    }

    positions = broker.positions if hasattr(broker, "positions") else []

    def main_block():
        return Div(
            Div(
                A(
                    "← 返回仿真列表",
                    href="/trade/paper/",
                    cls="text-sm text-gray-600 hover:text-gray-900 mb-4 inline-block",
                ),
                cls="mb-4",
            ),
            Div(
                H2(f"仿真账户：{name}", cls="text-lg font-bold mb-2"),
                Span(f"ID: {account_id}", cls="text-xs text-gray-500"),
                cls="mb-4",
            ),
            AssetSummary(asset_overview),
            Div(
                Div(PositionInfo(positions, account_id), cls="w-3/4 pr-4"),
                Div(TradePanel(account_id), cls="w-1/4"),
                cls="flex",
            ),
            cls="p-4",
        )

    layout.main_block = main_block
    return layout.render()


def _render_paper_picker(layout: MainLayout, sims: list[dict]) -> Any:
    rows = []
    for info in sims:
        account_id = info.get("id", "")
        name = info.get("name") or account_id
        rows.append(
            Tr(
                Td(account_id),
                Td(name),
                Td(
                    A(
                        "进入",
                        href=f"/trade/paper?account_id={account_id}",
                        cls="uk-button uk-button-primary uk-button-small",
                    ),
                ),
            )
        )

    table = Table(
        Thead(Tr(Th("账户ID"), Th("账户名称"), Th("操作"))),
        Tbody(*rows),
        cls="uk-table uk-table-divider uk-table-small uk-table-hover border border-gray-100 rounded-lg overflow-hidden",
    )

    def main_block():
        return Div(
            H2("请选择仿真账户", cls="text-lg font-bold mb-4"),
            P("当前系统中有多个仿真账户，请选择一个进入。", cls="text-sm text-gray-600 mb-4"),
            table,
            cls="p-4 bg-white rounded-xl shadow-sm border border-gray-100",
        )

    layout.main_block = main_block
    return layout.render()


def _render_empty_paper(layout: MainLayout) -> Any:
    def main_block():
        return Div(
            H2("暂无仿真账户", cls="text-lg font-bold mb-2"),
            P(
                "请先在 init wizard 中添加仿真账户。",
                cls="text-sm text-gray-600",
            ),
            cls="p-6 bg-white rounded-xl shadow-sm border border-gray-100",
        )

    layout.main_block = main_block
    return layout.render()


def _render_no_registry(session) -> Any:
    layout = MainLayout(title="仿真交易", user=session.get("auth"))

    def main_block():
        return Div(
            P("Broker registry 不可用。", cls="text-red-500 p-4"),
        )

    layout.main_block = main_block
    return layout.render()


@rt("/{portfolio_id}/positions")
def get_positions(req, portfolio_id: str):
    reg = _get_registry(req)
    broker = reg.get(BrokerKind.SIMULATION, portfolio_id) if reg else None
    positions = list(broker.positions) if broker and hasattr(broker, "positions") else []
    return PositionInfo(positions, portfolio_id)


@rt("/{portfolio_id}/order", methods=["POST"])
async def place_order(req, portfolio_id: str):
    reg = _get_registry(req)
    broker = reg.get(BrokerKind.SIMULATION, portfolio_id) if reg else None

    if not broker:
        return Div("Broker not found", cls="text-red-500 p-4")

    form = await req.form()
    side = form.get("side", "BUY")
    asset = form.get("asset")
    price = float(form.get("price", 0))
    shares = int(form.get("shares", 0))

    try:
        if side == "BUY":
            await broker.buy(asset, shares, price)
        else:
            await broker.sell(asset, shares, price)

        positions = list(broker.positions) if hasattr(broker, "positions") else []
        asset_overview = {
            "total": getattr(broker, "total_assets", 0),
            "cash": getattr(broker, "cash", 0),
            "frozen_cash": 0,
            "market_value": getattr(broker, "total_assets", 0) - getattr(broker, "cash", 0),
            "pnl": getattr(broker, "total_assets", 0) - getattr(broker, "principal", 0),
            "pnl_pct": (
                (getattr(broker, "total_assets", 0) - getattr(broker, "principal", 0))
                / getattr(broker, "principal", 1)
                if getattr(broker, "principal", 0)
                else 0
            ),
        }

        return (
            PositionInfo(positions, portfolio_id),
            AssetSummary(asset_overview, hx_swap_oob="true"),
        )
    except Exception as e:
        logger.exception(e)
        return Div(f"下单失败: {str(e)}", cls="text-red-500 font-bold p-4 bg-red-100 rounded")
