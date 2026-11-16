"""仿真（paper）交易页面。"""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    H1,
    H2,
    H3,
    A,
    Button,
    Div,
    Form,
    Input,
    Label,
    P,
    RedirectResponse,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)
from loguru import logger
from monsterui.all import UkIcon
from starlette.requests import Request

from quantide.core.enums import BrokerKind
from quantide.web.application import fast_app
from quantide.web.components.asset_label import resolve_asset_name
from quantide.web.layouts.main import MainLayout
from quantide.web.services.trade_orders import submit_share_form
from quantide.web.session_data import SessionData
from quantide.web.theme import AppTheme

paper_app, rt = fast_app(hdrs=AppTheme.headers())


def _get_registry(req: Request) -> Any:
    return req.scope.get("registry")


def _resolve_account_id(req: Request) -> str | None:
    """从 query string 读取 account_id。"""
    params = req.query_params
    return params.get("account_id") or None


def _resolve_default_paper_account(req: Request) -> str | None:
    """无 account_id 时取第一个 SIMULATION 账户。"""
    reg = _get_registry(req)
    if reg is None:
        return None
    sims = reg.list_by_kind(BrokerKind.SIMULATION)
    if not sims:
        return None
    account_id = sims[0].get("id")
    return account_id if isinstance(account_id, str) else None


@rt("/")
def paper_list(req: Request, session: SessionData) -> Any:
    """`GET /trade/paper/` 已废弃：统一跳转到 /trade（带 account_id）。"""
    account_id = _resolve_account_id(req)
    if account_id:
        reg = _get_registry(req)
        if reg is not None:
            try:
                if reg.get(BrokerKind.SIMULATION, account_id) is not None:
                    session["active_account_kind"] = BrokerKind.SIMULATION.value
                    session["active_account_id"] = account_id
            except Exception:
                pass
    url = "/trade" + (f"?account_id={account_id}" if account_id else "")
    return RedirectResponse(url, status_code=303)


BRAND_RED = "#e41815"


def _fmt_money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def AssetSummary(asset_overview: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    """资产概览：白底卡片 + 分隔线，与项目整体风格一致。"""
    overview = asset_overview or {}
    pnl = float(overview.get("pnl") or 0.0)
    pnl_cls = "text-red-500" if pnl > 0 else ("text-green-600" if pnl < 0 else "text-gray-900")
    pnl_pct = float(overview.get("pnl_pct") or 0.0) * 100

    def stat(label: str, value: str, value_cls: str = "text-gray-900") -> Any:
        return Div(
            P(label, cls="text-xs text-gray-500"),
            P(value, cls=f"mt-1 text-xl font-semibold tabular-nums {value_cls}"),
            cls="bg-white px-4 py-4",
        )

    return Div(
        Div(
            stat("总资产", _fmt_money(overview.get("total"))),
            stat("可用金额", _fmt_money(overview.get("cash"))),
            stat("冻结金额", _fmt_money(overview.get("frozen_cash"))),
            stat("总市值", _fmt_money(overview.get("market_value"))),
            stat("盈亏", _fmt_money(pnl), pnl_cls),
            stat("盈亏比例", f"{pnl_pct:.2f}%", pnl_cls),
            cls="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-px bg-gray-100",
        ),
        id="asset-summary",
        cls="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm",
        **kwargs,
    )


def _paper_position_row(p: Any) -> Any:
    """Render one row with its display values and available actions."""
    pnl_pct = (p.profit / (p.mv - p.profit)) if (p.mv - p.profit) != 0 else 0
    current_price = p.mv / p.shares if p.shares > 0 else 0
    color_cls = (
        "text-red-500" if p.profit > 0 else ("text-green-600" if p.profit < 0 else "text-gray-900")
    )
    return Tr(
        Td(p.asset, cls="font-mono text-xs text-gray-700"),
        Td(resolve_asset_name(p.asset), cls="text-gray-700"),
        Td(f"{p.shares:,}", cls="text-right tabular-nums"),
        Td(f"{p.avail:,}", cls="text-right tabular-nums"),
        Td(f"{p.shares - p.avail:,}", cls="text-right tabular-nums"),
        Td(f"{p.mv:,.2f}", cls="text-right tabular-nums"),
        Td(f"{current_price:,.2f}", cls="text-right tabular-nums"),
        Td(f"{p.price:,.2f}", cls="text-right tabular-nums"),
        Td(f"{p.profit:,.2f}", cls=f"text-right tabular-nums {color_cls}"),
        Td(f"{pnl_pct * 100:.2f}%", cls=f"text-right tabular-nums {color_cls}"),
        cls="border-b border-gray-50 last:border-0",
    )


def PositionInfo(positions: list[Any] | None = None, portfolio_id: str = "") -> Any:
    """持仓面板：白底卡片、红色强调，刷新走 paper 路由。"""
    headers = [
        ("证券代码", "text-left"),
        ("证券名称", "text-left"),
        ("当前持股", "text-right"),
        ("可用股数", "text-right"),
        ("冻结数量", "text-right"),
        ("市值", "text-right"),
        ("最新价", "text-right"),
        ("成本价", "text-right"),
        ("盈亏", "text-right"),
        ("盈亏比例", "text-right"),
    ]

    rows: list[Any] = []
    if positions:
        rows.extend(_paper_position_row(p) for p in positions)
    else:
        rows.append(
            Tr(
                Td(
                    Div(
                        UkIcon("briefcase", size=28, cls="mx-auto text-gray-300"),
                        P("暂无持仓", cls="mt-2 text-sm font-medium text-gray-500"),
                        P(
                            "策略成交后会在这里显示持仓明细",
                            cls="mt-0.5 text-xs text-gray-400",
                        ),
                        cls="py-12 text-center",
                    ),
                    colspan=len(headers),
                )
            )
        )

    return Div(
        Div(
            Div(
                UkIcon("briefcase", size=18, cls="text-[#e41815]"),
                H3("持仓信息", cls="text-base font-semibold text-gray-900"),
                cls="flex items-center gap-2",
            ),
            Button(
                UkIcon("refresh-cw", size=14),
                "刷新",
                type="button",
                hx_get=f"/trade/paper/{portfolio_id}/positions",
                hx_target="#position-info",
                hx_swap="outerHTML",
                cls=(
                    "inline-flex items-center gap-1 rounded-lg border border-gray-200 "
                    "bg-white px-3 py-1.5 text-xs font-medium text-gray-600 "
                    "hover:border-[#e41815] hover:text-[#e41815]"
                ),
            ),
            cls="mb-4 flex items-center justify-between",
        ),
        Div(
            Table(
                Thead(
                    Tr(
                        *[
                            Th(
                                label,
                                cls=(
                                    "whitespace-nowrap border-b border-gray-100 px-3 "
                                    "py-2 text-xs font-medium text-gray-500 "
                                    f"{align}"
                                ),
                            )
                            for label, align in headers
                        ]
                    )
                ),
                Tbody(*rows),
                cls="w-full text-sm",
            ),
            cls="overflow-x-auto",
        ),
        id="position-info",
        cls="h-full rounded-xl border border-gray-100 bg-white p-5 shadow-sm",
    )


def TradePanel(portfolio_id: str) -> Any:
    """下单面板：白底、红色主按钮，提交到 paper 路由。"""
    label_cls = "block text-xs font-medium text-gray-500"
    input_cls = (
        "mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm "
        "text-gray-900 outline-none transition focus:border-[#e41815] "
        "focus:ring-2 focus:ring-[#e41815]/10"
    )
    ratio_cls = (
        "rounded-md border border-gray-200 px-2 py-1 text-[11px] text-gray-600 "
        "transition hover:border-[#e41815] hover:text-[#e41815]"
    )
    tab_base = (
        "flex flex-1 cursor-pointer items-center justify-center gap-1 rounded-md "
        "px-3 py-1.5 text-xs font-semibold transition"
    )

    return Div(
        Div(
            H3("交易下单", cls="text-base font-semibold text-gray-900"),
            P(
                "手工买卖仅用于联调；策略交易由运行时自动执行。",
                cls="mt-1 text-xs text-gray-500",
            ),
            cls="mb-4",
        ),
        Form(
            Div(
                Label(
                    Input(
                        type="radio",
                        name="side",
                        value="BUY",
                        checked=True,
                        cls="peer sr-only",
                    ),
                    Span(
                        UkIcon("plus-circle", size=14),
                        "买入",
                        cls=(
                            f"{tab_base} text-gray-500 "
                            "peer-checked:bg-[#e41815] peer-checked:text-white"
                        ),
                    ),
                    cls="flex flex-1",
                ),
                Label(
                    Input(type="radio", name="side", value="SELL", cls="peer sr-only"),
                    Span(
                        UkIcon("minus-circle", size=14),
                        "卖出",
                        cls=(
                            f"{tab_base} text-gray-500 "
                            "peer-checked:bg-green-600 peer-checked:text-white"
                        ),
                    ),
                    cls="flex flex-1",
                ),
                cls="mb-4 flex gap-1 rounded-lg bg-gray-100 p-1",
            ),
            Div(
                Label("股票代码", cls=label_cls),
                Input(
                    name="asset",
                    placeholder="例如: 000001.SZ",
                    required=True,
                    cls=input_cls,
                ),
                cls="mb-3",
            ),
            Div(
                Label("委托价格", cls=label_cls),
                Input(
                    name="price",
                    type="number",
                    step="0.01",
                    value="0.00",
                    cls=input_cls,
                ),
                P("填 0 表示市价委托", cls="mt-1 text-[11px] text-gray-400"),
                cls="mb-3",
            ),
            Div(
                Label("仓位选择", cls=label_cls),
                Div(
                    Button("满仓", type="button", cls=ratio_cls),
                    Button("1/2", type="button", cls=ratio_cls),
                    Button("1/3", type="button", cls=ratio_cls),
                    Button("1/4", type="button", cls=ratio_cls),
                    Button("1/10", type="button", cls=ratio_cls),
                    cls="mt-1.5 flex flex-wrap gap-1.5",
                ),
                cls="mb-3",
            ),
            Div(
                Label("交易数量（股）", cls=label_cls),
                Input(
                    name="shares",
                    type="number",
                    step="100",
                    required=True,
                    cls=input_cls,
                ),
                cls="mb-4",
            ),
            Button(
                UkIcon("shopping-cart", size=16),
                "提交委托",
                type="submit",
                cls=(
                    "inline-flex w-full items-center justify-center gap-2 rounded-lg "
                    "bg-[#e41815] px-4 py-2.5 text-sm font-semibold text-white "
                    "transition hover:bg-[#c91412]"
                ),
            ),
            hx_post=f"/trade/paper/{portfolio_id}/order",
            hx_target="#position-info",
            hx_swap="outerHTML",
        ),
        cls="h-full rounded-xl border border-gray-100 bg-white p-5 shadow-sm",
    )


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

    def main_block() -> Any:
        return Div(
            A(
                "← 返回仿真列表",
                href="/trade/paper/",
                cls="inline-flex text-sm text-gray-500 transition hover:text-gray-900",
            ),
            Div(
                Div(
                    Div(
                        H1(name, cls="text-xl font-semibold text-gray-900"),
                        Span(
                            "仿真账户",
                            cls=(
                                "ml-3 inline-flex items-center rounded-full bg-[#fff3f2] "
                                "px-2.5 py-0.5 text-xs font-medium text-[#e41815]"
                            ),
                        ),
                        cls="flex flex-wrap items-center",
                    ),
                    P(f"ID: {account_id}", cls="mt-1 font-mono text-xs text-gray-500"),
                    cls="min-w-0",
                ),
                A(
                    "账号管理",
                    href="/system/accounts",
                    cls=(
                        "rounded-lg border border-gray-200 px-3 py-1.5 text-xs "
                        "font-medium text-gray-600 transition hover:border-gray-300 "
                        "hover:text-gray-900"
                    ),
                ),
                cls=(
                    "flex flex-wrap items-start justify-between gap-4 rounded-xl "
                    "border border-gray-100 bg-white p-6 shadow-sm"
                ),
            ),
            AssetSummary(asset_overview),
            Div(
                Div(PositionInfo(positions, account_id), cls="xl:col-span-3"),
                Div(TradePanel(account_id), cls="xl:col-span-1"),
                cls="grid grid-cols-1 gap-6 xl:grid-cols-4",
            ),
            cls="space-y-6",
        )

    layout.set_main_block(main_block)
    return layout.render()


def _render_paper_picker(layout: MainLayout, sims: list[dict[str, Any]]) -> Any:
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
                        href=f"/trade/paper/?account_id={account_id}",
                        cls="uk-button uk-button-primary uk-button-small",
                    ),
                ),
            )
        )

    table = Table(
        Thead(Tr(Th("账户ID"), Th("账户名称"), Th("操作"))),
        Tbody(*rows),
        cls=(
            "uk-table uk-table-divider uk-table-small uk-table-hover border "
            "border-gray-100 rounded-lg overflow-hidden"
        ),
    )

    def main_block() -> Any:
        return Div(
            H2("请选择仿真账户", cls="text-lg font-bold mb-4"),
            P("当前系统中有多个仿真账户，请选择一个进入。", cls="text-sm text-gray-600 mb-4"),
            table,
            cls="p-4 bg-white rounded-xl shadow-sm border border-gray-100",
        )

    layout.set_main_block(main_block)
    return layout.render()


def _render_empty_paper(layout: MainLayout) -> Any:
    def main_block() -> Any:
        return Div(
            H2("暂无仿真账户", cls="text-lg font-bold mb-2"),
            P(
                "请先在 init wizard 中添加仿真账户。",
                cls="text-sm text-gray-600",
            ),
            cls="p-6 bg-white rounded-xl shadow-sm border border-gray-100",
        )

    layout.set_main_block(main_block)
    return layout.render()


def _render_no_registry(session: SessionData) -> Any:
    layout = MainLayout(title="仿真交易", user=session.get("auth"))

    def main_block() -> Any:
        return Div(
            P("Broker registry 不可用。", cls="text-red-500 p-4"),
        )

    layout.set_main_block(main_block)
    return layout.render()


@rt("/{portfolio_id}/positions")
def get_positions(req: Request, portfolio_id: str) -> Any:
    reg = _get_registry(req)
    broker = reg.get(BrokerKind.SIMULATION, portfolio_id) if reg else None
    positions = list(broker.positions) if broker and hasattr(broker, "positions") else []
    return PositionInfo(positions, portfolio_id)


@rt("/{portfolio_id}/order", methods=["POST"])
async def place_order(req: Request, portfolio_id: str) -> Any:
    reg = _get_registry(req)
    broker = reg.get(BrokerKind.SIMULATION, portfolio_id) if reg else None

    if not broker:
        return Div("Broker not found", cls="text-red-500 p-4")

    try:
        await submit_share_form(broker, await req.form())

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
